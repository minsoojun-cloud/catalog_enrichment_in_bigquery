# ==============================================================================
# AI Commerce Search Catalog Mapper & Enricher — Cloud Run 用イメージ
#
# ビルドコンテキストはリポジトリのルート (このファイルがある階層) です。
# アプリ本体は web_ui/ 配下ですが、スキーマ定義 JSON がリポジトリ直下にあるため
# ルートをコンテキストにして両方をイメージに含めます。
#
#   ローカルビルド: docker build -t aics-enricher .
#   Cloud Build   : gcloud builds submit --tag ...
# ==============================================================================
FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PORT=8080

WORKDIR /app

# --- 1) 依存関係を先に導入（レイヤーキャッシュを効かせる） ---------------------
COPY web_ui/requirements.txt /app/web_ui/requirements.txt
RUN pip install --no-cache-dir -r /app/web_ui/requirements.txt

# --- 2) アプリが参照するリポジトリ直下のリソース ------------------------------
# app/config.py の _resolve_resource() が /app 直下も探索するため、この配置で解決される
COPY AI_Commerce_Search_Bigquery_schema.json /app/
COPY prompt.txt /app/
COPY data_mapping.md /app/

# --- 3) アプリ本体 -------------------------------------------------------------
COPY web_ui/app /app/web_ui/app
COPY web_ui/static /app/web_ui/static

# --- 4) 非 root ユーザーで実行 --------------------------------------------------
RUN useradd --create-home --uid 1000 appuser && chown -R appuser:appuser /app
USER appuser

WORKDIR /app/web_ui
EXPOSE 8080

# NOTE: アップロード済みデータセットとジョブ状態はプロセス内メモリに保持されるため
#       ワーカーは必ず 1 プロセスに固定する (--workers 1)。
#       スケールアウトさせる場合は Cloud Run 側も --max-instances=1 が必要。
CMD exec uvicorn app.main:app \
    --host 0.0.0.0 \
    --port ${PORT} \
    --workers 1 \
    --timeout-keep-alive 75
