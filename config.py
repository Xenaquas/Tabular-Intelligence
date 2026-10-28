from core.runtime import require_supported_python

require_supported_python()

import os
import logging
from pathlib import Path
from dotenv import load_dotenv

# Load .env file from project root
env_path = Path(__file__).parent / ".env"
load_dotenv(dotenv_path=env_path)

# Base Paths
BASE_DIR = Path(__file__).parent
DATA_DIR = BASE_DIR / "data"
SCRATCH_DIR = BASE_DIR / "scratch"

# =========================================================================
# AWS Bedrock Configuration (Claude 3.5 Haiku)
# =========================================================================
AWS_REGION = os.getenv("REGION", os.getenv("AWS_REGION", "ap-south-1"))
AWS_ROLE_ARN = os.getenv("ROLE_ARN", os.getenv("AWS_ROLE_ARN", ""))
BEDROCK_MODEL_ID = os.getenv("MODEL_ID", os.getenv("BEDROCK_MODEL_ID", "anthropic.claude-3-5-haiku-20241022-v1:0"))

# Direct AWS Credentials (optional fallback if not using STS assume role)
AWS_ACCESS_KEY_ID = os.getenv("AWS_ACCESS_KEY_ID", "")
AWS_SECRET_ACCESS_KEY = os.getenv("AWS_SECRET_ACCESS_KEY", "")
AWS_SESSION_TOKEN = os.getenv("AWS_SESSION_TOKEN", "")

# =========================================================================
# Model Provider Configuration (OpenRouter and Amazon Bedrock)
# =========================================================================
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "")
OPENROUTER_BASE_URL = os.getenv("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1")
OPENROUTER_MODEL = os.getenv("OPENROUTER_MODEL", "openai/gpt-4o-mini")

# Provider selection: "openrouter" or "bedrock"
# Defaults to "openrouter" if OPENROUTER_API_KEY is present, else "bedrock"
_default_provider = "openrouter" if bool(OPENROUTER_API_KEY.strip()) else "bedrock"
LLM_PROVIDER = os.getenv("LLM_PROVIDER", _default_provider).lower().strip()

# Active default model based on provider
if LLM_PROVIDER == "openrouter":
    SUPERVISOR_MODEL = os.getenv("SUPERVISOR_MODEL", os.getenv("OPENROUTER_MODEL", OPENROUTER_MODEL))
    SUBAGENT_MODEL = os.getenv("SUBAGENT_MODEL", os.getenv("OPENROUTER_MODEL", OPENROUTER_MODEL))
    FALLBACK_MODEL = os.getenv("FALLBACK_MODEL", os.getenv("OPENROUTER_MODEL", OPENROUTER_MODEL))
else:
    SUPERVISOR_MODEL = os.getenv("SUPERVISOR_MODEL", os.getenv("MODEL_ID", BEDROCK_MODEL_ID))
    SUBAGENT_MODEL = os.getenv("SUBAGENT_MODEL", os.getenv("MODEL_ID", BEDROCK_MODEL_ID))
    FALLBACK_MODEL = os.getenv("FALLBACK_MODEL", os.getenv("MODEL_ID", BEDROCK_MODEL_ID))

# =========================================================================
# Local Nomic Embedding Server (Port 8088 / Llama CPP)
# =========================================================================
NOMIC_EMBED_BASE_URL = os.getenv("NOMIC_EMBED_BASE_URL", "http://127.0.0.1:8088/v1")
NOMIC_EMBED_MODEL = os.getenv("NOMIC_EMBED_MODEL", "nomic-ai/nomic-embed-text-v1.5-GGUF:Q4_K_M")

# =========================================================================
# Local Oracle Database Configuration (python-oracledb)
# =========================================================================
ORACLE_HOST = os.getenv("ORACLE_HOST", "127.0.0.1")
ORACLE_PORT = int(os.getenv("ORACLE_PORT", "1521"))
ORACLE_SERVICE_NAME = os.getenv("ORACLE_SERVICE_NAME", "FREEPDB1")
ORACLE_USER = os.getenv("ORACLE_USER", "TABULA_DEMO_RO")
ORACLE_PASSWORD = os.getenv("ORACLE_PASSWORD", "")
ORACLE_SCHEMA = os.getenv("ORACLE_SCHEMA", "TABULA_DEMO_OWNER")
ORACLE_ALLOWED_SCHEMAS = [s.strip().upper() for s in os.getenv("ORACLE_ALLOWED_SCHEMAS", "TABULA_DEMO_OWNER").split(",") if s.strip()]
ORACLE_ALLOWED_TABLES = [t.strip().upper() for t in os.getenv("ORACLE_ALLOWED_TABLES", "USERS,CLAIMS").split(",") if t.strip()]
ORACLE_MODE = os.getenv("ORACLE_MODE", "thin").lower()
ORACLE_POOL_MIN = int(os.getenv("ORACLE_POOL_MIN", "1"))
ORACLE_POOL_MAX = int(os.getenv("ORACLE_POOL_MAX", "4"))
ORACLE_TIMEOUT_SECONDS = float(os.getenv("ORACLE_TIMEOUT_SECONDS", "30.0"))

# Reserved settings; the active agents/index do not enforce these values yet.
MAX_CATEGORICAL_CARDINALITY = int(os.getenv("MAX_CATEGORICAL_CARDINALITY", "2000"))
MAX_SQL_RETRY = int(os.getenv("MAX_SQL_RETRY", "3"))

# Logging Configuration
LOG_FORMAT = "%(asctime)s [%(levelname)s] [%(name)s] %(message)s"
logging.basicConfig(level=logging.INFO, format=LOG_FORMAT)
logger = logging.getLogger("TabularSwarm")
