# Project Context — Tabular Intelligence

## 1. Executive Origin & Evolution

Tabular Intelligence began as an experimental proof of concept (POC) designed to explore conversational data analytics over tabular business files (spreadsheets in CSV and Microsoft Excel formats). The original version coupled Streamlit with the Strands Agents SDK, AWS Bedrock (Claude 3.5 Haiku), an in-memory DuckDB analytical database, and local FAISS semantic indexing powered by Nomic embeddings.

Following successful leadership demonstrations, enterprise relational database requirements emerged, specifically requiring live, high-performance integration with an on-premises Oracle database without compromising local spreadsheet capabilities, UI responsiveness, or multi-agent orchestration.

### Chronological Development Milestones

1. **Phase 0A (Baseline Certification & Environment Hardening)**
   - Pinned Python 3.12+ runtime and `uv` 0.11.21 dependency management.
   - Enforced network boundaries during test execution via `pytest-socket`.
   - Identified 10 key technical limitations (unrestricted SQL execution, shared singleton state, lack of session isolation, and row truncation risks).

2. **Phase 0B (Runtime Evaluation & SQL Security Boundary)**
   - Introduced session-scoped execution contexts via `core/execution_context.py` to eliminate cross-session data leakage.
   - Integrated OpenRouter provider as a configurable secondary model endpoint.
   - Implemented AST-based SQL policy enforcement via `sqlglot` to reject DDL, DML, file access, and multi-statement attacks.
   - Established 94 passing offline tests with 10,000-row analytical completeness.

3. **New Framework with DB (Current Milestone)**
   - **Direct Oracle Integration**: Pure Thin-mode connectivity via `python-oracledb` with connection pooling and `SET TRANSACTION READ ONLY` enforcement.
   - **Architectural Decoupling**: Extracted `DataSource`, `QueryResult`, and `AnalyticsInput` abstractions (`core/contracts.py`), decoupling statistical and visualization tools from concrete DuckDB or Oracle backends.
   - **Deterministic Entity Disambiguation (DEF-02)**: Pre-query AST interception (`core/identity_resolver.py`) preventing queries from combining unpinned entities (e.g. multiple Rahuls).
   - **Database Statistical Parity (DEF-01)**: Decoupled statistics and Plotly chart generation to operate seamlessly on both DuckDB files and live Oracle tables.
   - **Reconciled Synthetic Fixture Ground Truth (DEF-03)**: Verified physical truth across 30 users, 70 claims, totaling ₹2,903,820.00.
   - **Comprehensive Automated Regression**: 105 offline tests + 8 live Oracle integration tests (113 total passed).

---

## 2. Core Product Principles

- **Local-First & Privacy Conscious**: Processing occurs locally using local DuckDB and on-premises Oracle. Cloud inference is strictly limited to model reasoning.
- **Architectural Decoupling**: Agents and tools interact with abstract `DataSource` contracts rather than concrete database instances.
- **Strict Read-Only Enforcement**: Database interaction is confined to read-only queries with zero DML/DDL permissions.
- **Deterministic Disambiguation**: The system never guesses an entity identity when multiple candidate records exist.
- **Preserved Specialist Swarm**: The Strands supervisor coordinates four distinct specialists: Profiler, Semantic, SQL, and Statistics/Visualization agents.

---

## 3. Scope & Protected Invariants

The following architectural decisions are non-negotiable invariants:
- **Do not replace Strands Agents SDK** with LangGraph, CrewAI, AutoGen, or custom orchestrators.
- **Do not consolidate the 4 specialist agents** into a monolithic prompt.
- **Do not replace DuckDB** as the analytical engine for uploaded spreadsheets.
- **Do not alter the Streamlit UI** layout, styling, metrics panel, or drawer navigation.
- **Do not use Oracle 23ai database-resident LLM or cloud vector features**; embeddings remain local via Nomic-MoE and FAISS.
- **Do not introduce SQLite** as an additional application database for user records.
