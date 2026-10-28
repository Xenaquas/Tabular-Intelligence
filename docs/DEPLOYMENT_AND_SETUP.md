# Local Deployment & Environment Setup Guide

## 1. Prerequisites

- **Operating System**: Windows 11 / 10 (tested baseline) or Linux (Ubuntu 22.04+).
- **Python Runtime**: **Python 3.12 or newer** (Python 3.12.10 recommended).
- **Package Manager**: **`uv` 0.11.21** (pinned in project configuration).
- **Oracle Database**: Oracle Database 23ai Free or Oracle 19c/21c accessible locally or over LAN.
- **Local Embedding Server**: Llama-CPP / Nomic embedding server running locally on port 8088 (`nomic-ai/nomic-embed-text-v2-moe-GGUF`).

---

## 2. Quick-Start Installation

### Step 1: Clone Repository & Create Virtual Environment

```powershell
# Clone the repository
git clone https://github.com/Xenaquas/Tabular-Intelligence.git
cd Tabular-Intelligence

# Install uv package manager (pinned version)
python -m pip install uv==0.11.21

# Create and sync virtual environment with locked dependencies
uv sync --locked
```

---

### Step 2: Environment Configuration

Copy `.env.example` to create your local `.env`:

```powershell
Copy-Item .env.example .env
```

Configure your local parameters inside `.env`:

```ini
# =========================================================================
# Model Provider: "bedrock" (Primary Production) or "openrouter" (Secondary)
# =========================================================================
LLM_PROVIDER=bedrock

# AWS Bedrock Configuration
REGION=ap-south-1
MODEL_ID=anthropic.claude-3-5-haiku-20241022-v1:0
# Optional: Set ROLE_ARN if assuming an IAM role via STS
# ROLE_ARN=arn:aws:iam::123456789012:role/TabularBedrockExecutionRole

# Optional: OpenRouter Development Configuration
OPENROUTER_API_KEY=your_openrouter_api_key_here
OPENROUTER_MODEL=openai/gpt-4o-mini

# =========================================================================
# Local Oracle Database Configuration (python-oracledb)
# =========================================================================
ORACLE_HOST=127.0.0.1
ORACLE_PORT=1521
ORACLE_SERVICE_NAME=FREEPDB1
ORACLE_USER=TABULA_DEMO_RO
ORACLE_PASSWORD=your_oracle_password_here
ORACLE_SCHEMA=TABULA_DEMO_OWNER
ORACLE_ALLOWED_SCHEMAS=TABULA_DEMO_OWNER
ORACLE_ALLOWED_TABLES=USERS,CLAIMS
ORACLE_MODE=thin

# =========================================================================
# Local Nomic Embedding Server
# =========================================================================
NOMIC_EMBED_BASE_URL=http://127.0.0.1:8088/v1
```

> [!CAUTION]
> Never commit `.env` or paste real credentials into pull requests, chat transcripts, or documentation.

---

### Step 3: Oracle Test Schema Provisioning

To provision the synthetic Users and Claims schema in your local Oracle PDB:

```sql
-- Connect as SYSDBA to your PDB (e.g. FREEPDB1)
ALTER SESSION SET CONTAINER = FREEPDB1;

-- 1. Create Schema Owner
CREATE USER TABULA_DEMO_OWNER IDENTIFIED BY "YOUR_OWNER_PASSWORD"
DEFAULT TABLESPACE USERS TEMPORARY TABLESPACE TEMP QUOTA UNLIMITED ON USERS;

GRANT CREATE SESSION, CREATE TABLE, CREATE VIEW, CREATE SEQUENCE TO TABULA_DEMO_OWNER;

-- 2. Create Read-Only Runtime Application User
CREATE USER TABULA_DEMO_RO IDENTIFIED BY "YOUR_READONLY_PASSWORD"
DEFAULT TABLESPACE USERS TEMPORARY TABLESPACE TEMP;

GRANT CREATE SESSION TO TABULA_DEMO_RO;

-- 3. Run schema creation and seed tables
-- Run fixtures/oracle_100_records/01_create_and_seed.sql as TABULA_DEMO_OWNER
```

---

## 3. Launching the Application

Start the Streamlit application server:

```powershell
uv run streamlit run app.py
```

The application will be accessible at:
```text
http://127.0.0.1:8501
```

---

## 4. Running the Test Suites

### 1. Offline Regression Suite (Network Blocked)
```powershell
uv run pytest tests/offline
```
*Expected: 105 passed in ~8s.*

### 2. Live Oracle Integration Suite
```powershell
uv run pytest tests/integration/test_oracle_integration.py --run-oracle
```
*Expected: 8 passed in ~3s.*

---

## 5. Troubleshooting Guide

| Issue / Error | Root Cause | Solution |
| :--- | :--- | :--- |
| `ORA-28000: The account is locked` | Exceeded failed login attempts | Run `ALTER USER TABULA_DEMO_RO ACCOUNT UNLOCK;` in `sqlplus` as SYSDBA. |
| `SocketBlockedError: A test tried to use socket` | `pytest-socket` blocked network access | Standard for offline tests. For Oracle integration tests, add `--run-oracle`. |
| `Error code: 400 - model ID not found` | Provider model identifier mismatch | Verify `LLM_PROVIDER` in `.env` matches your target endpoint (`bedrock` vs `openrouter`). |
| `Nomic Embed Connection Refused` | Local embed server not running on port 8088 | Verify server on `http://127.0.0.1:8088/v1`. Semantic agent will fall back to fuzzy matching. |
