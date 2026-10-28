"""Live Evaluation of Tabular Intelligence multi-agent swarm using OpenRouter."""

import os
import sys
import time
import pandas as pd
from dotenv import load_dotenv

if sys.stdout.encoding != 'utf-8':
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

load_dotenv()

from config import OPENROUTER_API_KEY, OPENROUTER_MODEL
from core.execution_context import SessionRegistry
from core.agents.supervisor import OrchestratorSupervisor


def run_evaluation():
    print("=" * 80)
    print("🚀 LIVE EVALUATION: TABULAR INTELLIGENCE WITH OPENROUTER")
    print(f"Model: {OPENROUTER_MODEL}")
    print(f"API Key configured: {bool(OPENROUTER_API_KEY and len(OPENROUTER_API_KEY) > 10)}")
    print("=" * 80)

    # 1. Initialize session execution context
    ctx = SessionRegistry.get_or_create("eval_session_01")
    df = pd.read_csv("data/retail_sales_sample.csv")
    with ctx.activate():
        meta = ctx.register_dataset(df, "retail_sales", "Retail & E-Commerce Benchmark")
        print(f"Registered 'retail_sales': {meta['row_count']} rows, {meta['column_count']} columns.")

    model_config = {
        "supervisor": OPENROUTER_MODEL,
        "sql": OPENROUTER_MODEL,
        "profiler": OPENROUTER_MODEL,
        "semantic": OPENROUTER_MODEL,
        "stats": OPENROUTER_MODEL
    }

    supervisor = OrchestratorSupervisor(
        api_key=OPENROUTER_API_KEY,
        model_config=model_config
    )

    representative_queries = [
        "How many records are in this dataset?",
        "What is the total revenue?",
        "Show revenue by region.",
        "Which products have the highest sales?",
        "Plot monthly sales trends.",
        "Calculate average sales and identify outliers."
    ]

    results_summary = []

    for idx, query in enumerate(representative_queries, 1):
        print(f"\n[{idx}/6] Query: '{query}'")
        start = time.time()
        with ctx.activate():
            res = supervisor.analyze(query, "retail_sales")
        elapsed = round(time.time() - start, 2)

        status = res.get("status", "unknown")
        sql = res.get("sql")
        has_df = res.get("dataframe") is not None and not res.get("dataframe").empty
        has_chart = res.get("chart") is not None
        summary = res.get("summary", "")[:120].replace("\n", " ")

        print(f"  -> Status: {status} ({elapsed}s)")
        if sql:
            print(f"  -> SQL: {sql.strip().replace(chr(10), ' ')[:90]}...")
        if has_df:
            print(f"  -> Result Data: {len(res['dataframe'])} rows")
        if has_chart:
            print(f"  -> Chart: Rendered ({res.get('chart_type', 'Plotly')})")
        print(f"  -> Summary: {summary}...")

        results_summary.append({
            "query": query,
            "status": status,
            "elapsed_s": elapsed,
            "sql": sql,
            "has_data": has_df,
            "has_chart": has_chart,
            "summary_preview": summary
        })

    ctx.close()

    print("\n" + "=" * 80)
    print("EVALUATION SUMMARY TABLE:")
    print(f"{'#':<3} | {'Status':<10} | {'Time':<6} | {'Data':<5} | {'Chart':<5} | {'Query'}")
    print("-" * 80)
    for idx, r in enumerate(results_summary, 1):
        print(f"{idx:<3} | {r['status']:<10} | {r['elapsed_s']:<5.1f}s | {str(r['has_data']):<5} | {str(r['has_chart']):<5} | {r['query']}")
    print("=" * 80)


if __name__ == "__main__":
    run_evaluation()
