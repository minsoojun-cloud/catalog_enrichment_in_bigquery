import os
import sys
from pathlib import Path
from typing import Optional
from pydantic import BaseModel

# Disable Cloudtop mTLS client cert config that causes MutualTLSChannelError in google-auth.
# (Cloud Run 上では未設定のため無害。ローカル/Cloudtop 実行時のみ効果があります)
os.environ.pop("GOOGLE_API_CERTIFICATE_CONFIG", None)
os.environ["GOOGLE_API_USE_CLIENT_CERTIFICATE"] = "false"
os.environ["CLOUDSDK_CONTEXT_AWARE_USE_CLIENT_CERTIFICATE"] = "false"

# Base directories
BASE_DIR = Path(__file__).resolve().parent.parent


def _resolve_resource(filename: str, env_var: Optional[str] = None) -> Path:
    """
    リソースファイル (スキーマ JSON 等) の配置場所を解決する。

    ローカル実行ではリポジトリ直下 (BASE_DIR.parent) に、コンテナ実行では
    イメージの構成次第で web_ui 直下や /app 直下に置かれるため、
    複数の候補を順に探索する。環境変数による明示指定を最優先する。
    """
    if env_var:
        override = os.environ.get(env_var)
        if override and Path(override).is_file():
            return Path(override)

    candidates = [
        BASE_DIR.parent / filename,   # ローカル: リポジトリ直下
        BASE_DIR / filename,          # コンテナ: web_ui 直下にコピーした場合
        BASE_DIR / "resources" / filename,
        Path("/app") / filename,      # コンテナ: /app 直下
    ]
    for candidate in candidates:
        if candidate.is_file():
            return candidate
    # 見つからない場合も従来どおりのパスを返す (schema_manager 側で内蔵定義にフォールバック)
    return BASE_DIR.parent / filename


SCHEMA_FILE_PATH = _resolve_resource(
    "AI_Commerce_Search_Bigquery_schema.json", env_var="SCHEMA_FILE_PATH"
)
PROMPT_FILE_PATH = _resolve_resource("prompt.txt")
DATA_MAPPING_MD_PATH = _resolve_resource("data_mapping.md")


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name, str(default)))
    except (TypeError, ValueError):
        return default


class Settings(BaseModel):
    project_id: str = os.environ.get("PROJECT_ID", "retail-search-jp-demo-minsoo")
    location: str = os.environ.get("LOCATION", "global")
    default_model: str = os.environ.get("DEFAULT_MODEL", "gemini-3.8-flash")
    default_dataset: str = os.environ.get("DEFAULT_DATASET", "retail_search")
    default_table: str = os.environ.get("DEFAULT_TABLE", "d-vais-c")
    max_concurrency: int = _env_int("MAX_CONCURRENCY", 5)
    port: int = _env_int("PORT", 8080)


settings = Settings()
