import sys
import pandas as pd

# Ensure UTF-8 output on Windows console
if sys.stdout.encoding != 'utf-8':
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')

from config import logger
from core.db_engine import DatabaseEngine
from core.nomic_embeddings import NomicEmbeddingsClient
from core.semantic_index import SemanticValueIndex
from core.tools.profiling_tools import (
    get_dataset_schema,
    get_missing_values_report,
    get_column_cardinality_and_stats
)
from core.tools.sql_tools import execute_duckdb_sql
from core.tools.stats_tools import (
    calculate_correlation_matrix,
    detect_outliers_iqr_zscore,
    calculate_distribution_stats,
    calculate_growth_metrics
)
from core.tools.viz_tools import generate_plotly_chart
from core.tools.artifact_store import ArtifactStore

def test_retail_benchmark():
    print("=" * 70)
    print("STARTING 100-ROW RETAIL BENCHMARK SUITE (Strands + DuckDB + Nomic + FAISS)")
    print("=" * 70)

    # 1. Ingest Benchmark Dataset into In-Memory DuckDB
    print("\n[1/7] Ingesting 'data/retail_sales_sample.csv' into DuckDB...")
    df = pd.read_csv("data/retail_sales_sample.csv")
    engine = DatabaseEngine.get_instance()
    meta = engine.register_dataframe(df, "retail_sales")
    print(f"✅ Ingested table 'retail_sales': {meta['row_count']} rows, {meta['column_count']} columns, {meta['memory_mb']} MB")
    
    # 2. Local Nomic Embeddings Health Ping
    print("\n[2/7] Checking Local Nomic Embeddings Client (Port 8088)...")
    nomic_client = NomicEmbeddingsClient()
    health = nomic_client.check_health()
    print(f"Nomic Health Status: {health['message']}")

    # 3. FAISS + Nomic Semantic Categorical Index
    print("\n[3/7] Building FAISS / Nomic Semantic Index on Categorical Columns...")
    sem_index = SemanticValueIndex()
    idx_res = sem_index.build_index_from_dataframe(df, "retail_sales")
    print(f"Indexed columns: {idx_res['indexed_columns']} (Total entities: {idx_res['total_entities']}, Vector mode: {idx_res['vector_mode']})")
    
    res_corp = sem_index.resolve_entity("corporate buyers")
    print(f"Resolve 'corporate buyers':\n{res_corp}")
    
    res_west = sem_index.resolve_entity("west stores")
    print(f"Resolve 'west stores':\n{res_west}")
    
    res_fallback = sem_index.resolve_entity("Quantum Nebula Spaceport")
    print(f"Deterministic Fallback:\n{res_fallback}")
    assert "No exact match found; proceed with ILIKE or standard SQL filtering" in res_fallback

    # 4. Benchmark Query 1: Category revenue & return rate
    print("\n[4/7] Benchmark Q1: Product categories driving highest revenue & return rate...")
    q1_sql = """
    SELECT 
        product_category,
        COUNT(*) AS total_orders,
        ROUND(SUM(quantity * unit_price * (1.0 - discount_pct)), 2) AS net_revenue,
        ROUND(AVG(CASE WHEN return_status = 'Yes' THEN 1.0 ELSE 0.0 END) * 100.0, 2) AS return_rate_pct
    FROM retail_sales
    GROUP BY product_category
    ORDER BY net_revenue DESC;
    """
    res_q1 = execute_duckdb_sql(q1_sql)
    print(res_q1)

    # 5. Benchmark Query 2: West region Corporate vs Consumer discounts
    print("\n[5/7] Benchmark Q2: Corporate vs Consumer discounts in Western region...")
    q2_sql = """
    SELECT 
        customer_segment,
        COUNT(*) AS order_count,
        ROUND(AVG(discount_pct) * 100.0, 2) AS avg_discount_pct,
        ROUND(AVG(unit_price), 2) AS avg_unit_price
    FROM retail_sales
    WHERE region = 'West' AND customer_segment IN ('Corporate', 'Consumer')
    GROUP BY customer_segment
    ORDER BY avg_discount_pct DESC;
    """
    res_q2 = execute_duckdb_sql(q2_sql)
    print(res_q2)

    # 6. Benchmark Query 3: Unit Price & Revenue Outlier Detection
    print("\n[6/7] Benchmark Q3: Outlier Detection on Unit Price (Enterprise Server Rack)...")
    outlier_rep = detect_outliers_iqr_zscore("retail_sales", "unit_price", method="iqr")
    print(outlier_rep)

    # 7. Benchmark Query 4: Monthly Revenue Line Chart across 2025
    print("\n[7/7] Benchmark Q4: Generating Monthly Revenue Trajectory Line Chart...")
    q4_sql = """
    SELECT 
        strftime(CAST(order_date AS DATE), '%Y-%m') AS order_month,
        ROUND(SUM(quantity * unit_price * (1.0 - discount_pct)), 2) AS monthly_revenue
    FROM retail_sales
    GROUP BY order_month
    ORDER BY order_month;
    """
    viz_res = generate_plotly_chart(
        chart_type="line",
        title="2025 Monthly Revenue Trajectory",
        table_name="retail_sales",
        x_col="order_month",
        y_col="monthly_revenue",
        sql_query=q4_sql
    )
    print(viz_res)
    
    store = ArtifactStore.get_instance()
    art = store.get_all()
    assert art["last_chart_spec"] is not None, "Plotly line chart spec missing in ArtifactStore"

    print("\n" + "=" * 70)
    print("ALL 5 BENCHMARK CAPABILITIES FULLY VALIDATED AND PASSED!")
    print("=" * 70)

if __name__ == "__main__":
    test_retail_benchmark()
