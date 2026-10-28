# AI Coding Agent Onboarding & Guidelines — Tabular Intelligence

Welcome to **Tabular Intelligence**. Read this file before proposing, writing, or refactoring code.

---

## 1. Mission & Architectural Boundaries

Tabular Intelligence is a local-first conversational analytics platform for spreadsheets (CSV/Excel) and relational databases (Oracle).

### Protected Invariants — NEVER VIOLATE:
1. **Preserve Strands Agents SDK**: Do NOT migrate to LangGraph, CrewAI, AutoGen, or custom orchestrators.
2. **Preserve Specialist Swarm**: Keep the Supervisor and its 4 specialists (`ProfilerAgent`, `SemanticAgent`, `SQLAgent`, `StatsAgent`). Do not merge them into a single agent.
3. **Preserve DuckDB**: Keep DuckDB as the analytical engine for uploaded spreadsheets.
4. **Preserve Streamlit UI**: Do not rewrite or alter the UI layout, styling, metrics, or drawers.
5. **Preserve Decoupled Contracts**: All new tools or database access must interact through `core/contracts.py` (`DataSource`, `AnalyticsInput`). Never hardcode engine imports into stats or viz tools.
6. **No Oracle 23ai Vector/AI Features**: Keep vector search local via FAISS and Nomic-MoE. Do not introduce database-resident LLM functions.

---

## 2. Files to Read First

1. [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md): System components, data contracts, and diagrams.
2. [`core/contracts.py`](core/contracts.py): `DataSource` protocol, `QueryResult`, and `AnalyticsInput`.
3. [`core/sql_policy.py`](core/sql_policy.py): AST SQL validation boundary.
4. [`core/identity_resolver.py`](core/identity_resolver.py): Deterministic entity disambiguation rules.
5. [`core/execution_context.py`](core/execution_context.py): Per-session isolation and memory scoping.

---

## 3. Testing Commands

Always run the full test suites locally before declaring any task complete:

```powershell
# 1. Run offline test suite (network blocked, 105 tests)
uv run pytest tests/offline

# 2. Run live Oracle integration suite (requires local Oracle, 8 tests)
uv run pytest tests/integration/test_oracle_integration.py --run-oracle
```

All 113 automated tests MUST pass. Zero regressions allowed.

---

## 4. Security & Secret Handling Rules

- **Zero Credentials in Code**: Never commit, hardcode, or log passwords, API keys, or tokens.
- **Always read passwords from environment**: `os.getenv("ORACLE_PASSWORD", "")`.
- **Never commit `.env` or database files**: Protected by `.gitignore`.

---

## 5. Git & Deployment Operations

- **Work locally only**: Never commit or push without explicit user instruction.
- **Never force-push or merge into `main`**.
- **No external reporting**: Do not push progress updates to GitHub PRs, Notion, or Google Drive.
