import vertexai
from vertexai.preview.batch_prediction import BatchPredictionJob

# 1. 設定情報
PROJECT_ID = "retail-search-jp-demo-minsoo"
LOCATION = "us-central1" # または us
BUCKET_NAME = "catalog_enrichment_bigquery"

# 2. Vertex AIの初期化
vertexai.init(project=PROJECT_ID, location=LOCATION)

# 3. モデル指定
# Vertex AI Batch Predictionでサポートされているモデルを指定します
MODEL_NAME = "gemini-2.5-flash"

print(f"Submitting batch prediction job using {MODEL_NAME}...")

# 4. バッチ予測ジョブの投入
job = BatchPredictionJob.submit(
    source_model=MODEL_NAME,
    input_dataset=f"gs://{BUCKET_NAME}/batch_input/products_*.jsonl",
    output_uri_prefix=f"gs://{BUCKET_NAME}/batch_output/",
    job_display_name="catalog-enrichment-batch",
)

print("Job submitted successfully!")
print(f"Resource Name: {job.resource_name}")
print(f"State: {job.state}")
print(f"View progress in Console: https://console.cloud.google.com/vertex-ai/batch-predictions?project={PROJECT_ID}")
