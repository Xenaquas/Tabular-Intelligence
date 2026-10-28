"""Tests proving schema-agnostic execution against a secondary multi-table relational schema.

Verifies:
- Dynamic discovery of arbitrary relational schemas without prompt changes
- Correct execution of multi-table joins across 4 tables with composite keys
- Graceful handling of nullable foreign keys (e.g. guest checkout orders)
- Execution against relational database views
- Decoupled statistical metrics and distributions on arbitrary schema tables
"""

import pytest
import duckdb
from core.db_engine import DatabaseEngine
from core.sql_policy import SQLPolicy
from core.execution_context import ExecutionContext
from core.contracts import AnalyticsInput, resolve_data_source
from core.tools.stats_tools import calculate_distribution_stats, detect_outliers_iqr_zscore
from tests.fixtures.ecommerce_schema import create_ecommerce_fixture


@pytest.fixture
def ecommerce_context():
    """Sets up an ExecutionContext pre-populated with the e-commerce relational schema."""
    ctx = ExecutionContext()
    # Populate the session's private DuckDB with the schema
    create_ecommerce_fixture(ctx.db_engine._conn)
    with ctx.activate():
        yield ctx
    ctx.close()


def test_schema_discovery_on_unseen_tables(ecommerce_context):
    """Verifies that the database engine discovers all tables and views dynamically."""
    engine = DatabaseEngine.get_instance()
    tables = engine.get_all_tables()
    assert "customers" in tables
    assert "products" in tables
    assert "orders" in tables
    assert "order_items" in tables
    assert "v_order_summary" in tables


def test_multi_table_relational_join_execution(ecommerce_context):
    """Executes a 4-table join with aggregations and composite key traversal."""
    policy = SQLPolicy()
    engine = DatabaseEngine.get_instance()

    query = """
    SELECT 
        c.customer_name,
        c.loyalty_tier,
        p.category,
        SUM(oi.quantity * oi.unit_price) AS total_spent
    FROM customers c
    JOIN orders o ON c.customer_id = o.customer_id
    JOIN order_items oi ON o.order_id = oi.order_id
    JOIN products p ON oi.product_id = p.product_id
    GROUP BY c.customer_name, c.loyalty_tier, p.category
    ORDER BY total_spent DESC
    """
    res = policy.execute_secure_query(
        conn=engine._conn,
        query=query,
        query_lock=engine._query_lock,
        allowed_tables={"customers", "orders", "order_items", "products"}
    )
    assert res.success is True
    assert res.total_rows > 0
    df = res.dataframe
    assert "customer_name" in df.columns
    assert "total_spent" in df.columns
    # Alice Walker should have top spend on electronics
    top_customer = df.iloc[0]["customer_name"]
    assert top_customer == "Alice Walker"


def test_nullable_foreign_key_guest_orders(ecommerce_context):
    """Verifies queries correctly handle orders with NULL customer_id."""
    policy = SQLPolicy()
    engine = DatabaseEngine.get_instance()

    query = """
    SELECT 
        o.order_id,
        COALESCE(c.customer_name, 'GUEST') AS customer_display,
        o.total_amount
    FROM orders o
    LEFT JOIN customers c ON o.customer_id = c.customer_id
    WHERE o.customer_id IS NULL
    """
    res = policy.execute_secure_query(
        conn=engine._conn,
        query=query,
        query_lock=engine._query_lock,
        allowed_tables={"customers", "orders"}
    )
    assert res.success is True
    assert res.total_rows == 1
    assert res.dataframe.iloc[0]["customer_display"] == "GUEST"
    assert res.dataframe.iloc[0]["order_id"] == 1005


def test_relational_view_query(ecommerce_context):
    """Verifies querying directly against relational database views."""
    policy = SQLPolicy()
    engine = DatabaseEngine.get_instance()

    query = "SELECT * FROM v_order_summary ORDER BY order_id"
    res = policy.execute_secure_query(
        conn=engine._conn,
        query=query,
        query_lock=engine._query_lock,
        allowed_tables={"v_order_summary", "orders", "customers", "order_items"}
    )
    assert res.success is True
    assert res.total_rows == 5


def test_statistical_tools_on_unseen_schema(ecommerce_context):
    """Verifies calculate_distribution_stats and outlier detection on the unseen products table."""
    with ecommerce_context.activate():
        # Compute distribution stats on products.unit_price
        dist_report = calculate_distribution_stats("products", "unit_price")
        assert "Distribution Metrics for `unit_price`" in dist_report
        assert "| **Count** | 5 |" in dist_report

        # Outlier detection on orders.total_amount
        outlier_report = detect_outliers_iqr_zscore("orders", "total_amount")
        assert "Outlier Detection Report: `total_amount` in `orders`" in outlier_report
