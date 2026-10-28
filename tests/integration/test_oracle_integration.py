import pytest
import oracledb
import pandas as pd
from core.oracle_engine import OracleEngine
from core.oracle_catalog import OracleCatalog
from core.sql_policy import SQLPolicy
from core.execution_context import ExecutionContext, SessionRegistry

pytestmark = [pytest.mark.integration, pytest.mark.oracle]

def test_oracle_connection_and_version():
    engine = OracleEngine()
    status = engine.check_connection()
    assert status["connected"] is True
    assert "23" in status["version"]
    assert status["schema"] == "TABULA_DEMO_OWNER"
    engine.close()

def test_oracle_read_only_permissions():
    engine = OracleEngine()
    # Attempting to insert a row under the restricted runtime account MUST fail
    df, err = engine.execute_sql(
        "INSERT INTO USERS (USER_ID, FULL_NAME, EMAIL, CITY, JOINED_DATE) VALUES (9999, 'Test', 'test@example.com', 'City', SYSDATE)"
    )
    assert df is None
    assert err is not None
    assert "ORA-41900" in err or "privilege" in err.lower()
    engine.close()

def test_oracle_100_synthetic_records_loaded():
    engine = OracleEngine()
    df_u, err_u = engine.execute_sql("SELECT COUNT(*) AS total_users FROM USERS")
    assert err_u is None
    assert int(df_u["TOTAL_USERS"].iloc[0]) == 30

    df_c, err_c = engine.execute_sql("SELECT COUNT(*) AS total_claims, SUM(CLAIM_AMOUNT) AS total_amount FROM CLAIMS")
    assert err_c is None
    assert int(df_c["TOTAL_CLAIMS"].iloc[0]) == 70
    assert float(df_c["TOTAL_AMOUNT"].iloc[0]) == 2903820.00
    engine.close()

def test_oracle_three_rahuls_candidates():
    engine = OracleEngine()
    df, err = engine.execute_sql(
        "SELECT USER_ID, FULL_NAME, EMAIL, CITY FROM USERS WHERE LOWER(FULL_NAME) LIKE '%rahul%' ORDER BY USER_ID"
    )
    assert err is None
    assert len(df) == 3

    # Check candidates
    ids = df["USER_ID"].tolist()
    names = df["FULL_NAME"].tolist()
    cities = df["CITY"].tolist()

    assert ids == [1001, 1002, 1003]
    assert names == ["Rahul Sharma", "Rahul Mehta", "Rahul Sharma"]
    assert cities == ["Mumbai", "Pune", "Delhi"]

    # Check claims per candidate
    for uid, expected_claims in [(1001, 6), (1002, 5), (1003, 4)]:
        df_claim, _ = engine.execute_sql(f"SELECT COUNT(*) AS cnt FROM CLAIMS WHERE USER_ID = {uid}")
        assert int(df_claim["CNT"].iloc[0]) == expected_claims

    engine.close()

def test_oracle_zero_claims_users():
    engine = OracleEngine()
    df, err = engine.execute_sql("""
    SELECT u.USER_ID, u.FULL_NAME
    FROM USERS u
    WHERE NOT EXISTS (SELECT 1 FROM CLAIMS c WHERE c.USER_ID = u.USER_ID)
    ORDER BY u.USER_ID
    """)
    assert err is None
    assert len(df) == 3
    assert df["USER_ID"].tolist() == [1028, 1029, 1030]
    engine.close()

def test_oracle_dynamic_catalog_discovery():
    catalog = OracleCatalog()
    meta = catalog.discover_metadata(force_refresh=True)

    tables = meta.get("tables", {})
    assert "USERS" in tables
    assert "CLAIMS" in tables

    # Check primary keys
    assert tables["USERS"]["primary_key"] == ["USER_ID"]
    assert tables["CLAIMS"]["primary_key"] == ["CLAIM_ID"]

    # Check foreign keys
    fks = tables["CLAIMS"]["foreign_keys"]
    assert len(fks) >= 1
    assert fks[0]["column"] == "USER_ID"
    assert fks[0]["ref_table"] == "USERS"
    assert fks[0]["ref_column"] == "USER_ID"

    # Check relationship graph
    rels = meta.get("relationships", [])
    assert len(rels) >= 1
    assert rels[0]["from_table"] == "CLAIMS"
    assert rels[0]["to_table"] == "USERS"
    assert rels[0]["cardinality"] == "N (CLAIMS) : 1 (USERS)"

    catalog.engine.close()

def test_oracle_sql_policy_execution():
    policy = SQLPolicy()
    engine = OracleEngine()

    # Query Rahul Mehta's claims via verified JOIN
    query = """
    SELECT u.USER_ID, u.FULL_NAME, c.CLAIM_ID, c.POLICY_NO, c.CLAIM_TYPE, c.CLAIM_AMOUNT, c.CLAIM_STATUS
    FROM USERS u
    JOIN CLAIMS c ON u.USER_ID = c.USER_ID
    WHERE u.USER_ID = 1002
    ORDER BY c.CLAIM_ID
    """
    res = policy.execute_secure_oracle_query(engine, query)
    assert res.success is True
    assert res.total_rows == 5
    assert res.dataframe is not None
    assert (res.dataframe["USER_ID"] == 1002).all()

    engine.close()

def test_oracle_session_isolation():
    ctx_a = ExecutionContext(session_id="session-a")
    ctx_b = ExecutionContext(session_id="session-b")

    with ctx_a.activate():
        meta_a = ctx_a.register_oracle_source()
        assert ctx_a.data_source_type == "oracle"
        assert "USERS" in meta_a["tables"]

    with ctx_b.activate():
        # Session B registers a local retail dataset
        df_bench = pd.DataFrame({"product": ["A", "B"], "revenue": [100, 200]})
        ctx_b.register_dataset(df_bench, "retail_bench", "Retail Bench")
        assert ctx_b.data_source_type == "duckdb"

    # Verify independent contexts
    assert ctx_a.data_source_type == "oracle"
    assert ctx_b.data_source_type == "duckdb"
    assert ctx_a.active_table != ctx_b.active_table

    ctx_a.close()
    ctx_b.close()
