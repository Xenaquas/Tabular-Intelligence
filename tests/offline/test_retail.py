"""Small-data regression evidence for existing tools, independent of LLMs."""

from io import BytesIO

import numpy as np
import pandas as pd
import pytest

from core.semantic_index import SemanticValueIndex
from core.tools.profiling_tools import get_dataset_schema, get_missing_values_report
from core.tools.sql_tools import execute_duckdb_sql
from core.tools.stats_tools import (
    calculate_correlation_matrix,
    calculate_distribution_stats,
    detect_outliers_iqr_zscore,
)
from core.tools.viz_tools import generate_plotly_chart


def test_retail_aggregation_and_artifact(dataset):
    frame, engine, store = dataset
    sql = """SELECT product_category, COUNT(*) AS orders,
        ROUND(SUM(quantity * unit_price * (1.0 - discount_pct)), 2) AS revenue
        FROM retail_sales GROUP BY product_category ORDER BY product_category"""
    response = execute_duckdb_sql(sql)
    assert "Successfully" in response
    actual = store.get_all()["last_dataframe"]
    assert actual["orders"].sum() == len(frame)
    expected = frame.assign(net=frame.quantity * frame.unit_price * (1 - frame.discount_pct))
    expected = expected.groupby("product_category")["net"].sum().round(2)
    np.testing.assert_allclose(actual.set_index("product_category").revenue, expected)
    assert store.get_all()["last_sql"] == sql


def test_schema_missing_values_and_stats(engine):
    engine.register_dataframe(pd.DataFrame({"x": [1., 2., 3., 4., None], "y": [2., 4., 6., 8., None]}), "metrics")
    assert "DOUBLE" in get_dataset_schema("metrics")
    assert "20.00%" in get_missing_values_report("metrics")
    distribution = calculate_distribution_stats("metrics", "x")
    assert "| **Count** | 4 |" in distribution
    assert "| **Mean** | 2.5000 |" in distribution
    assert "| **Median (Q2)** | 2.5000 |" in distribution
    assert "| **Std Deviation** | 1.2910 |" in distribution
    assert "+1.000" in calculate_correlation_matrix("metrics")


def test_retail_outliers(dataset):
    frame, _, _ = dataset
    values = frame.unit_price
    q1, q3 = values.quantile([0.25, 0.75])
    expected = int(((values < q1 - 1.5 * (q3 - q1)) | (values > q3 + 1.5 * (q3 - q1))).sum())
    assert expected > 0
    assert f"**{expected:,}** records" in detect_outliers_iqr_zscore("retail_sales", "unit_price")


def test_retail_return_rates(dataset):
    frame, engine, _ = dataset
    actual, error = engine.execute_sql("""SELECT product_category,
        AVG(CASE WHEN return_status = 'Yes' THEN 1.0 ELSE 0.0 END) * 100 AS rate
        FROM retail_sales GROUP BY product_category ORDER BY product_category""")
    assert error is None
    expected = frame.assign(returned=frame.return_status.eq("Yes")).groupby("product_category").returned.mean() * 100
    np.testing.assert_allclose(actual.rate, expected)


def test_west_segment_comparison(dataset):
    frame, engine, _ = dataset
    actual, error = engine.execute_sql("""SELECT customer_segment, AVG(discount_pct) AS discount
        FROM retail_sales WHERE region = 'West' AND customer_segment IN ('Corporate', 'Consumer')
        GROUP BY customer_segment ORDER BY customer_segment""")
    assert error is None
    selected = frame[frame.region.eq("West") & frame.customer_segment.isin(["Corporate", "Consumer"])]
    expected = selected.groupby("customer_segment").discount_pct.mean()
    assert actual.customer_segment.tolist() == expected.index.tolist()
    np.testing.assert_allclose(actual.discount, expected)


def test_chart_matches_its_explicit_query(dataset):
    _, engine, store = dataset
    sql = """SELECT strftime(CAST(order_date AS DATE), '%Y-%m') AS month,
        ROUND(SUM(revenue), 2) AS revenue FROM retail_sales GROUP BY month ORDER BY month"""
    response = generate_plotly_chart("line", "Synthetic monthly revenue", "retail_sales", "month", "revenue", sql_query=sql)
    assert "Generated" in response
    expected, error = engine.execute_sql(sql)
    assert error is None
    figure = store.get_all()["last_chart_spec"]
    assert list(figure.data[0].x) == expected.month.tolist()
    np.testing.assert_allclose(figure.data[0].y, expected.revenue)


def test_semantic_fallback_without_http(monkeypatch):
    from core.nomic_embeddings import NomicEmbeddingsClient

    def unavailable(*args, **kwargs):
        raise RuntimeError("Synthetic embedding outage; no HTTP request")

    monkeypatch.setattr(NomicEmbeddingsClient, "get_embeddings", unavailable)
    index = SemanticValueIndex()
    result = index.build_index_from_dataframe(pd.DataFrame({"region": ["West", "East"]}), "fixture")
    assert result["vector_mode"] is False
    assert index.resolve_term("West")[0]["value"] == "West"
    assert "No exact match" in index.resolve_entity("Quantum Nebula Spaceport")


def test_real_faiss_with_synthetic_embeddings(monkeypatch):
    from core.nomic_embeddings import NomicEmbeddingsClient

    def embeddings(client, texts):
        return [[1., 0.] if "West" in text else [0., 1.] for text in texts]

    monkeypatch.setattr(NomicEmbeddingsClient, "get_embeddings", embeddings)
    index = SemanticValueIndex()
    metadata = index.build_index_from_dataframe(pd.DataFrame({"region": ["West", "East"]}), "fixture")
    assert metadata["vector_mode"] is True
    candidate = index.resolve_term("West", top_k=1)[0]
    assert candidate["value"] == "West"
    assert candidate["score"] == pytest.approx(1.)


@pytest.mark.parametrize("file_format", ["csv", "xlsx"])
def test_pandas_file_readers(engine, file_format):
    source = pd.DataFrame({"policy_id": ["P001", "P002"], "premium": [10.25, 20.5]})
    data = BytesIO()
    if file_format == "csv":
        data.write(source.to_csv(index=False).encode("utf-8"))
        data.seek(0)
        loaded = pd.read_csv(data)
    else:
        source.to_excel(data, index=False)
        data.seek(0)
        loaded = pd.read_excel(data)
    engine.register_dataframe(loaded, "policies")
    actual, error = engine.execute_sql("SELECT policy_id, premium FROM policies ORDER BY policy_id")
    assert error is None
    pd.testing.assert_frame_equal(actual, source)


def test_xls_reader_dependency_present():
    import xlrd

    assert callable(xlrd.open_workbook)
