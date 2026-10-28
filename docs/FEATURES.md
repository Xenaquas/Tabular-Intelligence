# Feature Inventory & Capabilities Matrix — Tabular Intelligence

The following table provides the exhaustive implementation and verification status of all capabilities in Tabular Intelligence.

| Feature Name | Functional Description | Main Component | Data Source Compatibility | Status | Test Coverage | Known Limitations |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **Conversational Analytics** | Natural-language query translation into deterministic SQL | `SupervisorAgent`, `SQLAgent` | CSV, Excel, Oracle | **Implemented & Verified** | `tests/offline/test_baseline.py` | Requires clear conversational intent |
| **Dynamic Schema Discovery** | Discovers tables, columns, constraints, and types at runtime | `OracleCatalog`, `DatabaseEngine` | CSV, Excel, Oracle | **Implemented & Verified** | `tests/integration/test_oracle_integration.py` | Virtual generated columns excluded |
| **Multi-Table Relational Queries** | Generates and executes joins across primary and foreign keys | `SQLAgent`, `SQLPolicy` | CSV, Excel, Oracle | **Implemented & Verified** | `tests/offline/test_schema_agnosticism.py` | Joins require explicit or discovered FKs |
| **AST SQL Security Enforcement** | Rejects DDL, DML, multi-statement injection, and system functions | `SQLPolicy` | CSV, Excel, Oracle | **Implemented & Verified** | `tests/offline/test_sql_policy.py` | Complex recursive CTEs subject to timeout |
| **Deterministic Entity Disambiguation** | Pre-query AST interceptor blocking ambiguous queries (DEF-02) | `DeterministicIdentityResolver` | CSV, Excel, Oracle | **Implemented & Verified** | `tests/integration/test_oracle_integration.py` | Applies to parent/child relationship models |
| **Database Statistical Analysis** | Decoupled parametric & non-parametric metrics (DEF-01) | `StatsAgent`, `AnalyticsInput` | CSV, Excel, Oracle | **Implemented & Verified** | `tests/offline/test_data_correctness.py` | Requires numeric columns |
| **Outlier Detection** | IQR and Z-score anomaly cutoff boundaries with extreme samples | `detect_outliers_iqr_zscore` | CSV, Excel, Oracle | **Implemented & Verified** | `tests/offline/test_data_correctness.py` | Z-score assumes near-normal distribution |
| **Interactive Visualizations** | Generates high-contrast, light-themed Plotly charts | `VizAgent`, `generate_plotly_chart` | CSV, Excel, Oracle | **Implemented & Verified** | `tests/offline/test_retail.py` | Maximum 2,000 points plotted |
| **Spreadsheet Ingestion** | Ingests CSV and Excel files with automated header cleaning | `DatabaseEngine` | CSV, Excel (XLSX, XLS) | **Implemented & Verified** | `tests/offline/test_baseline.py` | In-memory ceiling per session |
| **Session Isolation** | Thread-safe per-session memory, DuckDB, FAISS, and artifacts | `ExecutionContext`, `SessionRegistry` | CSV, Excel, Oracle | **Implemented & Verified** | `tests/offline/test_session_isolation.py` | Memory reclaimed upon browser close |
| **Categorical Semantic Indexing** | Local vector embedding of distinct category values | `SemanticValueIndex`, `NomicEmbeddings` | CSV, Excel, Oracle | **Implemented & Verified** | `tests/offline/test_known_limitations.py` | Cardinality capped at 2,000 values |
| **Embedding Fallback** | Substring and RapidFuzz matching if embedding server offline | `SemanticValueIndex` | CSV, Excel, Oracle | **Implemented & Verified** | `tests/offline/test_baseline.py` | Fallback is lexical, not semantic |
| **Model Provider Abstraction** | Seamless switching between Bedrock (Primary) and OpenRouter | `llm_factory` | All | **Implemented & Verified** | `tests/integration/test_services.py` | Bedrock requires valid AWS IAM role |
| **Out-of-Scope Refusal** | Immediate refusal of off-topic or general knowledge questions | `SupervisorAgent` | All | **Implemented & Verified** | `tests/offline/test_oracle_policy_and_catalog.py` | Regulated by regex intent patterns |
| **Self-Healing SQL Repair** | Automatic retry loop feeding SQL execution errors back to LLM | `SQLAgent`, `execute_sql` | CSV, Excel, Oracle | **Implemented & Verified** | `tests/offline/test_sql_policy.py` | Maximum 3 repair retry attempts |
| **Read-Only Transaction Guard** | Enforces `SET TRANSACTION READ ONLY` on Oracle connections | `OracleEngine` | Oracle | **Implemented & Verified** | `tests/integration/test_oracle_integration.py` | Requires read-only session privilege |
