import os
import io
import csv
import json
import uuid
import time
import asyncio
import logging
from typing import Dict, Any, List, Optional
from pathlib import Path

# Disable mTLS client cert config before any google libraries are imported
os.environ.pop("GOOGLE_API_CERTIFICATE_CONFIG", None)
os.environ["GOOGLE_API_USE_CLIENT_CERTIFICATE"] = "false"
os.environ["CLOUDSDK_CONTEXT_AWARE_USE_CLIENT_CERTIFICATE"] = "false"

from fastapi import FastAPI, UploadFile, File, HTTPException, Body, Request
from fastapi.responses import HTMLResponse, StreamingResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from app.config import settings, BASE_DIR
from app.schema_manager import (
    load_bigquery_schema,
    get_mappable_schema_fields,
    auto_suggest_mapping,
    get_enrichment_presets
)
from app.sample_data import get_sample_data
from app.enricher import enricher_engine
from app.transformer import (
    build_base_mapped_row,
    apply_enrichment_to_extracted,
    format_to_bigquery_schema,
    validate_bigquery_row,
    build_enrichment_diff
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("main")

app = FastAPI(
    title="AI Commerce Search Catalog Mapper & Enricher",
    description="CSV/JSONL 商品カタログマッピング ＆ Google Search + Gemini マルチルール Enrichment ツール (AI Commerce Search BigQuery Schema対応)",
    version="1.0.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

STATIC_DIR = BASE_DIR / "static"
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

DATASETS: Dict[str, Dict[str, Any]] = {}
JOBS: Dict[str, Dict[str, Any]] = {}


class TestRuleRequest(BaseModel):
    dataset_id: Optional[str] = None
    row_index: int = 0
    sample_row: Optional[Dict[str, Any]] = None
    mapping_config: Dict[str, Dict[str, Any]] = {}
    rule: Dict[str, Any]
    model_name: str = "gemini-3.8-flash"
    project_id: Optional[str] = None
    location: Optional[str] = None


class StartJobRequest(BaseModel):
    dataset_id: str
    mapping_config: Dict[str, Dict[str, Any]]
    enrichment_rules: List[Dict[str, Any]]
    row_limit: Optional[int] = None
    concurrency: int = 5
    model_name: str = "gemini-3.8-flash"
    project_id: Optional[str] = None
    location: Optional[str] = None
    enable_verification: bool = True


class BigQueryLoadRequest(BaseModel):
    job_id: str
    project_id: str = "retail-search-jp-demo-minsoo"
    dataset_id: str = "retail_search"
    table_id: str = "d-vais-c"
    write_disposition: str = "WRITE_APPEND"


def decode_file_bytes(content: bytes) -> str:
    for enc in ["utf-8-sig", "utf-8", "shift_jis", "cp932", "euc-jp", "cp949", "latin1"]:
        try:
            return content.decode(enc)
        except UnicodeDecodeError:
            continue
    return content.decode("utf-8", errors="replace")


def parse_uploaded_file(filename: str, content: bytes) -> Dict[str, Any]:
    text = decode_file_bytes(content)
    rows = []
    columns = []

    if filename.lower().endswith(".jsonl") or filename.lower().endswith(".ndjson"):
        for line in text.splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
                if isinstance(obj, dict):
                    rows.append(obj)
                    for k in obj.keys():
                        if k not in columns:
                            columns.append(k)
            except Exception as e:
                logger.warning("Failed to parse JSONL line: %s", e)
    elif filename.lower().endswith(".json"):
        try:
            data = json.loads(text)
            if isinstance(data, list):
                for obj in data:
                    if isinstance(obj, dict):
                        rows.append(obj)
                        for k in obj.keys():
                            if k not in columns:
                                columns.append(k)
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"無効なJSONフォーマットです: {e}")
    else:
        sample_lines = text[:4096]
        dialect = csv.excel
        try:
            sniffer = csv.Sniffer()
            dialect = sniffer.sniff(sample_lines, delimiters=",\t;|")
        except Exception:
            pass

        reader = csv.DictReader(io.StringIO(text), dialect=dialect)
        columns = list(reader.fieldnames or [])
        for r in reader:
            rows.append(dict(r))

    if not rows:
        raise HTTPException(status_code=400, detail="データ行(Row)が見つかりません。有効なCSVまたはJSONLファイルであるか確認してください。")

    dataset_id = f"ds_{uuid.uuid4().hex[:8]}"
    dataset_info = {
        "dataset_id": dataset_id,
        "filename": filename,
        "columns": columns,
        "rows": rows,
        "total_rows": len(rows),
        "created_at": time.time()
    }
    DATASETS[dataset_id] = dataset_info
    return dataset_info


@app.get("/", response_class=HTMLResponse)
async def serve_index():
    index_path = STATIC_DIR / "index.html"
    if not index_path.exists():
        return HTMLResponse("<h1>index.html not found</h1>", status_code=404)
    return HTMLResponse(index_path.read_text(encoding="utf-8"))


@app.get("/api/health")
@app.get("/healthz")
async def healthz():
    """
    Cloud Run / ロードバランサ用のヘルスチェックエンドポイント。
    外部 API を呼ばずに即座に応答する（起動確認とコンテナ内の設定解決の検証用）。

    NOTE: Cloud Run では Google Front End (GFE) が "/healthz" を予約パスとして
          横取りし、コンテナまで到達せず GFE の 404 が返る。そのため本番では
          "/api/health" を使用すること。"/healthz" はローカル実行用に残している。
    """
    from app.config import SCHEMA_FILE_PATH

    return {
        "status": "ok",
        "project_id": settings.project_id,
        "location": settings.location,
        "default_model": settings.default_model,
        "schema_file": str(SCHEMA_FILE_PATH),
        "schema_file_found": SCHEMA_FILE_PATH.is_file(),
        "active_datasets": len(DATASETS),
        "active_jobs": len(JOBS),
    }



@app.get("/api/metadata")
async def get_metadata():
    return {
        "project_id": settings.project_id,
        "location": settings.location,
        "default_model": settings.default_model,
        "default_dataset": settings.default_dataset,
        "default_table": settings.default_table,
        "raw_bigquery_schema": load_bigquery_schema(),
        "mappable_fields": get_mappable_schema_fields(),
        "enrichment_presets": get_enrichment_presets()
    }


@app.post("/api/sample")
async def load_sample_dataset():
    sample = get_sample_data()
    dataset_id = f"ds_sample_{uuid.uuid4().hex[:6]}"
    dataset_info = {
        "dataset_id": dataset_id,
        "filename": sample["filename"],
        "columns": sample["columns"],
        "rows": sample["rows"],
        "total_rows": sample["total_rows"],
        "created_at": time.time()
    }
    DATASETS[dataset_id] = dataset_info
    suggestions = auto_suggest_mapping(sample["columns"])

    return {
        "dataset_id": dataset_id,
        "filename": sample["filename"],
        "columns": sample["columns"],
        "preview_rows": sample["rows"][:10],
        "total_rows": sample["total_rows"],
        "auto_mapping": suggestions
    }


@app.post("/api/upload")
async def upload_file(file: UploadFile = File(...)):
    content = await file.read()
    dataset_info = parse_uploaded_file(file.filename or "uploaded.csv", content)
    suggestions = auto_suggest_mapping(dataset_info["columns"])

    return {
        "dataset_id": dataset_info["dataset_id"],
        "filename": dataset_info["filename"],
        "columns": dataset_info["columns"],
        "preview_rows": dataset_info["rows"][:10],
        "total_rows": dataset_info["total_rows"],
        "auto_mapping": suggestions
    }


@app.post("/api/mapping/auto-suggest")
async def suggest_mapping_endpoint(payload: Dict[str, Any] = Body(...)):
    columns = payload.get("columns", [])
    return {
        "auto_mapping": auto_suggest_mapping(columns)
    }


@app.post("/api/enrichment/test-rule")
async def test_single_enrichment_rule(req: TestRuleRequest):
    raw_row = req.sample_row
    if not raw_row:
        if req.dataset_id and req.dataset_id in DATASETS:
            rows = DATASETS[req.dataset_id]["rows"]
            idx = min(max(0, req.row_index), len(rows) - 1)
            raw_row = rows[idx]
        else:
            sample = get_sample_data()
            raw_row = sample["rows"][0]

    base_extracted = build_base_mapped_row(raw_row, req.mapping_config)

    loop = asyncio.get_event_loop()
    result = await loop.run_in_executor(
        None,
        enricher_engine.execute_rule_sync,
        req.rule,
        raw_row,
        base_extracted,
        req.model_name,
        req.project_id or settings.project_id,
        req.location or settings.location
    )

    # "Before": mapping only (no AI enrichment applied)
    bq_before = format_to_bigquery_schema(dict(base_extracted), req.project_id or settings.project_id)
    validation_before = validate_bigquery_row(bq_before)

    # "After": mapping + this enrichment rule applied
    merged_extracted = apply_enrichment_to_extracted(base_extracted, [result])
    bq_preview = format_to_bigquery_schema(merged_extracted, req.project_id or settings.project_id)
    validation = validate_bigquery_row(bq_preview)

    diff_summary = build_enrichment_diff(bq_before, bq_preview, result.get("target_field", ""))

    return {
        "test_result": result,
        "raw_row": raw_row,
        "bigquery_row_before": bq_before,
        "bigquery_row_preview": bq_preview,
        "validation_before": validation_before,
        "validation": validation,
        "diff_summary": diff_summary
    }


async def run_batch_job_worker(job_id: str, req: StartJobRequest):
    job = JOBS[job_id]
    job["status"] = "running"
    job["logs"].append(f"[開始] ジョブID '{job_id}' 処理を開始しました (モデル: {req.model_name}, 並列数: {req.concurrency})")

    dataset = DATASETS.get(req.dataset_id)
    if not dataset:
        job["status"] = "failed"
        job["error"] = "Dataset not found"
        return

    all_rows = dataset["rows"]
    limit = req.row_limit if (req.row_limit and req.row_limit > 0) else len(all_rows)
    target_rows = all_rows[:limit]
    job["total_rows"] = len(target_rows)

    sem = asyncio.Semaphore(max(1, min(req.concurrency, 15)))
    loop = asyncio.get_event_loop()

    async def process_single_row(idx: int, raw_row: Dict[str, Any]):
        async with sem:
            row_start = time.time()
            base_extracted = build_base_mapped_row(raw_row, req.mapping_config)
            enrichment_outputs = []

            for rule in req.enrichment_rules:
                if not rule.get("enabled", True):
                    continue
                effective_rule = dict(rule)
                # ジョブ全体の検証設定をルール未指定時のデフォルトとして適用
                if "enable_verification" not in effective_rule:
                    effective_rule["enable_verification"] = req.enable_verification
                res = await loop.run_in_executor(
                    None,
                    enricher_engine.execute_rule_sync,
                    effective_rule,
                    raw_row,
                    base_extracted,
                    req.model_name,
                    req.project_id or settings.project_id,
                    req.location or settings.location
                )
                enrichment_outputs.append(res)

            merged = apply_enrichment_to_extracted(base_extracted, enrichment_outputs)
            bq_row = format_to_bigquery_schema(merged, req.project_id or settings.project_id)
            val_res = validate_bigquery_row(bq_row)

            # --- 品質検証サマリー ---
            fixed_rules = 0
            remaining_issues = 0
            for out in enrichment_outputs:
                ver = out.get("verification") or {}
                if ver.get("changed"):
                    fixed_rules += 1
                remaining_issues += len([
                    i for i in (ver.get("post_issues") or []) if i.get("severity") == "high"
                ])

            row_elapsed = round(time.time() - row_start, 2)
            prod_id = bq_row.get("id", f"row_{idx+1}")
            prod_title = (bq_row.get("title") or "")[:30]

            job["processed_rows"] += 1
            if val_res["valid"]:
                job["success_count"] += 1
            else:
                job["warning_count"] += 1
            job["fixed_count"] = job.get("fixed_count", 0) + fixed_rules
            job["quality_issue_count"] = job.get("quality_issue_count", 0) + remaining_issues

            quality_note = ""
            if fixed_rules:
                quality_note += f" / AI検証で {fixed_rules} 件自動修正"
            if remaining_issues:
                quality_note += f" / ⚠ 未解消の重大な問題 {remaining_issues} 件"

            log_msg = (
                f"[{job['processed_rows']}/{job['total_rows']}] 商品 '{prod_id}' ({prod_title}...) "
                f"変換・Enrichment完了 ({row_elapsed}秒){quality_note}"
            )
            job["logs"].append(log_msg)

            return {
                "row_index": idx,
                "raw_row": raw_row,
                "enrichment_traces": enrichment_outputs,
                "bigquery_row": bq_row,
                "validation": val_res,
                "verification_summary": {
                    "fixed_rules": fixed_rules,
                    "remaining_high_issues": remaining_issues
                },
                "elapsed_seconds": row_elapsed
            }


    try:
        tasks = [process_single_row(i, r) for i, r in enumerate(target_rows)]
        results = await asyncio.gather(*tasks)
        job["results"] = sorted(results, key=lambda x: x["row_index"])
        job["status"] = "completed"
        job["completed_at"] = time.time()
        total_elapsed = round(job["completed_at"] - job["started_at"], 2)
        job["logs"].append(f"[完了] 全 {len(results)} 件のデータ変換およびAI Enrichmentが完了しました！ (総所要時間: {total_elapsed}秒)")
    except Exception as e:
        logger.exception("Batch job failed")
        job["status"] = "failed"
        job["error"] = str(e)
        job["logs"].append(f"[エラー] 処理中断: {str(e)}")


@app.post("/api/process/start")
async def start_batch_process(req: StartJobRequest):
    if req.dataset_id not in DATASETS:
        raise HTTPException(status_code=404, detail="データセットが見つかりません。ファイルを再アップロードするかサンプルデータを読み込んでください。")

    job_id = f"job_{uuid.uuid4().hex[:8]}"
    dataset = DATASETS[req.dataset_id]
    limit = req.row_limit if (req.row_limit and req.row_limit > 0) else len(dataset["rows"])

    JOBS[job_id] = {
        "job_id": job_id,
        "dataset_id": req.dataset_id,
        "status": "queued",
        "total_rows": min(limit, len(dataset["rows"])),
        "processed_rows": 0,
        "success_count": 0,
        "warning_count": 0,
        "fixed_count": 0,
        "quality_issue_count": 0,
        "started_at": time.time(),
        "completed_at": None,
        "logs": [],
        "results": [],
        "error": None
    }

    asyncio.create_task(run_batch_job_worker(job_id, req))
    return {"job_id": job_id, "status": "queued", "total_rows": JOBS[job_id]["total_rows"]}


@app.get("/api/process/status/{job_id}")
async def get_job_status(job_id: str):
    if job_id not in JOBS:
        raise HTTPException(status_code=404, detail="Job not found")
    job = JOBS[job_id]
    return {
        "job_id": job["job_id"],
        "status": job["status"],
        "total_rows": job["total_rows"],
        "processed_rows": job["processed_rows"],
        "success_count": job["success_count"],
        "warning_count": job["warning_count"],
        "fixed_count": job.get("fixed_count", 0),
        "quality_issue_count": job.get("quality_issue_count", 0),
        "logs": job["logs"][-30:],
        "error": job["error"],
        "results_preview": job["results"][:20] if job["status"] == "completed" else []
    }


@app.get("/api/export/jsonl/{job_id}")
async def export_bigquery_jsonl(job_id: str):
    if job_id not in JOBS:
        raise HTTPException(status_code=404, detail="Job not found")
    job = JOBS[job_id]
    if not job["results"]:
        raise HTTPException(status_code=400, detail="変換された結果データがありません。")

    lines = []
    for item in job["results"]:
        bq_row = item["bigquery_row"]
        lines.append(json.dumps(bq_row, ensure_ascii=False))

    content = "\n".join(lines) + "\n"
    filename = f"aics_bigquery_catalog_{job_id}.jsonl"

    return Response(
        content=content.encode("utf-8"),
        media_type="application/x-ndjson",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'}
    )


@app.post("/api/bigquery/load")
async def load_to_bigquery_table(req: BigQueryLoadRequest):
    if req.job_id not in JOBS:
        raise HTTPException(status_code=404, detail="Job not found")
    job = JOBS[req.job_id]
    if not job["results"]:
        raise HTTPException(status_code=400, detail="ロードするデータがありません。")

    try:
        from google.cloud import bigquery

        client = bigquery.Client(project=req.project_id)
        table_ref = f"{req.project_id}.{req.dataset_id}.{req.table_id}"

        rows_to_insert = [item["bigquery_row"] for item in job["results"]]
        jsonl_buffer = io.BytesIO()
        for r in rows_to_insert:
            jsonl_buffer.write((json.dumps(r, ensure_ascii=False) + "\n").encode("utf-8"))
        jsonl_buffer.seek(0)

        job_config = bigquery.LoadJobConfig(
            source_format=bigquery.SourceFormat.NEWLINE_DELIMITED_JSON,
            write_disposition=req.write_disposition,
            ignore_unknown_values=True
        )

        raw_schema = load_bigquery_schema()
        bq_schema_fields = []
        def build_bq_field(f_dict):
            subfields = [build_bq_field(sub) for sub in f_dict.get("fields", [])]
            return bigquery.SchemaField(
                name=f_dict["name"],
                field_type=f_dict["type"],
                mode=f_dict.get("mode", "NULLABLE"),
                fields=subfields
            )
        for field in raw_schema:
            bq_schema_fields.append(build_bq_field(field))
        job_config.schema = bq_schema_fields

        load_job = client.load_table_from_file(jsonl_buffer, table_ref, job_config=job_config)
        load_job.result()

        return {
            "status": "success",
            "table": table_ref,
            "loaded_rows": len(rows_to_insert),
            "job_id": load_job.job_id
        }
    except Exception as e:
        logger.exception("BigQuery load failed")
        raise HTTPException(status_code=500, detail=f"BigQueryロードエラー: {str(e)}")
