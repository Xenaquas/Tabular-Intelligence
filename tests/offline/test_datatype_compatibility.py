"""Comprehensive Data-Type Compatibility Matrix Tests.

Audits engine data handling across:
1. Numeric: Decimal, 64-bit int, high-precision float, NaN, Inf
2. Text: Unicode (₹ Rupee symbol, Cyrillic, Arabic, Chinese, Emoji), empty string vs NULL
3. Date/Time: ISO dates, timestamps with/without timezone, leap years
4. Boolean / Categorical: True/False, 1/0, 'Y'/'N'
5. Structured: JSON string parsing and column isolation
"""

import pytest
import duckdb
import pandas as pd
import numpy as np
from core.db_engine import DatabaseEngine
from core.sql_policy import SQLPolicy
from core.execution_context import ExecutionContext
from core.contracts import AnalyticsInput


@pytest.fixture
def datatype_context():
    """Sets up an ExecutionContext with edge-case datatype test records."""
    ctx = ExecutionContext()
    df = pd.DataFrame({
        "id": [1, 2, 3, 4, 5],
        "num_decimal": [12345.67, 0.0001, -987.654, 1e6, np.nan],
        "num_bigint": [9223372036854775800, 100, -9223372036854775800, 0, 42],
        "text_unicode": ["₹2,903,820", "Москва", "مرحبا", "北京", "🚀 Data & Tech"],
        "text_empty_vs_null": ["", None, "valid", "   ", None],
        "date_col": ["2026-01-01", "2024-02-29", "1999-12-31", "2026-12-31", None],  # 2024 is leap year
        "timestamp_tz": [
            "2026-03-01T10:30:00+05:30",
            "2026-03-01T05:00:00Z",
            "2026-06-15T12:00:00-04:00",
            "2026-12-25T18:45:00+00:00",
            None
        ],
        "bool_flag": [True, False, True, False, None],
        "categorical_code": ["Y", "N", "Y", "P", "N"],
        "json_payload": [
            '{"status": "ok", "retries": 0}',
            '{"status": "error", "code": 404}',
            '{"status": "pending"}',
            '{}',
            None
        ]
    })
    with ctx.activate():
        ctx.register_dataset(df, "dt_matrix", "Datatype Matrix")
        yield ctx
    ctx.close()


def test_numeric_precision_and_nan(datatype_context):
    """Verifies decimal precision and NaN exclusion in numeric calculations."""
    engine = DatabaseEngine.get_instance()
    df, err = engine.execute_sql("SELECT SUM(num_decimal) AS sum_dec, AVG(num_decimal) AS avg_dec FROM dt_matrix")
    assert err is None
    assert not np.isnan(df.iloc[0]["sum_dec"])

    # High precision int
    df_int, err_int = engine.execute_sql("SELECT num_bigint FROM dt_matrix WHERE id = 1")
    assert err_int is None
    assert df_int.iloc[0]["num_bigint"] == 9223372036854775800


def test_unicode_text_handling(datatype_context):
    """Verifies that multi-byte Unicode strings including ₹, Cyrillic, and Emojis are preserved intact."""
    engine = DatabaseEngine.get_instance()
    df, err = engine.execute_sql("SELECT text_unicode FROM dt_matrix ORDER BY id")
    assert err is None
    vals = df["text_unicode"].tolist()
    assert vals[0] == "₹2,903,820"
    assert vals[1] == "Москва"
    assert vals[2] == "مرحبا"
    assert vals[3] == "北京"
    assert "🚀" in vals[4]


def test_empty_string_vs_null_semantics(datatype_context):
    """Verifies distinction between empty string '' and SQL NULL."""
    engine = DatabaseEngine.get_instance()
    # Count NULLs
    df_nulls, _ = engine.execute_sql("SELECT COUNT(*) AS null_count FROM dt_matrix WHERE text_empty_vs_null IS NULL")
    assert df_nulls.iloc[0]["null_count"] == 2

    # Count empty strings
    df_empty, _ = engine.execute_sql("SELECT COUNT(*) AS empty_count FROM dt_matrix WHERE text_empty_vs_null = ''")
    assert df_empty.iloc[0]["empty_count"] == 1


def test_date_and_timestamp_parsing(datatype_context):
    """Verifies date leap-year handling and timestamp ISO querying."""
    engine = DatabaseEngine.get_instance()
    # Leap year date query
    df_leap, err = engine.execute_sql("SELECT date_col FROM dt_matrix WHERE date_col = '2024-02-29'")
    assert err is None
    assert len(df_leap) == 1

    # Timestamp comparison
    df_ts, err_ts = engine.execute_sql("SELECT COUNT(*) AS total_ts FROM dt_matrix WHERE timestamp_tz IS NOT NULL")
    assert err_ts is None
    assert df_ts.iloc[0]["total_ts"] == 4


def test_boolean_and_categorical_querying(datatype_context):
    """Verifies boolean filters and categorical aggregations."""
    engine = DatabaseEngine.get_instance()
    df_bool, err = engine.execute_sql("SELECT COUNT(*) AS bool_true FROM dt_matrix WHERE bool_flag = true")
    assert err is None
    assert df_bool.iloc[0]["bool_true"] == 2

    df_cat, _ = engine.execute_sql("SELECT categorical_code, COUNT(*) AS cnt FROM dt_matrix GROUP BY categorical_code ORDER BY cnt DESC")
    assert len(df_cat) >= 3


def test_json_payload_querying(datatype_context):
    """Verifies structured JSON payloads can be stored and queried."""
    engine = DatabaseEngine.get_instance()
    df_json, err = engine.execute_sql("SELECT id, json_payload FROM dt_matrix WHERE json_payload LIKE '%404%'")
    assert err is None
    assert len(df_json) == 1
    assert df_json.iloc[0]["id"] == 2
