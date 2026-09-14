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

    def execute_rule_sync(
        self,
        rule: Dict[str, Any],
        raw_row: Dict[str, Any],
        mapped_row: Dict[str, Any],
        model_name: str = "gemini-2.5-flash",
        project_id: Optional[str] = None,
        location: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Executes a single Enrichment Rule synchronously and returns detailed trace + parsed result.
        """
        prompt_template = rule.get("prompt", "")
        source_fields = rule.get("source_fields", [])
        use_google_search = bool(rule.get("use_google_search", True))
        output_format = rule.get("output_format", "json_array")
        target_field = rule.get("target_field", "tags")

        rendered_prompt = self.render_prompt(prompt_template, raw_row, mapped_row, source_fields)

        client = self.get_client(project_id, location)
        tools = [{"google_search": {}}] if use_google_search else []
        config = types.GenerateContentConfig(
            tools=tools if tools else None,
            temperature=0.2,
            max_output_tokens=4096,
        )

        start_time = time.time()
        last_err = None
        for attempt in range(3):
            try:
                response = client.models.generate_content(
                    model=model_name,
                    contents=rendered_prompt,
                    config=config
                )
                elapsed = round(time.time() - start_time, 2)
                raw_text = response.text or ""

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
                return {
                    "status": "success",
                    "rule_id": rule.get("id"),
                    "rule_name": rule.get("name"),
                    "target_field": target_field,
                    "output_format": output_format,
                    "use_google_search": use_google_search,
                    "rendered_prompt": rendered_prompt,
                    "raw_response": raw_text,
                    "parsed_result": parsed_result,
                    "search_queries": search_queries,
                    "sources": sources,
                    "elapsed_seconds": elapsed
                }
            except Exception as e:
                last_err = str(e)
                logger.warning("Gemini API attempt %d failed: %s", attempt + 1, last_err)
                time.sleep(1.5 * (attempt + 1))

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


enricher_engine = EnrichmentEngine()
