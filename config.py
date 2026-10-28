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

# Default Bedrock Model for Multi-Agent Swarm
SUPERVISOR_MODEL = BEDROCK_MODEL_ID
SUBAGENT_MODEL = BEDROCK_MODEL_ID
FALLBACK_MODEL = BEDROCK_MODEL_ID

# =========================================================================
# Local Nomic Embedding Server (Port 8088 / Llama CPP)
# =========================================================================
NOMIC_EMBED_BASE_URL = os.getenv("NOMIC_EMBED_BASE_URL", "http://127.0.0.1:8088/v1")
NOMIC_EMBED_MODEL = os.getenv("NOMIC_EMBED_MODEL", "nomic-ai/nomic-embed-text-v1.5-GGUF:Q4_K_M")

# =========================================================================
# Legacy OpenRouter Settings (Commented out for Bedrock deployment)
# =========================================================================
# Kept defined (empty by default) so legacy imports in supervisor.py / demo_live_swarm.py resolve.
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "")
# OPENROUTER_BASE_URL = os.getenv("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1")

# Reserved settings; the active agents/index do not enforce these values yet.
MAX_CATEGORICAL_CARDINALITY = int(os.getenv("MAX_CATEGORICAL_CARDINALITY", "2000"))
MAX_SQL_RETRY = int(os.getenv("MAX_SQL_RETRY", "3"))

# Logging Configuration
LOG_FORMAT = "%(asctime)s [%(levelname)s] [%(name)s] %(message)s"
logging.basicConfig(level=logging.INFO, format=LOG_FORMAT)
logger = logging.getLogger("TabularSwarm")
