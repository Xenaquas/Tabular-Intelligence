"""Strict expected failures document defects; they do not certify safety."""

import pandas as pd
import pytest


@pytest.mark.xfail(strict=True, raises=AssertionError, reason="P0: SQL policy deferred to Phase 0B-1")
def test_model_execution_rejects_ddl(engine):
    _, error = engine.execute_sql("CREATE TABLE should_be_rejected AS SELECT 1 AS x")
    assert error is not None


@pytest.mark.xfail(strict=True, raises=AssertionError, reason="P0: session isolation deferred to Phase 0B-2")
def test_singleton_consumers_are_isolated(engine):
    from core.db_engine import DatabaseEngine

    first = DatabaseEngine.get_instance()
    second = DatabaseEngine.get_instance()
    assert first is not second


@pytest.mark.xfail(strict=True, raises=AssertionError, reason="P1: analytical truncation deferred to Phase 0C")
def test_5001_rows_are_complete(engine):
    engine.register_dataframe(pd.DataFrame({"x": range(5001)}), "large_fixture")
    result, error = engine.execute_sql("SELECT * FROM large_fixture")
    assert error is None
    assert len(result) == 5001


@pytest.mark.xfail(strict=True, raises=AttributeError, reason="Missing discount ingestion repair deferred to Phase 0C")
def test_revenue_without_discount_column(engine):
    engine.register_dataframe(pd.DataFrame({"quantity": [2], "unit_price": [10.]}), "no_discount")
