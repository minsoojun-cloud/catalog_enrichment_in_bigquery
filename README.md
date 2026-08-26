# E-Commerce Product Catalog Enrichment with Gemini in BigQuery & Vertex AI

A production-ready pipeline for enriching large-scale e-commerce product catalogs with AI-generated search tags using **Google Cloud Vertex AI (Gemini)** and **BigQuery**.

Designed specifically for **Google Cloud Retail Search (AI Commerce Search / Vertex AI Search for Retail)** to maximize search recall across Japanese language variations (Kanji, Hiragana, Katakana, English / Romaji, colloquialisms, brand names, and phonetic variations).

---

## Architecture Overview

This repository provides two implementation paths based on catalog size:

```mermaid
flowchart TD
    subgraph Path 1: Direct BigQuery ML (Up to ~50K items)
        A1["BigQuery Catalog Table<br/>(id, title, attributes)"] -->|"ML.GENERATE_TEXT<br/>(Remote Model)"| B1["Gemini Flash Inference"]
        B1 -->|"Direct UPDATE"| A1
    end

    subgraph Path 2: Vertex AI Batch Prediction (Large scale: 50K ~ Millions of items)
        A2["BigQuery Catalog Table"] -->|"Step 1: EXPORT DATA (JSONL)"| B2["Cloud Storage (GCS)"]
        B2 -->|"Step 2: Vertex AI Batch Prediction<br/>(50% Cost Discount / No RPM Limit)"| C2["Gemini Flash Batch Inference"]
        C2 -->|"Step 3: bq load --replace"| D2["BigQuery Temp Table"]
        D2 -->|"Step 4: Fast Bulk UPDATE<br/>(Deduplicated via QUALIFY)"| A2
    end
```

---

## Key Features

- **Search Recall Optimization**: Generates 2–10 high-precision search tags per product covering Kanji (漢字), Hiragana (ひらがな), Katakana (カタカナ), English/Romaji (英語表記), voiced/unvoiced variations (連濁), and colloquial terminology.
- **50% Cost Reduction & No Quota Limits**: Leverages Vertex AI Batch Prediction to slash token pricing by 50% while bypassing online API rate limits (RPM/TPM 429 errors).
- **Schema Preservation**: Safely updates or inserts the `'tags'` attribute while preserving all existing custom attributes in the Retail API `ARRAY<STRUCT<key STRING, value STRUCT<...>>>` format.
- **Production Resilience**:
  - **Idempotent**: Re-runnable at any time without reprocessing already tagged items (`WHERE attributes IS NULL OR NOT EXISTS(...)`).
  - **Deduplicated**: Prevents `UPDATE/MERGE must match at most one source row` errors using window functions (`QUALIFY ROW_NUMBER() = 1`).
  - **Real-time Cost Tracking**: Includes BigQuery SQL to audit token usage and dollar expenses instantly from `usageMetadata`.

---

## Repository Structure

| File | Description |
|---|---|
| [`vertex_ai_batch_prediction_guide_ja.md`](vertex_ai_batch_prediction_guide_ja.md) | **Comprehensive Japanese Implementation Guide** detailing the full batch prediction lifecycle, parameter setup, and troubleshooting. |
| [`update_enrichment_query.sql`](update_enrichment_query.sql) | SQL script for direct in-place catalog `UPDATE` using BigQuery ML (`ML.GENERATE_TEXT`). |
| [`test_enrichment_query.sql`](test_enrichment_query.sql) | DDL for creating the Gemini Remote Model and a preview `SELECT` query for test validation. |
| [`submit_batch_job.py`](submit_batch_job.py) | Ready-to-run Python script for submitting Vertex AI Batch Prediction jobs via the Vertex AI SDK. |
| [`prompt.txt`](prompt.txt) | Tuned system prompt designed for e-commerce search indexing and Japanese morphological variants. |
| [`AI_Commerce_Search_Bigquery_schema.json`](AI_Commerce_Search_Bigquery_schema.json) | Standard BigQuery schema definition for Google Cloud Retail Search catalog ingestion. |
| [`data_mapping.md`](data_mapping.md) | Field mapping reference between e-commerce raw catalog attributes and Retail Search schema types. |

---

## Quickstart: Large-Scale Batch Pipeline

### Prerequisites

- A Google Cloud Project with the following APIs enabled:
  - BigQuery API (`bigquery.googleapis.com`)
  - Vertex AI API (`aiplatform.googleapis.com`)
  - Cloud Storage API (`storage.googleapis.com`)
- A Cloud Storage bucket for staging batch inputs and outputs.
- A BigQuery product table matching the Google Cloud Retail API schema.

### Configuration Parameters

Adjust the parameters below to match your GCP environment:

| Parameter | Example Value | Description |
|---|---|---|
| `PROJECT_ID` | `retail-search-jp-demo-minsoo` | Google Cloud Project ID |
| `DATASET_NAME` | `retail_search` | Target BigQuery dataset |
| `TABLE_NAME` | `d-vais-c` | Target catalog table |
| `BUCKET_NAME` | `catalog_enrichment_bigquery` | Cloud Storage bucket for batch processing |
| `LOCATION` | `us-central1` | Vertex AI region (`us-central1` or `us`) |
| `MODEL_NAME` | `gemini-2.5-flash` | Gemini model for batch prediction |

---

### Step 1: Export Untagged Products to Cloud Storage

Run the following query in BigQuery to generate formatted JSONL files in Cloud Storage. This wraps the request inside the official Vertex AI `request` object and embeds the product ID for correlation.

```sql
DECLARE bucket_name STRING DEFAULT 'catalog_enrichment_bigquery';

EXPORT DATA OPTIONS(
  uri=CONCAT('gs://', bucket_name, '/batch_input/products_*.jsonl'),
  format='JSON',
  overwrite=true
) AS
SELECT
  STRUCT(
    [
      STRUCT(
        'user' AS role,
        [
          STRUCT(
            CONCAT(
              """# 役割: Eコマース検索の専門家
# 目的: 日本のECユーザーが検索で使用するタグ（漢字、英語表記、ひらがな、カタカナ等）を網羅したJSONを出力
# ルール: 表記揺れ、連濁、俗称、英字を網羅し、2〜10個のタグを生成
# 出力形式: 必ず {"tags": ["タグ1", "タグ2", ...]} のJSON形式のみ出力
# 入力商品情報
- 商品ID: """, id, """
- タイトル: """, COALESCE(title, '')
            ) AS text
          )
        ] AS parts
      )
    ] AS contents,
    STRUCT(0.2 AS temperature, 2048 AS maxOutputTokens) AS generationConfig
  ) AS request
FROM
  `retail-search-jp-demo-minsoo.retail_search.d-vais-c`
WHERE
  title IS NOT NULL
  AND (attributes IS NULL OR NOT EXISTS(SELECT 1 FROM UNNEST(attributes) WHERE key = 'tags'));
```

---

### Step 2: Submit Vertex AI Batch Prediction Job

#### Option A: Python Script
Run [`submit_batch_job.py`](submit_batch_job.py):
```bash
python3 submit_batch_job.py
```

#### Option B: REST API (`curl`)
```bash
PROJECT_ID="retail-search-jp-demo-minsoo"
LOCATION="us-central1"
BUCKET_NAME="catalog_enrichment_bigquery"

curl -X POST \
  -H "Authorization: Bearer $(gcloud auth print-access-token)" \
  -H "Content-Type: application/json; charset=utf-8" \
  "https://${LOCATION}-aiplatform.googleapis.com/v1/projects/${PROJECT_ID}/locations/${LOCATION}/batchPredictionJobs" \
  -d "{
    \"displayName\": \"catalog-enrichment-batch\",
    \"model\": \"publishers/google/models/gemini-2.5-flash\",
    \"inputConfig\": {
      \"instancesFormat\": \"jsonl\",
      \"gcsSource\": {
        \"uris\": [\"gs://${BUCKET_NAME}/batch_input/products_*.jsonl\"]
      }
    },
    \"outputConfig\": {
      \"predictionsFormat\": \"jsonl\",
      \"gcsDestination\": {
        \"outputUriPrefix\": \"gs://${BUCKET_NAME}/batch_output/\"
      }
    }
  }"
```

#### Option C: Google Cloud Console
1. Navigate to **Vertex AI > Batch Predictions**.
2. Click **Create**, select the Gemini model (e.g. `gemini-2.5-flash`).
3. Set input path to `gs://catalog_enrichment_bigquery/batch_input/products_*.jsonl`.
4. Set output path to `gs://catalog_enrichment_bigquery/batch_output/` and submit.

---

### Step 3: Load Predictions into BigQuery Temp Table

Once the batch job succeeds, load the output into a temporary staging table in BigQuery:

```bash
BUCKET_NAME="catalog_enrichment_bigquery"

# Find the latest output file path generated by Vertex AI
OUTPUT_URI=$(gcloud storage ls "gs://${BUCKET_NAME}/batch_output/**/predictions*.jsonl" | tail -n 1)
echo "Loading: ${OUTPUT_URI}"

# Load into BigQuery with --replace=true to avoid duplicate rows
bq load \
  --project_id=retail-search-jp-demo-minsoo \
  --replace=true \
  --source_format=NEWLINE_DELIMITED_JSON \
  --autodetect \
  retail-search-jp-demo-minsoo:retail_search.temp_batch_prediction_results \
  "${OUTPUT_URI}"
```

---

### Step 4: Bulk UPDATE Catalog Attributes

Apply the generated tags back into the production catalog table. This query safely deduplicates rows using `QUALIFY`, parses the JSON array, and updates the `attributes` RECORD in seconds:

```sql
UPDATE `retail-search-jp-demo-minsoo.retail_search.d-vais-c` AS target
SET attributes = ARRAY_CONCAT(
  -- Retain all existing attributes other than 'tags'
  ARRAY(
    SELECT AS STRUCT a.*
    FROM UNNEST(COALESCE(target.attributes, [])) AS a
    WHERE a.key != 'tags'
  ),
  -- Append newly generated tags attribute
  [STRUCT(
    'tags' AS key,
    STRUCT(
      source.generated_tags AS text,
      CAST([] AS ARRAY<FLOAT64>) AS numbers
    ) AS value
  )]
)
FROM (
  SELECT
    -- Extract product ID embedded in the request prompt
    REGEXP_EXTRACT(
      request.contents[SAFE_OFFSET(0)].parts[SAFE_OFFSET(0)].text,
      r'- 商品ID:\s*([^\n\r]+)'
    ) AS id,
    -- Parse generated tags array
    JSON_EXTRACT_STRING_ARRAY(
      TRIM(REGEXP_REPLACE(response.candidates[SAFE_OFFSET(0)].content.parts[SAFE_OFFSET(0)].text, r'^```(?:json)?|```$', '')),
      '$.tags'
    ) AS generated_tags
  FROM
    `retail-search-jp-demo-minsoo.retail_search.temp_batch_prediction_results`
  WHERE
    response.candidates[SAFE_OFFSET(0)].content.parts[SAFE_OFFSET(0)].text IS NOT NULL
  -- Ensure unique source row per product ID
  QUALIFY ROW_NUMBER() OVER(PARTITION BY id ORDER BY processed_time DESC) = 1
) AS source
WHERE
  target.id = source.id
  AND source.generated_tags IS NOT NULL 
  AND ARRAY_LENGTH(source.generated_tags) > 0;
```

---

### Step 5: Verify Results

Inspect the updated attributes in BigQuery:

```sql
SELECT 
  id, 
  title, 
  attributes 
FROM 
  `retail-search-jp-demo-minsoo.retail_search.d-vais-c`
WHERE 
  ARRAY_LENGTH(attributes) > 0
LIMIT 5;
```

---

## Cost & Token Audit Query

Estimate exact token usage and billing costs directly from the prediction output before the monthly invoice is compiled:

```sql
SELECT
  COUNT(*) AS total_processed_items,
  SUM(response.usageMetadata.promptTokenCount) AS total_input_tokens,
  SUM(response.usageMetadata.candidatesTokenCount) AS total_output_tokens,
  SUM(response.usageMetadata.totalTokenCount) AS grand_total_tokens,
  
  -- Gemini 2.5 Flash Batch Prediction pricing (50% discount):
  -- Input: $0.0375 / 1M tokens, Output: $0.15 / 1M tokens
  ROUND(
    (SUM(response.usageMetadata.promptTokenCount) / 1000000.0 * 0.0375) +
    (SUM(response.usageMetadata.candidatesTokenCount) / 1000000.0 * 0.15),
    4
  ) AS estimated_cost_usd
FROM
  `retail-search-jp-demo-minsoo.retail_search.temp_batch_prediction_results`;
```

*Typical benchmark: Processing 1,000 product items consumes ~350K tokens, resulting in approximately **$0.03 ~ $0.05 USD**.*

---

## Troubleshooting Guide

| Issue / Error | Cause | Resolution |
|---|---|---|
| `The lines in the specified input JSONL file must contain the "request" property.` | Root JSON object was missing the `"request"` property. | Wrap prompt contents and config in `STRUCT(...) AS request` in Step 1 SQL. |
| `Not found: Uris gs://.../prediction.results-*.jsonl` | Output directory contains dynamic timestamp folder; `bq load` does not support wildcards in folder paths. | Use `OUTPUT_URI=$(gcloud storage ls ... \| tail -n 1)` to fetch the exact file path. |
| `UPDATE/MERGE must match at most one source row for each target row` | `bq load` was run multiple times without `--replace`, creating duplicate rows for the same product ID. | Use `QUALIFY ROW_NUMBER() OVER(PARTITION BY id ...) = 1` in Step 4, and pass `--replace=true` in `bq load`. |
| Tags appear missing in raw JSONL | In raw JSONL, tags are nested and escaped under `response.candidates[0].content.parts[0].text`. | Normal behavior. Extract using BigQuery's `JSON_EXTRACT_STRING_ARRAY` in Step 4. |

---

## References

- [Vertex AI Batch Prediction Documentation](https://cloud.google.com/vertex-ai/generative-ai/docs/multimodal/batch-prediction-gemini)
- [Google Cloud Retail API Catalog Attributes Specification](https://cloud.google.com/retail/docs/catalog)
- [Japanese Implementation Guide (日本語詳細ガイド)](vertex_ai_batch_prediction_guide_ja.md)
