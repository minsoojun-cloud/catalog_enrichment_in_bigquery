import os
import re
import json
import time
import asyncio
import logging
from typing import Dict, Any, List, Optional, Tuple

# Ensure mTLS client cert issue is disabled
os.environ.pop("GOOGLE_API_CERTIFICATE_CONFIG", None)
os.environ["GOOGLE_API_USE_CLIENT_CERTIFICATE"] = "false"
os.environ["CLOUDSDK_CONTEXT_AWARE_USE_CLIENT_CERTIFICATE"] = "false"

from google import genai
from google.genai import types
from app.config import settings

logger = logging.getLogger("enricher")
logger.setLevel(logging.INFO)

# 出力が途中で切れた (finish_reason=MAX_TOKENS) 場合に段階的に引き上げる出力トークン上限。
# gemini-3.x 系は思考トークンも同じ予算を消費するため、初期値を十分に大きく取る。
MAX_OUTPUT_TOKEN_LADDER = [8192, 16384, 32768]

# 検証 (校閲) パス用の出力トークン上限
VERIFICATION_MAX_TOKENS = 32768



class EnrichmentEngine:
    def __init__(self, project_id: Optional[str] = None, location: Optional[str] = None):
        self.project_id = project_id or settings.project_id
        self.location = location or settings.location
        self._client = None

    def get_client(self, project_id: Optional[str] = None, location: Optional[str] = None) -> genai.Client:
        proj = project_id or self.project_id
        loc = location or self.location
        return genai.Client(vertexai=True, project=proj, location=loc)

    def render_prompt(
        self,
        prompt_template: str,
        raw_row: Dict[str, Any],
        mapped_row: Dict[str, Any],
        source_fields: List[str]
    ) -> str:
        """
        Replaces {field_name} placeholders in prompt_template using values from either raw_row or mapped_row.
        Also appends a structured summary of selected source_fields if not explicitly in template.
        """
        context_data = {}
        # Populate from raw_row
        for k, v in raw_row.items():
            context_data[k] = v if v is not None else ""
        # Populate from mapped_row (e.g. title, brands, gtin)
        for k, v in mapped_row.items():
            if isinstance(v, list):
                context_data[k] = ", ".join(str(x) for x in v)
            elif isinstance(v, dict):
                context_data[k] = json.dumps(v, ensure_ascii=False)
            elif v is not None:
                context_data[k] = str(v)

        rendered = prompt_template
        # Replace {key} placeholders
        for k, val in context_data.items():
            placeholder = f"{{{k}}}"
            if placeholder in rendered:
                rendered = rendered.replace(placeholder, str(val))

        # Clean up any remaining {unmatched} placeholders that exist in schema/columns with empty string
        # Only replace simple {word} patterns to avoid breaking JSON examples like {"tags": [...]}
        def replace_unmatched(match):
            key = match.group(1)
            if key in context_data:
                return str(context_data[key])
            # If key looks like a JSON example key (e.g. "tags": ...), keep it
            return match.group(0)

        # Check if all selected source_fields are included; if any selected source field wasn't in prompt, append it
        missing_sources = []
        for sf in source_fields:
            if f"{{{sf}}}" not in prompt_template and sf in context_data and context_data[sf]:
                missing_sources.append(f"- {sf}: {context_data[sf]}")

        if missing_sources:
            rendered += "\n\n# 追加参照データ\n" + "\n".join(missing_sources)

        return rendered

    def parse_llm_output(self, raw_text: str, output_format: str, target_field: str) -> Any:
        """
        Parses raw LLM response text according to output_format and target_field schema requirements.
        """
        if not raw_text:
            return [] if output_format == "json_array" else ""

        cleaned = raw_text.strip()
        # Remove markdown code block wrappers if present
        cleaned_no_fence = re.sub(r"^```(?:json|text|markdown)?\s*", "", cleaned, flags=re.IGNORECASE)
        cleaned_no_fence = re.sub(r"\s*```$", "", cleaned_no_fence).strip()

        if output_format == "text":
            return cleaned_no_fence

        # Try parsing JSON
        parsed_json = None
        try:
            parsed_json = json.loads(cleaned_no_fence)
        except Exception:
            # Try extracting first JSON array or object from text
            arr_match = re.search(r"(\[[\s\S]*\])", cleaned_no_fence)
            obj_match = re.search(r"(\{[\s\S]*\})", cleaned_no_fence)
            if output_format == "json_array" and arr_match:
                try:
                    parsed_json = json.loads(arr_match.group(1))
                except Exception:
                    pass
            if parsed_json is None and obj_match:
                try:
                    parsed_json = json.loads(obj_match.group(1))
                except Exception:
                    pass

        if output_format == "json_array":
            if isinstance(parsed_json, list):
                return [str(x).strip() for x in parsed_json if str(x).strip()]
            elif isinstance(parsed_json, dict):
                # e.g. {"tags": ["a", "b"]} or {"categories": [...]}
                for val in parsed_json.values():
                    if isinstance(val, list):
                        return [str(x).strip() for x in val if str(x).strip()]
            # Fallback: split by comma or newline
            lines = [line.strip().lstrip("-*•1234567890. ") for line in cleaned_no_fence.replace(",", "\n").split("\n")]
            return [x for x in lines if x and not x.startswith("{") and not x.startswith("[")]

        elif output_format == "attributes_kv":
            # Convert to BigQuery attributes RECORD array format:
            # [{"key": "k", "value": {"text": ["v"], "numbers": []}}]
            attr_list = []
            if isinstance(parsed_json, dict):
                for k, v in parsed_json.items():
                    if v is None:
                        continue
                    if isinstance(v, list):
                        texts = [str(i) for i in v if i is not None]
                    else:
                        texts = [str(v)]
                    if texts:
                        attr_list.append({
                            "key": str(k).strip(),
                            "value": {
                                "text": texts,
                                "numbers": []
                            }
                        })
            elif isinstance(parsed_json, list):
                # Already list of records or key-values
                for item in parsed_json:
                    if isinstance(item, dict) and "key" in item:
                        val = item.get("value", {})
                        if isinstance(val, dict) and "text" in val:
                            attr_list.append(item)
                        else:
                            attr_list.append({
                                "key": str(item["key"]),
                                "value": {"text": [str(val)], "numbers": []}
                            })
            return attr_list

        elif output_format == "json_object":
            if isinstance(parsed_json, dict):
                return parsed_json
            return {"raw": cleaned_no_fence}

        return cleaned_no_fence

    # ------------------------------------------------------------------
    # 品質検証 (Quality Verification) ロジック
    # ------------------------------------------------------------------

    # 文末として自然な終端記号
    SENTENCE_TERMINATORS = ("。", "．", ".", "！", "!", "？", "?", "」", "』", "）", ")", "】", "]", "}", "\"", "'", "…", "〜", "・")
    BRACKET_PAIRS = [("「", "」"), ("『", "』"), ("（", "）"), ("(", ")"), ("【", "】"), ("［", "］"), ("[", "]"), ("{", "}")]

    def detect_output_issues(
        self,
        raw_text: str,
        parsed_result: Any,
        output_format: str,
        finish_reason: str = ""
    ) -> List[Dict[str, str]]:
        """
        LLM を呼ばずに機械的に検出できる出力品質の問題点を列挙する。
        返り値: [{"type": ..., "severity": "high|medium|low", "detail": ...}, ...]
        """
        issues: List[Dict[str, str]] = []
        text = (raw_text or "").strip()

        if not text:
            issues.append({"type": "empty", "severity": "high", "detail": "出力が空です。"})
            return issues

        # 1) トークン上限による途中切れ
        if finish_reason and finish_reason.upper() in ("MAX_TOKENS", "LENGTH"):
            issues.append({
                "type": "truncated",
                "severity": "high",
                "detail": f"モデルの出力が最大トークン数に達して途中で打ち切られました (finish_reason={finish_reason})。"
            })

        # 2) 文末が不自然 (テキスト形式のみ)
        if output_format == "text":
            if not text.endswith(self.SENTENCE_TERMINATORS):
                issues.append({
                    "type": "incomplete_sentence",
                    "severity": "high",
                    "detail": f"文章が句点等で終わっておらず、途中で切れている可能性があります (末尾: 「…{text[-25:]}」)。"
                })
            # 3) 括弧の対応が取れていない
            for open_c, close_c in self.BRACKET_PAIRS:
                if text.count(open_c) != text.count(close_c):
                    issues.append({
                        "type": "unbalanced_bracket",
                        "severity": "medium",
                        "detail": f"括弧「{open_c}{close_c}」の開閉数が一致していません ({text.count(open_c)} 対 {text.count(close_c)})。"
                    })
                    break
            # 4) 極端に短い
            if len(text) < 20:
                issues.append({
                    "type": "too_short",
                    "severity": "medium",
                    "detail": f"出力が {len(text)} 文字と極端に短く、内容が不十分な可能性があります。"
                })
            # 5) 同一フレーズの異常な繰り返し
            rep = self._detect_repetition(text)
            if rep:
                issues.append({
                    "type": "repetition",
                    "severity": "medium",
                    "detail": f"同一フレーズが繰り返し出力されています (「{rep}」)。"
                })

        # 6) 未置換のプレースホルダーや定型の穴埋め文字が残っている
        leftover = re.findall(r"\{[A-Za-z_][A-Za-z0-9_]*\}", text)
        if leftover:
            issues.append({
                "type": "unresolved_placeholder",
                "severity": "high",
                "detail": f"未置換のプレースホルダーが残っています: {', '.join(sorted(set(leftover))[:5])}"
            })
        for ng in ["ここに記載", "TODO", "（要確認）", "情報がありません", "不明です", "記載なし", "as an AI", "申し訳ありません"]:
            if ng in text:
                issues.append({
                    "type": "placeholder_text",
                    "severity": "medium",
                    "detail": f"未確定・回答拒否を示す表現が含まれています: 「{ng}」"
                })
                break

        # 7) 構造化出力のパース結果が空
        if output_format in ("json_array", "attributes_kv"):
            if not parsed_result:
                issues.append({
                    "type": "parse_empty",
                    "severity": "high",
                    "detail": f"{output_format} としてパースした結果が空でした。JSON 構文が壊れている可能性があります。"
                })
            elif isinstance(parsed_result, list):
                broken = [str(x) for x in parsed_result if isinstance(x, str) and (x.startswith("{") or x.startswith("[") or '"' in x)]
                if broken:
                    issues.append({
                        "type": "malformed_item",
                        "severity": "medium",
                        "detail": f"JSON の断片がそのまま要素として混入している可能性があります: {broken[0][:60]}"
                    })
        elif output_format == "json_object":
            if isinstance(parsed_result, dict) and "raw" in parsed_result and len(parsed_result) == 1:
                issues.append({
                    "type": "parse_failed",
                    "severity": "high",
                    "detail": "JSON オブジェクトとしてパースできず、生テキストのまま保持されています。"
                })

        return issues

    @staticmethod
    def _detect_repetition(text: str, chunk: int = 18, threshold: int = 3) -> Optional[str]:
        """同じ長さ chunk のフレーズが threshold 回以上出現したら、その断片を返す。"""
        if len(text) < chunk * threshold:
            return None
        seen: Dict[str, int] = {}
        for i in range(0, len(text) - chunk, 4):
            frag = text[i:i + chunk]
            if frag.strip():
                seen[frag] = seen.get(frag, 0) + 1
                if seen[frag] >= threshold:
                    return frag
        return None

    def build_verification_prompt(
        self,
        rule: Dict[str, Any],
        raw_row: Dict[str, Any],
        generated_text: str,
        output_format: str,
        target_field: str,
        detected_issues: List[Dict[str, str]]
    ) -> str:
        """LLM による自己検証・自動修正用のレビュー用プロンプトを生成する。"""
        source_lines = []
        for k, v in raw_row.items():
            if v is None or str(v).strip() == "":
                continue
            source_lines.append(f"- {k}: {v}")
        source_block = "\n".join(source_lines) if source_lines else "(なし)"

        issue_block = "(機械的な検出なし)"
        if detected_issues:
            issue_block = "\n".join(f"- [{i['severity']}] {i['type']}: {i['detail']}" for i in detected_issues)

        format_rules = {
            "text": '"corrected_output" は修正後の本文そのもの (JSON 文字列) を返してください。',
            "json_array": '"corrected_output" は修正後の文字列配列 (JSON 配列) を返してください。',
            "json_object": '"corrected_output" は修正後の JSON オブジェクトを返してください。',
            "attributes_kv": '"corrected_output" は {"キー": "値"} 形式の JSON オブジェクトを返してください。',
        }.get(output_format, '"corrected_output" は修正後の内容を返してください。')

        return f"""あなたは EC 商品カタログの厳格な校閲者（ファクトチェッカー兼日本語エディター）です。
下記の「生成結果」を検証し、問題があれば修正した完成版を出力してください。

# 元の商品データ（唯一の信頼できる一次情報）
{source_block}

# 生成時にモデルへ与えた指示
{rule.get('prompt', '')[:2000]}

# 出力先スキーマ項目
{target_field}（形式: {output_format}）

# 生成結果（検証対象）
\"\"\"
{generated_text}
\"\"\"

# 機械チェックで既に検出された問題
{issue_block}

# 検証チェックリスト
1. **文章の完全性**: 途中で切れている文・段落がないか。文末が句点で正しく終わっているか。見出しだけで本文がない箇所はないか。
2. **日本語の自然さ**: 不自然な言い回し、重複表現、助詞の誤り、体裁の崩れ（記号の乱れ、閉じられていない括弧）がないか。
3. **事実の正確性**: 元の商品データや一般に確認できる事実と矛盾する記述がないか。型番・数値・容量・機能名が正しいか。
4. **ハルシネーション**: 元データにも公開情報にも根拠がない断定（架空の機能・受賞歴・独自仕様・特定販売店名など）が含まれていないか。根拠が無い記述は削除するか、断定を避けた表現に直す。
5. **形式遵守**: 指定された出力形式・文字数・構造を守っているか。余計な前置き（「はい、承知しました」等）やマークダウンのコードフェンスが混入していないか。

# 修正方針
- 途中で切れている文は、元データから確実に言える範囲で自然に完結させる（情報を捏造しない）。
- 根拠のない記述は削除する。削除して短くなることは許容する。
- 問題がなければ元の内容をそのまま "corrected_output" に返す。
- 説明文やコードフェンスを付けず、**JSON のみ**を出力すること。

# 出力 JSON スキーマ
{{
  "verdict": "ok" または "fixed",
  "issues": [
    {{"type": "incomplete_sentence|unnatural_japanese|factual_error|hallucination|format_violation|other",
      "severity": "high|medium|low",
      "detail": "問題の具体的な説明",
      "evidence": "該当箇所の抜粋（40文字以内）"}}
  ],
  "corrected_output": ...
}}
{format_rules}
"""

    def verify_and_fix_sync(
        self,
        rule: Dict[str, Any],
        raw_row: Dict[str, Any],
        generated_text: str,
        parsed_result: Any,
        output_format: str,
        target_field: str,
        detected_issues: List[Dict[str, str]],
        model_name: str,
        project_id: Optional[str] = None,
        location: Optional[str] = None,
        use_google_search: bool = False
    ) -> Dict[str, Any]:
        """
        生成結果を LLM に再レビューさせ、誤り・不自然な文章を自動修正する。
        """
        started = time.time()
        review_prompt = self.build_verification_prompt(
            rule, raw_row, generated_text, output_format, target_field, detected_issues
        )
        client = self.get_client(project_id, location)
        config = types.GenerateContentConfig(
            tools=[{"google_search": {}}] if use_google_search else None,
            temperature=0.0,
            max_output_tokens=VERIFICATION_MAX_TOKENS,
        )

        last_err = None
        for attempt in range(2):
            try:
                response = client.models.generate_content(
                    model=model_name, contents=review_prompt, config=config
                )
                review_text = self._safe_response_text(response)
                review_json = self._extract_json_object(review_text)
                if review_json is None:
                    raise ValueError("検証レスポンスを JSON として解釈できませんでした。")

                verdict = str(review_json.get("verdict", "ok")).lower()
                llm_issues = review_json.get("issues") or []
                if not isinstance(llm_issues, list):
                    llm_issues = []
                corrected_raw = review_json.get("corrected_output", None)

                corrected_text = ""
                if corrected_raw is not None:
                    if isinstance(corrected_raw, str):
                        corrected_text = corrected_raw
                    else:
                        corrected_text = json.dumps(corrected_raw, ensure_ascii=False)

                return {
                    "status": "success",
                    "verdict": verdict,
                    "llm_issues": llm_issues,
                    "corrected_text": corrected_text,
                    "review_prompt": review_prompt,
                    "review_raw_response": review_text,
                    "elapsed_seconds": round(time.time() - started, 2),
                }
            except Exception as e:
                last_err = str(e)
                logger.warning("検証パス %d 回目に失敗: %s", attempt + 1, last_err)
                time.sleep(1.0 * (attempt + 1))

        return {
            "status": "error",
            "verdict": "error",
            "llm_issues": [],
            "corrected_text": "",
            "review_prompt": review_prompt,
            "review_raw_response": "",
            "error": last_err or "Unknown verification error",
            "elapsed_seconds": round(time.time() - started, 2),
        }

    @staticmethod
    def _safe_response_text(response: Any) -> str:
        try:
            return response.text or ""
        except Exception:
            pass
        try:
            parts = response.candidates[0].content.parts or []
            return "".join(getattr(p, "text", "") or "" for p in parts)
        except Exception:
            return ""

    @staticmethod
    def _get_finish_reason(response: Any) -> str:
        try:
            fr = response.candidates[0].finish_reason
            return getattr(fr, "name", None) or str(fr)
        except Exception:
            return ""

    @staticmethod
    def _extract_json_object(text: str) -> Optional[Dict[str, Any]]:
        if not text:
            return None
        cleaned = re.sub(r"^```(?:json)?\s*", "", text.strip(), flags=re.IGNORECASE)
        cleaned = re.sub(r"\s*```$", "", cleaned).strip()
        try:
            obj = json.loads(cleaned)
            return obj if isinstance(obj, dict) else None
        except Exception:
            pass
        match = re.search(r"\{[\s\S]*\}", cleaned)
        if match:
            try:
                obj = json.loads(match.group(0))
                return obj if isinstance(obj, dict) else None
            except Exception:
                return None
        return None

    def execute_rule_sync(
        self,
        rule: Dict[str, Any],
        raw_row: Dict[str, Any],
        mapped_row: Dict[str, Any],
        model_name: str = "gemini-3.8-flash",
        project_id: Optional[str] = None,
        location: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Enrichment ルールを 1 件同期実行する。

        処理フロー:
          1. 生成: 出力がトークン上限で切れた場合は上限を拡張して自動再生成
          2. 機械チェック: 文末の途切れ・括弧不整合・空出力・パース失敗などを検出
          3. AI 検証: 別プロンプトで校閲させ、事実誤り・不自然な日本語・途中切れを自動修正
        """
        prompt_template = rule.get("prompt", "")
        source_fields = rule.get("source_fields", [])
        use_google_search = bool(rule.get("use_google_search", True))
        output_format = rule.get("output_format", "json_array")
        target_field = rule.get("target_field", "tags")
        enable_verification = bool(rule.get("enable_verification", True))
        verification_use_search = bool(rule.get("verification_use_google_search", False))

        rendered_prompt = self.render_prompt(prompt_template, raw_row, mapped_row, source_fields)

        client = self.get_client(project_id, location)
        tools = [{"google_search": {}}] if use_google_search else []

        start_time = time.time()
        last_err = None
        regeneration_count = 0
        raw_text = ""
        parsed_result: Any = None
        finish_reason = ""
        search_queries: List[str] = []
        sources: List[Dict[str, str]] = []
        generated = False

        for budget_index, max_tokens in enumerate(MAX_OUTPUT_TOKEN_LADDER):
            config = types.GenerateContentConfig(
                tools=tools if tools else None,
                temperature=0.2,
                max_output_tokens=max_tokens,
            )
            for attempt in range(3):
                try:
                    response = client.models.generate_content(
                        model=model_name,
                        contents=rendered_prompt,
                        config=config
                    )
                    raw_text = self._safe_response_text(response)
                    finish_reason = self._get_finish_reason(response)

                    # Extract search grounding info
                    search_queries = []
                    sources = []
                    if response.candidates and len(response.candidates) > 0:
                        gm = getattr(response.candidates[0], "grounding_metadata", None)
                        if gm:
                            if getattr(gm, "web_search_queries", None):
                                search_queries = list(gm.web_search_queries)
                            chunks = getattr(gm, "grounding_chunks", None)
                            if chunks:
                                for ch in chunks:
                                    web = getattr(ch, "web", None)
                                    if web:
                                        sources.append({
                                            "title": getattr(web, "title", ""),
                                            "uri": getattr(web, "uri", "")
                                        })

                    parsed_result = self.parse_llm_output(raw_text, output_format, target_field)
                    generated = True
                    last_err = None
                    break
                except Exception as e:
                    last_err = str(e)
                    logger.warning("Gemini API attempt %d failed: %s", attempt + 1, last_err)
                    time.sleep(1.5 * (attempt + 1))

            if not generated:
                break

            # トークン上限で切れている場合のみ、上限を引き上げて再生成
            truncated = bool(finish_reason and finish_reason.upper() in ("MAX_TOKENS", "LENGTH"))
            if truncated and budget_index < len(MAX_OUTPUT_TOKEN_LADDER) - 1:
                regeneration_count += 1
                logger.info(
                    "出力がトークン上限 (%s) で切れたため %s トークンで再生成します",
                    max_tokens, MAX_OUTPUT_TOKEN_LADDER[budget_index + 1]
                )
                generated = False
                continue
            break

        if not generated:
            return {
                "status": "error",
                "rule_id": rule.get("id"),
                "rule_name": rule.get("name"),
                "target_field": target_field,
                "error": last_err or "Unknown error",
                "rendered_prompt": rendered_prompt,
                "parsed_result": None,
                "search_queries": [],
                "sources": [],
                "elapsed_seconds": round(time.time() - start_time, 2)
            }

        # --- Step 2: 機械チェック ------------------------------------------
        pre_issues = self.detect_output_issues(raw_text, parsed_result, output_format, finish_reason)

        # --- Step 3: AI 検証・自動修正 --------------------------------------
        verification: Dict[str, Any] = {
            "enabled": enable_verification,
            "performed": False,
            "verdict": "skipped",
            "pre_issues": pre_issues,
            "post_issues": pre_issues,
            "llm_issues": [],
            "changed": False,
            "original_response": raw_text,
            "corrected_response": "",
            "regeneration_count": regeneration_count,
            "finish_reason": finish_reason,
            "elapsed_seconds": 0.0,
        }

        if enable_verification and raw_text.strip():
            review = self.verify_and_fix_sync(
                rule=rule,
                raw_row=raw_row,
                generated_text=raw_text,
                parsed_result=parsed_result,
                output_format=output_format,
                target_field=target_field,
                detected_issues=pre_issues,
                model_name=model_name,
                project_id=project_id,
                location=location,
                use_google_search=verification_use_search,
            )
            verification["performed"] = True
            verification["verdict"] = review.get("verdict", "error")
            verification["llm_issues"] = review.get("llm_issues", [])
            verification["review_prompt"] = review.get("review_prompt", "")
            verification["elapsed_seconds"] = review.get("elapsed_seconds", 0.0)
            if review.get("status") == "error":
                verification["error"] = review.get("error", "")

            corrected_text = (review.get("corrected_text") or "").strip()
            if corrected_text:
                corrected_parsed = self.parse_llm_output(corrected_text, output_format, target_field)
                # 修正後に内容が空になってしまう場合は採用しない（デグレ防止）
                if not corrected_parsed:
                    verification["verdict"] = "rejected"
                    verification["error"] = "検証後の出力が空だったため、修正を適用しませんでした。"
                    verification["post_issues"] = self.detect_output_issues(
                        raw_text, parsed_result, output_format, ""
                    )
                else:
                    # NOTE: 生テキストの比較だと JSON の再シリアライズ（空白・改行の違い）だけで
                    #       「修正あり」と誤判定されるため、パース結果どうしを意味的に比較する。
                    semantically_changed = corrected_parsed != parsed_result
                    verification["changed"] = semantically_changed
                    if semantically_changed:
                        verification["corrected_response"] = corrected_text
                    raw_text = corrected_text
                    parsed_result = corrected_parsed
                    verification["post_issues"] = self.detect_output_issues(
                        corrected_text, corrected_parsed, output_format, ""
                    )
            else:
                verification["post_issues"] = self.detect_output_issues(
                    raw_text, parsed_result, output_format, ""
                )


        verification["issue_count_before"] = len(verification["pre_issues"]) + 0
        verification["issue_count_after"] = len(verification["post_issues"])
        verification["quality_ok"] = (
            len([i for i in verification["post_issues"] if i.get("severity") == "high"]) == 0
        )

        return {
            "status": "success",
            "rule_id": rule.get("id"),
            "rule_name": rule.get("name"),
            "target_field": target_field,
            "output_format": output_format,
            "use_google_search": use_google_search,
            "rendered_prompt": rendered_prompt,
            "raw_response": raw_text,
            "original_response": verification["original_response"],
            "parsed_result": parsed_result,
            "search_queries": search_queries,
            "sources": sources,
            "verification": verification,
            "elapsed_seconds": round(time.time() - start_time, 2)
        }



enricher_engine = EnrichmentEngine()
