"""Deterministic tests verifying cross-session isolation and resource ownership."""

import threading
import time
import pandas as pd
import pytest

from core.execution_context import ExecutionContext, SessionRegistry, get_current_context
from core.tools.sql_tools import execute_duckdb_sql
from core.tools.artifact_store import ArtifactStore
from core.agents.semantic_agent import lookup_categorical_entity


@pytest.fixture(autouse=True)
def offline_semantic_fallback(monkeypatch):
    """Ensures offline tests use deterministic string/fuzzy matching without attempting local HTTP calls."""
    from core.nomic_embeddings import NomicEmbeddingsClient

    def offline_stub(*args, **kwargs):
        raise RuntimeError("Offline test; local embedding server is bypassed.")

    monkeypatch.setattr(NomicEmbeddingsClient, "get_embeddings", offline_stub)
    yield


def test_independent_sessions_table_isolation():
    """Verifies Session A cannot query Session B's tables and vice versa."""
    ctx_a = SessionRegistry.get_or_create("session_alpha")
    ctx_b = SessionRegistry.get_or_create("session_beta")

    df_a = pd.DataFrame({"alpha_id": [1, 2], "revenue": [100.0, 200.0]})
    df_b = pd.DataFrame({"beta_id": [10, 20], "salary": [5000.0, 6000.0]})

    with ctx_a.activate():
        ctx_a.register_dataset(df_a, "alpha_table", "Alpha Dataset")

    with ctx_b.activate():
        ctx_b.register_dataset(df_b, "beta_table", "Beta Dataset")

    # Session A executes queries
    with ctx_a.activate():
        res_a, err_a = ctx_a.db_engine.execute_sql("SELECT * FROM alpha_table")
        assert err_a is None
        assert len(res_a) == 2

        # Session A attempts to query Session B's table -> MUST FAIL
        res_cross, err_cross = ctx_a.db_engine.execute_sql("SELECT * FROM beta_table")
        assert res_cross is None
        assert err_cross is not None
        assert "not in the authorized catalog" in err_cross or "does not exist" in err_cross

    # Session B executes queries
    with ctx_b.activate():
        res_b, err_b = ctx_b.db_engine.execute_sql("SELECT * FROM beta_table")
        assert err_b is None
        assert len(res_b) == 2

        # Session B attempts to query Session A's table -> MUST FAIL
        res_cross_b, err_cross_b = ctx_b.db_engine.execute_sql("SELECT * FROM alpha_table")
        assert res_cross_b is None
        assert err_cross_b is not None

    ctx_a.close()
    ctx_b.close()


def test_semantic_index_isolation():
    """Verifies that categorical entities indexed in Session A do not leak into Session B."""
    ctx_a = SessionRegistry.get_or_create("session_sem_a")
    ctx_b = SessionRegistry.get_or_create("session_sem_b")

    df_a = pd.DataFrame({"department": ["Aerospace", "Biotech"]})
    df_b = pd.DataFrame({"department": ["Finance", "Legal"]})

    with ctx_a.activate():
        ctx_a.register_dataset(df_a, "dept_a", "Dept A")

    with ctx_b.activate():
        ctx_b.register_dataset(df_b, "dept_b", "Dept B")

    with ctx_a.activate():
        res_a = ctx_a.semantic_index.resolve_entity("Aerospace")
        assert "Aerospace" in res_a
        # Session A does not have Finance
        res_a_leak = ctx_a.semantic_index.resolve_entity("Finance")
        assert "Finance" not in res_a_leak

    with ctx_b.activate():
        res_b = ctx_b.semantic_index.resolve_entity("Finance")
        assert "Finance" in res_b
        # Session B does not have Aerospace
        res_b_leak = ctx_b.semantic_index.resolve_entity("Aerospace")
        assert "Aerospace" not in res_b_leak

    ctx_a.close()
    ctx_b.close()


def test_interleaved_query_artifacts_isolation():
    """Verifies interleaved executions across sessions do not overwrite each other's artifact stores."""
    ctx_1 = SessionRegistry.get_or_create("session_worker_1")
    ctx_2 = SessionRegistry.get_or_create("session_worker_2")

    df_1 = pd.DataFrame({"metric_a": [1, 2, 3]})
    df_2 = pd.DataFrame({"metric_b": [100, 200, 300]})

    with ctx_1.activate():
        ctx_1.register_dataset(df_1, "t1", "T1")

    with ctx_2.activate():
        ctx_2.register_dataset(df_2, "t2", "T2")

    # Step 1: Session 1 runs query
    with ctx_1.activate():
        execute_duckdb_sql("SELECT SUM(metric_a) AS total FROM t1")
        art_1 = ctx_1.artifact_store.get_all()
        assert art_1["last_sql"] == "SELECT SUM(metric_a) AS total FROM t1"
        assert art_1["last_dataframe"].iloc[0]["total"] == 6

    # Step 2: Session 2 runs query
    with ctx_2.activate():
        execute_duckdb_sql("SELECT SUM(metric_b) AS total FROM t2")
        art_2 = ctx_2.artifact_store.get_all()
        assert art_2["last_sql"] == "SELECT SUM(metric_b) AS total FROM t2"
        assert art_2["last_dataframe"].iloc[0]["total"] == 600

    # Step 3: Verify Session 1 artifacts were NOT overwritten by Session 2
    with ctx_1.activate():
        art_1_check = ctx_1.artifact_store.get_all()
        assert art_1_check["last_sql"] == "SELECT SUM(metric_a) AS total FROM t1"
        assert art_1_check["last_dataframe"].iloc[0]["total"] == 6

    ctx_1.close()
    ctx_2.close()


def test_concurrent_sessions_thread_safety():
    """Verifies concurrent queries from distinct threads do not corrupt isolated session states."""
    errors = []

    def run_session_flow(session_name: str, val: int):
        try:
            ctx = SessionRegistry.get_or_create(session_name)
            df = pd.DataFrame({"col": [val, val * 2]})
            tbl_name = f"tbl_{session_name}"
            with ctx.activate():
                ctx.register_dataset(df, tbl_name, tbl_name)
                for _ in range(5):
                    res, err = ctx.db_engine.execute_sql(f"SELECT SUM(col) AS total FROM {tbl_name}")
                    if err or res is None or res.iloc[0]["total"] != val * 3:
                        errors.append(f"Session {session_name} mismatch or error: {err}")
            ctx.close()
        except Exception as e:
            errors.append(f"Thread exception in {session_name}: {e}")

    threads = [
        threading.Thread(target=run_session_flow, args=(f"worker_{i}", i * 10))
        for i in range(1, 6)
    ]

    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert len(errors) == 0, f"Concurrent isolation errors: {errors}"
