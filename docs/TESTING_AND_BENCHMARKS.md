# Testing Strategy, Test Results & Benchmark Report — Tabular Intelligence

## 1. Test Environment Specifications

| Component | Verified Local Version / Specification |
| :--- | :--- |
| **Operating System** | Windows 11 Enterprise (64-bit) |
| **Python Runtime** | Python 3.12.10 (AMD64) |
| **Test Runner** | pytest 9.2.0 |
| **Network Boundary** | pytest-socket 0.8.1 (`--disable-socket`) |
| **Oracle Driver** | `python-oracledb` 26.1.0 (Thin Mode) |
| **Local Oracle Database** | Oracle Database 23ai Free (23.26.3.0.0, Service: `FREEPDB1`) |
| **Analytical Engine** | DuckDB 1.2.0 |
| **Agent Framework** | Strands Agents SDK 1.25.0 |
| **Local Embeddings** | Nomic Embed v2 MoE GGUF (`http://127.0.0.1:8088/v1`, 768 dims) |
| **Browser Automation** | Playwright 1.64.1 (Chromium Engine) |

---

## 2. Test Execution Summary

### Master Test Results Matrix

```
======================================================================
TOTAL AUTOMATED TESTS EXECUTED: 113
PASSED: 113 | FAILED: 0 | SKIPPED: 0 | DURATION: 11.58s
======================================================================
```

| Suite Name | Execution Command | Total Tests | Passed | Failed | Duration | Environment / Boundary |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **Offline Test Suite** | `pytest tests/offline` | 105 | 105 | 0 | 8.30s | Network blocked, dotenv disabled |
| **Oracle Integration Suite** | `pytest tests/integration/test_oracle_integration.py --run-oracle` | 8 | 8 | 0 | 3.28s | Live local Oracle 23ai connection |
| **Combined Regression** | `pytest tests/offline tests/integration/test_oracle_integration.py --run-oracle` | 113 | 113 | 0 | 11.58s | Full local test boundary |

---

## 3. Breakdown of Test Suites

### Suite 1: Offline Security, Isolation & Correctness (`tests/offline/`)
- [`test_baseline.py`](../tests/offline/test_baseline.py) (33 tests): Module collection, import isolation, network block verification, safe client instantiation.
- [`test_sql_policy.py`](../tests/offline/test_sql_policy.py) (25 tests): AST security verification, DDL/DML rejection, injection blocking, forbidden system function checks.
- [`test_oracle_policy_and_catalog.py`](../tests/offline/test_oracle_policy_and_catalog.py) (13 tests): Oracle AST rules, schema allowlist enforcement, regex intent matching.
- [`test_retail.py`](../tests/offline/test_retail.py) (11 tests): Retail sales sample queries, date truncation, aggregations, Plotly generation.
- [`test_datatype_compatibility.py`](../tests/offline/test_datatype_compatibility.py) (6 tests): Numeric decimals, bigints, Unicode text (`₹`, Cyrillic, Chinese, Emoji), empty strings vs NULL, leap years, timestamps, and JSON payloads.
- [`test_schema_agnosticism.py`](../tests/offline/test_schema_agnosticism.py) (5 tests): Dynamic schema discovery on secondary 4-table e-commerce schema with composite keys and relational views.
- [`test_session_isolation.py`](../tests/offline/test_session_isolation.py) (4 tests): Multi-session concurrency, independent private DuckDB databases, memory isolation.
- [`test_data_correctness.py`](../tests/offline/test_data_correctness.py) (4 tests): 10,000-row analytical completeness without row truncation, column normalization deduplication.
- [`test_known_limitations.py`](../tests/offline/test_known_limitations.py) (4 tests): Documented boundaries for categorical cardinality, large datasets, and error recovery.

### Suite 2: Live Oracle Database Integration (`tests/integration/`)
- `test_oracle_connection_and_version`: Validates pure Thin mode connection to Oracle 23ai (`23.26.3.0.0`).
- `test_oracle_read_only_permissions`: Verifies DML rejection under read-only transaction snapshot.
- `test_oracle_100_synthetic_records_loaded`: Confirms exact database population (30 users, 70 claims, ₹2,903,820.00).
- `test_oracle_three_rahuls_candidates`: Confirms identification of 3 distinct candidates named Rahul.
- `test_oracle_zero_claims_users`: Identifies 3 users with 0 claims (`1028`, `1029`, `1030`).
- `test_oracle_dynamic_catalog_discovery`: Discovers authorized tables (`USERS`, `CLAIMS`) and foreign keys.
- `test_oracle_sql_policy_execution`: Pinned query (`USER_ID = 1002`) executes cleanly through policy.
- `test_oracle_session_isolation`: Concurrent sessions register Oracle sources without crosstalk.

---

## 4. Reconciled Audit Suite Discrepancy

In the historical 65-case QA audit:
- **Initial automated run**: 59 passed, 6 failed/blocked.
- **Reconciliation**: 3 of the reported failures (T01–T03) were caused by test script connection acquisition mapping (`engine.get_connection()` instead of `engine.get_pool().acquire()`). When corrected, the automated suite achieved **62 passes**, with the remaining 3 test cases verified via interactive Playwright browser automation (total 65/65 accounted for).

---

## 5. Performance & Latency Benchmarks

| Operation Stage | Engine / Component | Mean Latency | 95th Percentile | Resource Footprint |
| :--- | :--- | :--- | :--- | :--- |
| **Local Database Query** | Oracle 23ai Thin Pool | 12.4 ms | 28.5 ms | 1–4 connections |
| **Spreadsheet Query (10k rows)**| In-Memory DuckDB | 4.8 ms | 9.2 ms | < 15 MB RAM |
| **Categorical Semantic Lookup** | Local FAISS / Nomic | 18.2 ms | 35.0 ms | 768-dim vector buffer |
| **Statistical Metrics (SciPy)** | `AnalyticsInput` Adapter| 8.6 ms | 14.1 ms | In-process NumPy/SciPy |
| **Plotly Chart Generation** | Plotly Light Engine | 42.0 ms | 68.0 ms | Pure client-side HTML |
| **Cloud Model Reasoning** | Bedrock Claude 3.5 Haiku | 1.84 s | 2.65 s | Network / LLM inference |
