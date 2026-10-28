import sys
import os
import time
import json

# Ensure project root is on sys.path
sys.path.insert(0, os.path.abspath("."))
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")

from config import OPENROUTER_API_KEY, OPENROUTER_MODEL, logger
from core.execution_context import ExecutionContext
from core.agents.supervisor import OrchestratorSupervisor

def main():
    print("=" * 80)
    print("TABULAR INTELLIGENCE — LIVE ORACLE MULTI-AGENT EVALUATION")
    print(f"Model: {OPENROUTER_MODEL} (via OpenRouter)")
    print("Backend: Oracle Database 23ai Free (127.0.0.1:1521/FREEPDB1)")
    print("=" * 80)

    ctx = ExecutionContext(session_id="eval-oracle-session")
    with ctx.activate():
        print("\n[Step 1] Connecting to Oracle Database & discovering schema...")
        meta = ctx.register_oracle_source()
        tables = list(meta.get("tables", {}).keys())
        rels = meta.get("relationships", [])
        print(f"Discovered Tables: {tables}")
        for r in rels:
            print(f"Discovered Relationship: {r['from_table']}.{r['from_column']} -> {r['to_table']}.{r['to_column']} ({r['cardinality']})")

        supervisor = OrchestratorSupervisor(
            api_key=OPENROUTER_API_KEY,
            model_config={"supervisor": OPENROUTER_MODEL, "sql": OPENROUTER_MODEL}
        )

        history = []

        # =====================================================================
        # Turn 1: Ambiguous user question
        # =====================================================================
        q1 = "Give me the claim details of user Rahul."
        print("\n" + "-" * 80)
        print(f"Turn 1 Query: \"{q1}\"")
        t0 = time.time()
        res1 = supervisor.analyze(q1, ctx.active_table, conversation_history=history)
        dt1 = time.time() - t0
        print(f"Execution time: {dt1:.1f}s | Status: {res1['status']}")
        print(f"Response Summary:\n{res1['summary']}")
        history.append({"role": "user", "content": q1})
        history.append({"role": "assistant", "content": res1["summary"]})

        # =====================================================================
        # Turn 2: User clarifies identity to User 1002 (Rahul Mehta from Pune)
        # =====================================================================
        q2 = "I want to see claims for Rahul Mehta (User ID 1002 from Pune)."
        print("\n" + "-" * 80)
        print(f"Turn 2 Query (Clarification): \"{q2}\"")
        t0 = time.time()
        res2 = supervisor.analyze(q2, ctx.active_table, conversation_history=history)
        dt2 = time.time() - t0
        print(f"Execution time: {dt2:.1f}s | Status: {res2['status']}")
        print(f"SQL Executed:\n{res2['sql']}")
        print(f"Total Rows Returned: {res2['total_rows']}")
        if res2["dataframe"] is not None:
            print(f"Result DataFrame:\n{res2['dataframe']}")
        print(f"Response Summary:\n{res2['summary']}")
        history.append({"role": "user", "content": q2})
        history.append({"role": "assistant", "content": res2["summary"]})

        # =====================================================================
        # Turn 3: Follow-up question maintaining clarified context
        # =====================================================================
        q3 = "What is his total claim amount and which one is his highest claim?"
        print("\n" + "-" * 80)
        print(f"Turn 3 Query (Follow-up): \"{q3}\"")
        t0 = time.time()
        res3 = supervisor.analyze(q3, ctx.active_table, conversation_history=history)
        dt3 = time.time() - t0
        print(f"Execution time: {dt3:.1f}s | Status: {res3['status']}")
        print(f"SQL Executed:\n{res3['sql']}")
        print(f"Response Summary:\n{res3['summary']}")
        history.append({"role": "user", "content": q3})
        history.append({"role": "assistant", "content": res3["summary"]})

        # =====================================================================
        # Turn 4: Out-of-scope query
        # =====================================================================
        q4 = "Tell me a joke about database administrators."
        print("\n" + "-" * 80)
        print(f"Turn 4 Query (Out of scope): \"{q4}\"")
        t0 = time.time()
        res4 = supervisor.analyze(q4, ctx.active_table, conversation_history=history)
        dt4 = time.time() - t0
        print(f"Execution time: {dt4:.1f}s | Status: {res4['status']}")
        print(f"Response Summary:\n{res4['summary']}")

        # =====================================================================
        # Turn 5: Zero-claims question
        # =====================================================================
        q5 = "Which users have zero filed claims?"
        print("\n" + "-" * 80)
        print(f"Turn 5 Query (Zero Claims): \"{q5}\"")
        t0 = time.time()
        res5 = supervisor.analyze(q5, ctx.active_table, conversation_history=history)
        dt5 = time.time() - t0
        print(f"Execution time: {dt5:.1f}s | Status: {res5['status']}")
        print(f"SQL Executed:\n{res5['sql']}")
        print(f"Total Rows: {res5['total_rows']}")
        if res5["dataframe"] is not None:
            print(f"Result DataFrame:\n{res5['dataframe']}")
        print(f"Response Summary:\n{res5['summary']}")

        # =====================================================================
        # Turn 6: Total claim amount
        # =====================================================================
        q6 = "What is the total claim amount across all 70 claims?"
        print("\n" + "-" * 80)
        print(f"Turn 6 Query (Total Portfolio): \"{q6}\"")
        t0 = time.time()
        res6 = supervisor.analyze(q6, ctx.active_table, conversation_history=history)
        dt6 = time.time() - t0
        print(f"Execution time: {dt6:.1f}s | Status: {res6['status']}")
        print(f"SQL Executed:\n{res6['sql']}")
        print(f"Response Summary:\n{res6['summary']}")

    ctx.close()
    print("\n" + "=" * 80)
    print("ALL 6 LIVE CONVERSATIONS COMPLETED SUCCESSFULLY.")
    print("=" * 80)

if __name__ == "__main__":
    main()
