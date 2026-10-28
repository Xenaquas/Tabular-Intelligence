# Known Limitations & Engineering Boundaries — Tabular Intelligence

This document records the verified operational boundaries, intentional architectural constraints, and known limitations of the Tabular Intelligence platform.

---

## 1. Database & Schema Limitations

### 1. Unsupported Oracle Features & Versions
- **Legacy Oracle (11g and older)**: Does not support modern ANSI joins or `python-oracledb` Thin mode. Requires thick-mode client libraries.
- **Oracle 23ai AI Functions**: Tabular Intelligence deliberately does **not** support or use Oracle 23ai database-resident vector indexes or AI extensions (`DBMS_HYBRID_VECTOR`). All vector search is handled locally via FAISS.
- **Missing Foreign Keys in Legacy Schemas**: If a legacy schema lacks defined foreign-key constraints in `ALL_CONSTRAINTS`, `OracleCatalog` cannot infer join paths automatically without naming heuristics.

### 2. Unsupported Data Types
- **Binary Large Objects (`BLOB`)**: Raw image, audio, or compiled binary data stored in database BLOB columns are excluded from analysis.
- **Oracle Spatial (`SDO_GEOMETRY`)**: Geometry and GIS mapping objects are unsupported.
- **User-Defined Objects (UDTs) & Nested Tables**: Complex PL/SQL collections or custom types cannot be deserialized into standard tabular series.

---

## 3. Large Dataset & Memory Constraints

- **In-Memory DuckDB Ceiling**: File uploads are registered in-memory (`:memory:`). Datasets exceeding available physical RAM will fail or trigger `duckdb.OutOfMemoryException`.
- **Textual Preview Cap**: LLM prompt context is clamped to the first 15 rows of query results to prevent context window saturation, while the full result dataset is stored in the session context.
- **Categorical Cardinality Limit**: The local semantic vector index caps categorical indexing at 2,000 unique values per column to avoid memory bloat.

---

## 4. Security & Enterprise Authorization

- **Lack of Row-Level Security (RLS)**: The application connects via a shared service account (`TABULA_DEMO_RO`). Row-level filtering is governed by conversational SQL generation rather than database-enforced Virtual Private Database (VPD) policies.
- **No SSO / LDAP Integration**: Authentication is session-based at the Streamlit layer; enterprise Single Sign-On (SAML/OIDC) is not yet integrated.

---

## 5. Model Provider & Operational Monitoring

- **AWS Bedrock Model Access**: Bedrock requires pre-authorized model access in AWS IAM for the specific model ID (`anthropic.claude-3-5-haiku-20241022-v1:0`).
- **Telemetry & Monitoring**: Logs are emitted via Python's standard `logging` library. OpenTelemetry traces and Prometheus metrics exporters are not yet integrated.
