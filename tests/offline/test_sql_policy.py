"""Comprehensive deterministic test suite for SQL authorization policy and execution boundaries."""

import duckdb
import pandas as pd
import pytest

from core.db_engine import DatabaseEngine
from core.sql_policy import SQLPolicy, SQLPolicyViolationType, SQLQueryResult


@pytest.fixture
def policy_engine():
    """Provides a fresh isolated DatabaseEngine configured with a sample table."""
    engine = DatabaseEngine()
    df = pd.DataFrame({
        "id": [1, 2, 3, 4, 5],
        "category": ["Electronics", "Clothing", "Electronics", "Home", "Clothing"],
        "amount": [100.0, 50.0, 200.0, 75.0, 150.0]
    })
    engine.register_dataframe(df, "sales_data")
    try:
        yield engine
    finally:
        engine.close()


# =========================================================================
# 1. Legitimate Analytical Queries (Must Succeed)
# =========================================================================

def test_valid_simple_select(policy_engine):
    res, err = policy_engine.execute_sql("SELECT * FROM sales_data")
    assert err is None
    assert len(res) == 5
    assert list(res["id"]) == [1, 2, 3, 4, 5]


def test_valid_cte_query(policy_engine):
    query = """
    WITH category_summary AS (
        SELECT category, SUM(amount) AS total_amount
        FROM sales_data
        GROUP BY category
    )
    SELECT * FROM category_summary ORDER BY total_amount DESC
    """
    res, err = policy_engine.execute_sql(query)
    assert err is None
    assert len(res) == 3
    assert res.iloc[0]["category"] == "Electronics"
    assert res.iloc[0]["total_amount"] == 300.0


def test_valid_nested_cte(policy_engine):
    query = """
    WITH step1 AS (
        SELECT category, amount FROM sales_data WHERE amount > 60
    ),
    step2 AS (
        SELECT category, COUNT(*) AS cnt, AVG(amount) AS avg_amt
        FROM step1
        GROUP BY category
    )
    SELECT category, cnt, ROUND(avg_amt, 2) AS avg_amt FROM step2 ORDER BY category
    """
    res, err = policy_engine.execute_sql(query)
    assert err is None
    assert len(res) == 3


def test_valid_group_by_aggregations(policy_engine):
    query = """
    SELECT category, COUNT(*) AS count, MIN(amount) AS min_a, MAX(amount) AS max_a, AVG(amount) AS avg_a
    FROM sales_data
    GROUP BY category
    ORDER BY category
    """
    res, err = policy_engine.execute_sql(query)
    assert err is None
    assert len(res) == 3


def test_valid_self_join(policy_engine):
    query = """
    SELECT a.id AS a_id, b.id AS b_id, a.category
    FROM sales_data a
    JOIN sales_data b ON a.category = b.category AND a.id < b.id
    ORDER BY a_id, b_id
    """
    res, err = policy_engine.execute_sql(query)
    assert err is None
    assert len(res) >= 2


def test_valid_subquery(policy_engine):
    query = """
    SELECT * FROM sales_data
    WHERE amount > (SELECT AVG(amount) FROM sales_data)
    ORDER BY id
    """
    res, err = policy_engine.execute_sql(query)
    assert err is None
    assert len(res) == 2


def test_valid_parameterized_query(policy_engine):
    query = "SELECT * FROM sales_data WHERE category = ?"
    res, err = policy_engine.execute_sql(query, params=["Electronics"])
    assert err is None
    assert len(res) == 2
    assert all(res["category"] == "Electronics")


# =========================================================================
# 2. DDL & DML Rejections
# =========================================================================

def test_reject_create_table(policy_engine):
    res, err = policy_engine.execute_sql("CREATE TABLE evil AS SELECT 1 AS x")
    assert res is None
    assert "Policy Violation" in err
    assert "Create" in err or "not permitted" in err


def test_reject_drop_table(policy_engine):
    res, err = policy_engine.execute_sql("DROP TABLE sales_data")
    assert res is None
    assert "Policy Violation" in err
    assert "Drop" in err or "not permitted" in err


def test_reject_alter_table(policy_engine):
    res, err = policy_engine.execute_sql("ALTER TABLE sales_data ADD COLUMN hack INT")
    assert res is None
    assert "Policy Violation" in err


def test_reject_truncate_table(policy_engine):
    res, err = policy_engine.execute_sql("TRUNCATE TABLE sales_data")
    assert res is None
    assert "Policy Violation" in err


def test_reject_insert_into(policy_engine):
    res, err = policy_engine.execute_sql("INSERT INTO sales_data VALUES (6, 'Toys', 25.0)")
    assert res is None
    assert "Policy Violation" in err


def test_reject_update(policy_engine):
    res, err = policy_engine.execute_sql("UPDATE sales_data SET amount = 0 WHERE id = 1")
    assert res is None
    assert "Policy Violation" in err


def test_reject_delete(policy_engine):
    res, err = policy_engine.execute_sql("DELETE FROM sales_data WHERE id = 1")
    assert res is None
    assert "Policy Violation" in err


# =========================================================================
# 3. Multi-Statement & Stacking Rejections
# =========================================================================

def test_reject_multi_statements_with_semicolon(policy_engine):
    query = "SELECT * FROM sales_data; DROP TABLE sales_data"
    res, err = policy_engine.execute_sql(query)
    assert res is None
    assert "Multiple SQL statements" in err


def test_reject_multi_statements_clean(policy_engine):
    query = "SELECT 1; SELECT 2;"
    res, err = policy_engine.execute_sql(query)
    assert res is None
    assert "Multiple SQL statements" in err


# =========================================================================
# 4. File-Reading & System Commands
# =========================================================================

def test_reject_read_csv(policy_engine):
    query = "SELECT * FROM read_csv('secret.csv')"
    res, err = policy_engine.execute_sql(query)
    assert res is None
    assert "read_csv" in err.lower() or "blocked" in err.lower()


def test_reject_read_parquet(policy_engine):
    query = "SELECT * FROM read_parquet('data.parquet')"
    res, err = policy_engine.execute_sql(query)
    assert res is None
    assert "read_parquet" in err.lower() or "blocked" in err.lower()


def test_reject_glob_function(policy_engine):
    query = "SELECT * FROM glob('*')"
    res, err = policy_engine.execute_sql(query)
    assert res is None
    assert "glob" in err.lower() or "blocked" in err.lower()


def test_reject_system_state_inspection(policy_engine):
    query = "SELECT current_setting('max_memory')"
    res, err = policy_engine.execute_sql(query)
    assert res is None
    assert "current_setting" in err.lower() or "blocked" in err.lower()


def test_reject_copy_export(policy_engine):
    query = "COPY sales_data TO 'exfiltrate.csv'"
    res, err = policy_engine.execute_sql(query)
    assert res is None
    assert "Policy Violation" in err


# =========================================================================
# 5. Unauthorized Table & Schema Qualifications
# =========================================================================

def test_reject_unauthorized_table(policy_engine):
    query = "SELECT * FROM non_existent_or_secret_table"
    res, err = policy_engine.execute_sql(query)
    assert res is None
    assert "not in the authorized catalog" in err


def test_reject_schema_qualified_table(policy_engine):
    query = "SELECT * FROM information_schema.tables"
    res, err = policy_engine.execute_sql(query)
    assert res is None
    assert "Schema qualification" in err or "not permitted" in err


def test_reject_path_in_table_name(policy_engine):
    query = "SELECT * FROM '/etc/passwd'"
    res, err = policy_engine.execute_sql(query)
    assert res is None
    assert "invalid path" in err or "injection" in err


# =========================================================================
# 6. Database-Level Defense-in-Depth
# =========================================================================

def test_database_level_external_access_disabled(policy_engine):
    """Verifies that even if AST validation were bypassed, DuckDB's engine itself blocks external access."""
    with pytest.raises(duckdb.PermissionException):
        # Direct raw execution bypassing SQL policy
        policy_engine._conn.execute("SELECT * FROM read_csv('test_bypass.csv')")
