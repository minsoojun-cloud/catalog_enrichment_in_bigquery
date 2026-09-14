#!/usr/bin/env bash
set -e

DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" >/dev/null 2>&1 && pwd )"
cd "$DIR"

export GOOGLE_API_USE_CLIENT_CERTIFICATE=false
export GOOGLE_API_CERTIFICATE_CONFIG=""
export CLOUDSDK_CONTEXT_AWARE_USE_CLIENT_CERTIFICATE=false

PORT=${PORT:-8080}

echo "================================================================================"
echo " Starting AI Commerce Search Catalog Mapper & Enricher Web Server"
echo " Local / Cloudtop Proxy URL: http://$(hostname):${PORT}"
echo "================================================================================"

exec "$DIR/venv/bin/python" -P -m uvicorn app.main:app --host 0.0.0.0 --port "$PORT"
