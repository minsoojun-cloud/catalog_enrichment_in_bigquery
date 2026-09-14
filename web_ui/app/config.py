import os
import sys
from pathlib import Path
from pydantic import BaseModel

# Disable Cloudtop mTLS client cert config that causes MutualTLSChannelError in google-auth
os.environ.pop("GOOGLE_API_CERTIFICATE_CONFIG", None)
os.environ["GOOGLE_API_USE_CLIENT_CERTIFICATE"] = "false"
os.environ["CLOUDSDK_CONTEXT_AWARE_USE_CLIENT_CERTIFICATE"] = "false"

# Base directories
BASE_DIR = Path(__file__).resolve().parent.parent
SCHEMA_FILE_PATH = BASE_DIR.parent / "AI_Commerce_Search_Bigquery_schema.json"
PROMPT_FILE_PATH = BASE_DIR.parent / "prompt.txt"
DATA_MAPPING_MD_PATH = BASE_DIR.parent / "data_mapping.md"


class Settings(BaseModel):
    project_id: str = os.environ.get("PROJECT_ID", "retail-search-jp-demo-minsoo")
    location: str = os.environ.get("LOCATION", "us-central1")
    default_model: str = os.environ.get("DEFAULT_MODEL", "gemini-2.5-flash")
    default_dataset: str = os.environ.get("DEFAULT_DATASET", "retail_search")
    default_table: str = os.environ.get("DEFAULT_TABLE", "d-vais-c")
    max_concurrency: int = 5
    port: int = int(os.environ.get("PORT", "8080"))


settings = Settings()
