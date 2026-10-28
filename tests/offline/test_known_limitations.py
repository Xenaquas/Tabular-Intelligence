"""Regression tests for previously known limitations resolved in Phase 0B."""

import pandas as pd
import pytest


def test_model_execution_rejects_ddl(engine):
    """P0-A: Verifies DDL execution is rejected by SQL policy."""
    _, error = engine.execute_sql("CREATE TABLE should_be_rejected AS SELECT 1 AS x")
    assert error is not None
    assert "Policy Violation" in error or "not permitted" in error


def test_singleton_consumers_are_isolated(engine):
    """P0-B: Verifies separate calls to get_instance yield isolated consumers."""
    from core.db_engine import DatabaseEngine

    first = DatabaseEngine.get_instance()
    second = DatabaseEngine.get_instance()
    assert first is not second


def test_5001_rows_are_complete(engine):
    """Correctness: Verifies analytical queries are not truncated to 5,000 rows."""
    engine.register_dataframe(pd.DataFrame({"x": range(5001)}), "large_fixture")
    result, error = engine.execute_sql("SELECT * FROM large_fixture")
    assert error is None
    assert len(result) == 5001


def test_revenue_without_discount_column(engine):
    """Ingestion: Verifies tables lacking discount_pct register without error."""
    meta = engine.register_dataframe(pd.DataFrame({"quantity": [2], "unit_price": [10.]}), "no_discount")
    assert meta["row_count"] == 1
    assert "revenue" in meta["columns"]
