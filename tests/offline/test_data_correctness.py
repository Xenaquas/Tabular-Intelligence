"""Deterministic tests verifying large-dataset completeness, column normalization, and error handling."""

import numpy as np
import pandas as pd
import pytest

from core.db_engine import DatabaseEngine, normalize_column_name
from core.tools.sql_tools import execute_duckdb_sql
from core.tools.stats_tools import calculate_distribution_stats, detect_outliers_iqr_zscore
from core.tools.artifact_store import ArtifactStore
from core.execution_context import ExecutionContext


@pytest.fixture
def large_dataset_context():
    """Sets up an ExecutionContext with a 10,000-row dataset."""
    ctx = ExecutionContext()
    # Generate 10,000 values where mean is known
    values = np.arange(1, 10001, dtype=float)  # 1 to 10000, mean = 5000.5
    df = pd.DataFrame({
        "row_id": range(1, 10001),
        "metric_val": values
    })
    with ctx.activate():
        ctx.register_dataset(df, "big_table", "Big Table")
        yield ctx
    ctx.close()


def test_10000_rows_analytics_not_truncated(large_dataset_context):
    """Verifies that analytical calculations compute on all 10,000 rows without silent truncation."""
    with large_dataset_context.activate():
        engine = DatabaseEngine.get_instance()
        res, err = engine.execute_sql("SELECT COUNT(*) AS total_count, AVG(metric_val) AS avg_val FROM big_table")
        assert err is None
        assert res.iloc[0]["total_count"] == 10000
        # If truncated to 5,000 rows, avg would be ~2500.5, but full population avg is 5000.5
        assert np.isclose(res.iloc[0]["avg_val"], 5000.5)


def test_distribution_stats_on_full_population(large_dataset_context):
    """Verifies calculate_distribution_stats computes metrics across all 10,000 rows."""
    with large_dataset_context.activate():
        report = calculate_distribution_stats("big_table", "metric_val")
        # Full count is 10,000 formatted with comma
        assert "| **Count** | 10,000 |" in report
        assert "5000.5000" in report  # Mean is exactly 5000.5000


def test_column_normalization_consistency():
    """Verifies normalization handles whitespace, symbols, leading digits, and duplicate collisions."""
    raw_columns = [" Customer ID ", "order-date", "item.price", "123_code", "Total Sales", "Total-Sales"]
    df = pd.DataFrame({col: [1, 2] for col in raw_columns})

    engine = DatabaseEngine()
    meta = engine.register_dataframe(df, "test_norm")
    cols = meta["columns"]

    # No spaces, hyphens, periods, or leading digits in column names
    for c in cols:
        assert " " not in c
        assert "-" not in c
        assert "." not in c
        assert not c[0].isdigit()

    # Deduplicated: Total_Sales and Total_Sales_2
    assert "Total_Sales" in cols
    assert "Total_Sales_2" in cols
    assert "col_123_code" in cols

    engine.close()


def test_dataset_replacement_clean():
    """Verifies re-registering an existing table replaces it completely without locking or column residue."""
    engine = DatabaseEngine()
    df1 = pd.DataFrame({"old_a": [1, 2], "old_b": [3, 4]})
    engine.register_dataframe(df1, "dynamic_tbl")
    assert engine.get_table_metadata("dynamic_tbl")["columns"] == ["old_a", "old_b"]

    # Replace with completely different schema
    df2 = pd.DataFrame({"new_x": [10, 20], "new_y": [30, 40], "new_z": [50, 60]})
    engine.register_dataframe(df2, "dynamic_tbl")
    meta2 = engine.get_table_metadata("dynamic_tbl")
    assert meta2["columns"] == ["new_x", "new_y", "new_z"]
    assert meta2["column_count"] == 3

    res, err = engine.execute_sql("SELECT * FROM dynamic_tbl")
    assert err is None
    assert list(res.columns) == ["new_x", "new_y", "new_z"]

    engine.close()
