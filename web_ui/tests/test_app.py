import os
import json
import pytest
from fastapi.testclient import TestClient

os.environ.pop("GOOGLE_API_CERTIFICATE_CONFIG", None)
os.environ["GOOGLE_API_USE_CLIENT_CERTIFICATE"] = "false"

from app.main import app
from app.schema_manager import auto_suggest_mapping, get_mappable_schema_fields
from app.transformer import (
    build_base_mapped_row,
    apply_enrichment_to_extracted,
    format_to_bigquery_schema,
    validate_bigquery_row
)
from app.enricher import enricher_engine

client = TestClient(app)


def test_metadata_endpoint():
    res = client.get("/api/metadata")
    assert res.status_code == 200
    data = res.json()
    assert "raw_bigquery_schema" in data
    assert len(data["mappable_fields"]) >= 30
    assert len(data["enrichment_presets"]) >= 5


def test_sample_endpoint_and_auto_mapping():
    res = client.post("/api/sample")
    assert res.status_code == 200
    data = res.json()
    assert data["total_rows"] == 5
    assert "p_cd" in data["columns"]
    mapping = data["auto_mapping"]
    assert mapping["id"]["source_column"] == "p_cd"
    assert mapping["title"]["source_column"] == "product_name"
    assert mapping["brands"]["source_column"] == "maker"


def test_transformer_and_enrichment_merging():
    raw_row = {
        "p_cd": "00080997740",
        "product_name": "ダイキン エアコン ATE22ASE5-WS",
        "maker": "ダイキン",
        "intax_price": "99800",
        "stock_qty": "196"
    }
    mapping_config = auto_suggest_mapping(list(raw_row.keys()))
    base_extracted = build_base_mapped_row(raw_row, mapping_config)

    enrichment_outputs = [
        {
            "status": "success",
            "target_field": "tags",
            "parsed_result": ["ダイキン", "エアコン", "6畳", "省エネ"]
        },
        {
            "status": "success",
            "target_field": "attributes.tags",
            "parsed_result": ["エアコン", "インバーター"]
        },
        {
            "status": "success",
            "target_field": "description",
            "parsed_result": "省エネ性能に優れた6畳用ルームエアコンです。"
        }
    ]

    merged = apply_enrichment_to_extracted(base_extracted, enrichment_outputs)
    bq_row = format_to_bigquery_schema(merged)

    assert bq_row["id"] == "00080997740"
    assert bq_row["title"] == "ダイキン エアコン ATE22ASE5-WS"
    assert "ダイキン" in bq_row["tags"]
    assert bq_row["description"] == "省エネ性能に優れた6畳用ルームエアコンです。"
    assert bq_row["priceInfo"]["price"] == 99800.0
    assert bq_row["availableQuantity"] == 196

    # Check attributes[key='tags']
    tag_attr = next((a for a in bq_row["attributes"] if a["key"] == "tags"), None)
    assert tag_attr is not None
    assert "インバーター" in tag_attr["value"]["text"]

    val = validate_bigquery_row(bq_row)
    assert val["valid"] is True


def test_prompt_rendering():
    template = "상품명: {title}, 브랜드: {brands}"
    raw_row = {"p_cd": "123"}
    mapped_row = {"title": "테스트 상품", "brands": ["브랜드A"]}
    rendered = enricher_engine.render_prompt(template, raw_row, mapped_row, ["title", "brands", "p_cd"])
    assert "상품명: 테스트 상품" in rendered
    assert "브랜드: 브랜드A" in rendered
    assert "p_cd: 123" in rendered


# ============================================================================
# 出力品質検証 (Quality Verification) のテスト
# ============================================================================

TRUNCATED_DESCRIPTION = (
    "【清潔性と高耐久を両立した限定モデル】日立 白くまくん Dシリーズ 6畳用。"
    "凍結洗浄Light とカビバスターをW搭載し、内部の汚れやカビを抑制します。"
    "● カビの原因を残さない「内部送風乾燥運転」 冷房や除湿運転の停止後、自動で約2時間の送風運転を行い、室"
)


def test_detect_truncated_description():
    """途中で切れた説明文を機械チェックで検出できること。"""
    issues = enricher_engine.detect_output_issues(
        TRUNCATED_DESCRIPTION, TRUNCATED_DESCRIPTION, "text", "MAX_TOKENS"
    )
    types = {i["type"] for i in issues}
    assert "truncated" in types
    assert "incomplete_sentence" in types
    assert all(i["severity"] == "high" for i in issues)


def test_detect_clean_description_has_no_issue():
    """正常に完結した文章では問題を検出しないこと。"""
    text = "ダイキンのエアコンです。ストリーマ搭載で内部を清潔に保ちます。"
    assert enricher_engine.detect_output_issues(text, text, "text", "STOP") == []


def test_detect_unresolved_placeholder_and_empty_array():
    leftover = "商品名は {product_name} です。"
    types = {i["type"] for i in enricher_engine.detect_output_issues(leftover, leftover, "text", "STOP")}
    assert "unresolved_placeholder" in types

    types = {i["type"] for i in enricher_engine.detect_output_issues("[]", [], "json_array", "STOP")}
    assert "parse_empty" in types


def test_detect_unbalanced_bracket():
    text = "この商品は「高耐久モデルです。長くお使いいただけます。"
    types = {i["type"] for i in enricher_engine.detect_output_issues(text, text, "text", "STOP")}
    assert "unbalanced_bracket" in types


def test_verification_prompt_contains_source_and_issues():
    rule = {"prompt": "商品説明を生成してください。", "name": "desc"}
    raw_row = {"product_name": "日立 白くまくん", "maker": "日立"}
    issues = enricher_engine.detect_output_issues(
        TRUNCATED_DESCRIPTION, TRUNCATED_DESCRIPTION, "text", "MAX_TOKENS"
    )
    prompt = enricher_engine.build_verification_prompt(
        rule, raw_row, TRUNCATED_DESCRIPTION, "text", "description", issues
    )
    assert "日立 白くまくん" in prompt
    assert "incomplete_sentence" in prompt
    assert "corrected_output" in prompt
    assert "ハルシネーション" in prompt


def test_extract_json_object_from_fenced_review_response():
    fenced = '```json\n{"verdict": "fixed", "issues": [], "corrected_output": "完結した文章です。"}\n```'
    parsed = enricher_engine._extract_json_object(fenced)
    assert parsed["verdict"] == "fixed"
    assert parsed["corrected_output"] == "完結した文章です。"


def test_start_job_request_defaults_verification_on():
    from app.main import StartJobRequest
    req = StartJobRequest(dataset_id="d", mapping_config={}, enrichment_rules=[])
    assert req.enable_verification is True
