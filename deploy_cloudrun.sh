#!/usr/bin/env bash
# ==============================================================================
# AI Commerce Search Catalog Mapper & Enricher
#   Cloud Run デプロイスクリプト（冪等・再実行可能）
#
#   使い方:
#     ./deploy_cloudrun.sh                 # デプロイ実行
#     ./deploy_cloudrun.sh --setup-only    # API 有効化 + SA/IAM 設定のみ
#     ./deploy_cloudrun.sh --dry-run       # 実行するコマンドの確認のみ
#
#   環境変数で上書き可能:
#     PROJECT_ID / REGION / SERVICE_NAME / SERVICE_ACCOUNT_NAME
#     VERTEX_LOCATION / DEFAULT_MODEL / DEFAULT_DATASET / DEFAULT_TABLE
#     ALLOW_UNAUTHENTICATED (true|false)
# ==============================================================================
set -euo pipefail

# ---------- 設定 ---------------------------------------------------------------
PROJECT_ID="${PROJECT_ID:-retail-search-jp-demo-minsoo}"
REGION="${REGION:-asia-northeast1}"
SERVICE_NAME="${SERVICE_NAME:-aics-catalog-enricher}"
SERVICE_ACCOUNT_NAME="${SERVICE_ACCOUNT_NAME:-aics-enricher-sa}"

# アプリ設定 (Cloud Run の環境変数として注入)
VERTEX_LOCATION="${VERTEX_LOCATION:-global}"   # gemini-3.8-flash は global のみ提供
DEFAULT_MODEL="${DEFAULT_MODEL:-gemini-3.8-flash}"
DEFAULT_DATASET="${DEFAULT_DATASET:-retail_search}"
DEFAULT_TABLE="${DEFAULT_TABLE:-d-vais-c}"

# 認証なしで公開するか (社内デモ用途なら true、限定公開なら false)
ALLOW_UNAUTHENTICATED="${ALLOW_UNAUTHENTICATED:-false}"

# Cloud Run リソース設定
MEMORY="${MEMORY:-2Gi}"
CPU="${CPU:-2}"
REQUEST_TIMEOUT="${REQUEST_TIMEOUT:-3600}"     # バッチ Enrichment は長時間かかる
CONCURRENCY="${CONCURRENCY:-40}"

# gcloud のパス解決 (Cloudtop では PATH に無いことがある)
GCLOUD="${GCLOUD:-$(command -v gcloud || echo /google/data/ro/teams/cloud-sdk/gcloud)}"

SERVICE_ACCOUNT_EMAIL="${SERVICE_ACCOUNT_NAME}@${PROJECT_ID}.iam.gserviceaccount.com"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" >/dev/null 2>&1 && pwd)"

DRY_RUN=false
SETUP_ONLY=false
for arg in "$@"; do
  case "$arg" in
    --dry-run)    DRY_RUN=true ;;
    --setup-only) SETUP_ONLY=true ;;
    -h|--help)    sed -n '2,20p' "${BASH_SOURCE[0]}"; exit 0 ;;
    *) echo "不明な引数: $arg" >&2; exit 1 ;;
  esac
done

run() {
  echo "  \$ $*"
  if [[ "$DRY_RUN" == "false" ]]; then
    "$@"
  fi
}

section() {
  echo
  echo "=============================================================================="
  echo " $1"
  echo "=============================================================================="
}

# ---------- 0) 事前チェック -----------------------------------------------------
section "0. 事前チェック"
if [[ ! -x "$GCLOUD" ]] && ! command -v "$GCLOUD" >/dev/null 2>&1; then
  echo "ERROR: gcloud が見つかりません。GCLOUD=/path/to/gcloud を指定してください。" >&2
  exit 1
fi
echo "  gcloud      : $GCLOUD"
echo "  PROJECT_ID  : $PROJECT_ID"
echo "  REGION      : $REGION"
echo "  SERVICE     : $SERVICE_NAME"
echo "  SERVICE_ACCT: $SERVICE_ACCOUNT_EMAIL"
echo "  MODEL       : $DEFAULT_MODEL (location=$VERTEX_LOCATION)"
echo "  公開設定    : ALLOW_UNAUTHENTICATED=$ALLOW_UNAUTHENTICATED"

if [[ "$DRY_RUN" == "false" ]]; then
  if ! "$GCLOUD" auth print-access-token >/dev/null 2>&1; then
    echo "ERROR: gcloud にログインしていません。次を実行してください:" >&2
    echo "  $GCLOUD auth login --update-adc" >&2
    exit 1
  fi
fi

# ---------- 1) 必要な API の有効化 ----------------------------------------------
section "1. 必要な API を有効化"
run "$GCLOUD" services enable \
  run.googleapis.com \
  cloudbuild.googleapis.com \
  artifactregistry.googleapis.com \
  aiplatform.googleapis.com \
  bigquery.googleapis.com \
  --project="$PROJECT_ID"

# ---------- 2) サービスアカウントと IAM -----------------------------------------
section "2. サービスアカウントと IAM ロール"
if "$GCLOUD" iam service-accounts describe "$SERVICE_ACCOUNT_EMAIL" \
      --project="$PROJECT_ID" >/dev/null 2>&1; then
  echo "  サービスアカウントは既に存在します: $SERVICE_ACCOUNT_EMAIL"
else
  run "$GCLOUD" iam service-accounts create "$SERVICE_ACCOUNT_NAME" \
    --display-name="AI Commerce Search Catalog Enricher (Cloud Run)" \
    --project="$PROJECT_ID"
fi

# Vertex AI (Gemini + Google Search Grounding) と BigQuery ロードに必要な最小権限
for ROLE in \
  roles/aiplatform.user \
  roles/bigquery.jobUser \
  roles/bigquery.dataEditor
do
  echo "  付与: $ROLE"
  run "$GCLOUD" projects add-iam-policy-binding "$PROJECT_ID" \
    --member="serviceAccount:${SERVICE_ACCOUNT_EMAIL}" \
    --role="$ROLE" \
    --condition=None \
    --quiet
done

if [[ "$SETUP_ONLY" == "true" ]]; then
  section "--setup-only が指定されたため、ここで終了します"
  exit 0
fi

# ---------- 3) ビルド & デプロイ -------------------------------------------------
section "3. Cloud Run へビルド & デプロイ"

AUTH_FLAG="--no-allow-unauthenticated"
if [[ "$ALLOW_UNAUTHENTICATED" == "true" ]]; then
  AUTH_FLAG="--allow-unauthenticated"
fi

# NOTE:
#  --max-instances=1  : データセット/ジョブ状態をプロセス内メモリに保持するため必須
#  --no-cpu-throttling: バッチ Enrichment はリクエスト応答後もバックグラウンドで
#                       動き続けるため、CPU 常時割当が必要
#  --timeout          : 一括実行の進捗ポーリングが長時間に及ぶケースに対応
run "$GCLOUD" run deploy "$SERVICE_NAME" \
  --source="$SCRIPT_DIR" \
  --project="$PROJECT_ID" \
  --region="$REGION" \
  --platform=managed \
  --service-account="$SERVICE_ACCOUNT_EMAIL" \
  --memory="$MEMORY" \
  --cpu="$CPU" \
  --timeout="$REQUEST_TIMEOUT" \
  --concurrency="$CONCURRENCY" \
  --min-instances=0 \
  --max-instances=1 \
  --no-cpu-throttling \
  --execution-environment=gen2 \
  --set-env-vars="PROJECT_ID=${PROJECT_ID},LOCATION=${VERTEX_LOCATION},DEFAULT_MODEL=${DEFAULT_MODEL},DEFAULT_DATASET=${DEFAULT_DATASET},DEFAULT_TABLE=${DEFAULT_TABLE}" \
  "$AUTH_FLAG"

# ---------- 4) 結果表示 ----------------------------------------------------------
section "4. デプロイ完了"
if [[ "$DRY_RUN" == "false" ]]; then
  URL="$("$GCLOUD" run services describe "$SERVICE_NAME" \
          --project="$PROJECT_ID" --region="$REGION" \
          --format='value(status.url)')"
  echo "  サービス URL: $URL"
  echo
  echo "  ヘルスチェック:"
  echo "    curl -s ${URL}/api/health"
  if [[ "$ALLOW_UNAUTHENTICATED" != "true" ]]; then
    echo
    echo "  ※ 認証必須で公開しています。ブラウザからアクセスするには以下のいずれかを実施してください:"
    echo "    a) ローカルプロキシ経由:"
    echo "       $GCLOUD run services proxy $SERVICE_NAME --project=$PROJECT_ID --region=$REGION --port=8080"
    echo "       → http://localhost:8080"
    echo "    b) 特定ユーザーに権限付与:"
    echo "       $GCLOUD run services add-iam-policy-binding $SERVICE_NAME \\"
    echo "         --project=$PROJECT_ID --region=$REGION \\"
    echo "         --member='user:YOUR_LDAP@google.com' --role='roles/run.invoker'"
  fi
fi
