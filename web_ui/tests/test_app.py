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
