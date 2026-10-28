# Data-Type Support Matrix & Type System — Tabular Intelligence

## 1. Supported Data-Type Matrix

The table below documents the end-to-end data type support across the entire Tabular Intelligence data lifecycle: Ingestion, Database Storage, SQL Aggregation, Statistical Computing, and Plotly Visualization.

| Data Type Category | Specific Data Types | CSV/Excel Ingestion | Oracle Retrieval | DuckDB Conversion | SQL Aggregation | Statistics (SciPy) | Plotly Charts | Support Classification | Operational Notes |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **Integers** | `INT`, `BIGINT`, `NUMBER(10)` | Yes | Yes | `INT64` | `SUM`, `AVG`, `MIN`, `MAX` | Full | X/Y Axis | **Fully Supported** | 64-bit integer precision preserved without overflow. |
| **Fixed Decimals** | `DECIMAL(p,s)`, `NUMBER(p,s)` | Yes | Yes | `DECIMAL` / `DOUBLE` | `SUM`, `AVG`, `ROUND` | Full | X/Y Axis | **Fully Supported** | Converted cleanly to Python `float` for scientific computing. |
| **Floating Point** | `FLOAT`, `DOUBLE`, `BINARY_DOUBLE`| Yes | Yes | `DOUBLE` | Full | Full | Full | **Fully Supported** | `NaN` values excluded automatically from distribution calculations. |
| **Text Strings** | `VARCHAR`, `VARCHAR2`, `TEXT` | Yes | Yes | `VARCHAR` | `COUNT`, `GROUP BY` | Frequency | Category Axis | **Fully Supported** | Full UTF-8 support (tested with `₹` Rupee, Cyrillic, Chinese, Emoji). |
| **Empty vs NULL** | `''` vs `NULL` | Yes | Yes | Distinguishable | Separate counts | Excluded | Excluded | **Fully Supported** | SQL ternary logic preserved (`IS NULL` vs `=''`). |
| **Calendar Dates** | `DATE`, ISO `YYYY-MM-DD` | Yes | Yes | `DATE` | `MIN`, `MAX`, `GROUP BY` | Date diffs | Time Series Axis | **Fully Supported** | Leap years (`2024-02-29`) and historical dates verified. |
| **Timestamps** | `TIMESTAMP`, `TIMESTAMP WITH TZ` | Yes | Yes | `TIMESTAMP_TZ` | `EXTRACT`, `TRUNC` | Delta stats | Time Series Axis | **Supported with Conversion**| Time zones converted to standardized ISO UTC timestamps. |
| **Booleans** | `BOOLEAN`, `1/0`, `'Y'/'N'` | Yes | Yes | `BOOLEAN` / `VARCHAR` | `COUNT`, Filter | True/False ratio | Category Axis | **Fully Supported** | Standardized to Python boolean flags. |
| **Structured JSON** | JSON strings, nested payloads | Yes | Yes | `JSON` / `VARCHAR` | Predicates (`LIKE`) | None | None | **Retrieval-only** | Retrievable and filterable; nested JSON expansion not executed. |
| **Large Objects** | `CLOB`, `BLOB`, `LONG` | Excluded | Chunked | Read as String/Skip | None | None | None | **Retrieval-only** | Text LOBs streamed via `val.read()`; raw binary BLOBs truncated. |
| **Spatial / Vectors** | Oracle Spatial, SDO_GEOMETRY | No | No | No | No | No | No | **Unsupported** | Vector indexing handled locally via FAISS; Oracle spatial excluded. |

---

## 2. Type Conversion & Normalization Rules

1. **Numeric Series Conversion**: `AnalyticsInput.get_numeric_series()` applies `pd.to_numeric(df[col], errors='coerce').dropna()`. Non-numeric or missing entries are safely dropped before computing parametric statistics.
2. **Column Name Normalization**: Headers with whitespace, hyphens, periods, or leading numbers (e.g. ` 123-Total Sales `) are transformed to legal SQL identifiers (`_123_total_sales`) via `core/db_engine.py:normalize_column_name`.
3. **Oracle Number Mapping**: `NUMBER(10)` is mapped to 64-bit integer; `NUMBER(12,2)` is mapped to double precision float.
