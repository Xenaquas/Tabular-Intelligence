import os
import sys
import pandas as pd

if sys.stdout.encoding != 'utf-8':
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')

from config import OPENROUTER_API_KEY
from core.db_engine import DatabaseEngine
from core.semantic_index import SemanticValueIndex
from core.agents.semantic_agent import set_semantic_index
from core.agents.supervisor import OrchestratorSupervisor

def run_live_demonstration():
    print("=" * 80)
    print("🚀 LIVE MULTI-AGENT TABULAR INTELLIGENCE DEMONSTRATION")
    print("=" * 80)

    # 1. Dataset Loading into In-Memory DuckDB
    print("\n[Step 1] Loading 'data/retail_sales_sample.csv' into DuckDB...")
    df = pd.read_csv("data/retail_sales_sample.csv")
    engine = DatabaseEngine.get_instance()
    meta = engine.register_dataframe(df, "retail_sales")
    print(f"Table 'retail_sales' loaded ({meta['row_count']} rows, {meta['column_count']} columns).")

    # 2. Semantic Indexing
    print("\n[Step 2] Building Local Categorical Semantic Index...")
    sem_index = SemanticValueIndex()
    sem_index.build_index_from_dataframe(df, "retail_sales")
    set_semantic_index(sem_index)
    print(f"Indexed columns: {sem_index.indexed_columns}")

    # 3. Initialize Orchestrator Supervisor Swarm
    print("\n[Step 3] Initializing Multi-Agent Swarm with OpenRouter API Key...")
    supervisor = OrchestratorSupervisor(
        api_key=OPENROUTER_API_KEY,
        model_config={
            "supervisor": "deepseek/deepseek-chat",
            "sql": "deepseek/deepseek-chat",
            "profiler": "deepseek/deepseek-chat",
            "semantic": "deepseek/deepseek-chat",
            "stats": "deepseek/deepseek-chat"
        }
    )

    # 4. Run Benchmark Queries
    queries = [
        "Which product categories drive the highest revenue, and what is their return rate?",
        "Are corporate segment buyers in the Western region receiving higher average discounts than consumer buyers?",
        "Identify any revenue or unit price outliers across our transactions."
    ]

    for idx, q in enumerate(queries, 1):
        print(f"\n" + "-" * 80)
        print(f"🔍 [Query {idx}/3]: '{q}'")
        print("-" * 80)
        
        result = supervisor.analyze(q, "retail_sales")
        
        print("\n--- 🧠 AGENT EXECUTION TRACE ---")
        for t in result.get("trace", []):
            print(f"[{t.get('agent')}] {t.get('action')}: {t.get('details')[:100]}")
            
        print("\n--- 💻 EXECUTED SQL ---")
        if result.get("sql"):
            print(result.get("sql"))
        else:
            print("No SQL query executed.")
            
        print("\n--- 📊 EXECUTIVE BRIEFING ---")
        print(result.get("summary"))

    print("\n" + "=" * 80)
    print("✅ LIVE DEMONSTRATION SUCCESSFULLY COMPLETED!")
    print("=" * 80)

if __name__ == "__main__":
    run_live_demonstration()
