from typing import Optional
from config import SUPERVISOR_MODEL, FALLBACK_MODEL, logger
from core.agents.llm_factory import get_openrouter_model
from core.tools.sql_tools import (
    execute_duckdb_sql,
    inspect_table_schema,
    preview_table_data
)
from core.tools.artifact_store import ArtifactStore

try:
    from strands import Agent
except ImportError:
    class Agent:
        def __init__(self, model, tools, system_prompt):
            self.model = model
            self.tools = tools
            self.system_prompt = system_prompt
        def __call__(self, prompt):
            return f"Agent execution placeholder for: {prompt}"

SQL_SYSTEM_PROMPT = """You are the Analytical SQL Execution Subagent in a multi-agent tabular analytics swarm.
Your job is to generate and execute strict, dialect-compliant DuckDB SQL queries against the active in-memory session to accurately answer user questions.

MANDATORY EXECUTION RULE:
- You MUST ALWAYS call `execute_duckdb_sql(query=...)` to execute your formulated SQL query.
- DO NOT just state the SQL query in text without executing it via `execute_duckdb_sql`.

DuckDB SQL Rules:
1. Column Names: Use exact schema names. For columns with spaces/special characters, wrap in double quotes (e.g., `"product_category"`).
2. String Literals: Use single quotes for text values (e.g., `WHERE region = 'West'`).
3. Mathematical Calculations: Guard against division by zero using `NULLIF(denominator, 0)`.
4. Revenue Calculation: In tables with `revenue`, use `revenue` directly, or `quantity * unit_price * (1.0 - discount_pct)`.
5. Return Rate Calculation: For `return_status` ('Yes'/'No'), return rate percentage is `ROUND(AVG(CASE WHEN return_status = 'Yes' THEN 1.0 ELSE 0.0 END) * 100.0, 2)`.
6. Self-Correction Loop:
   - When `execute_duckdb_sql` executes, if an error traceback is returned, analyze the exact error message, inspect schema/data using `inspect_table_schema` or `preview_table_data`, and formulate a corrected query.
7. Final Summary: State the final SQL query in a ```sql block followed by concise quantitative interpretation of the query results.
"""

def create_sql_agent(api_key: Optional[str] = None, model_id: Optional[str] = None) -> Agent:
    """Instantiates the Analytical SQL Execution Subagent."""
    model = get_openrouter_model(
        model_name=model_id or SUPERVISOR_MODEL,
        api_key=api_key
    )
    tools = [
        execute_duckdb_sql,
        inspect_table_schema,
        preview_table_data
    ]
    return Agent(
        model=model,
        tools=tools,
        system_prompt=SQL_SYSTEM_PROMPT
    )

def run_sql_analyst(task_description: str, api_key: Optional[str] = None, model_id: Optional[str] = None) -> str:
    """Executes a task against the Analytical SQL Engine Agent with automatic fallback on rate limits."""
    store = ArtifactStore.get_instance()
    store.add_trace("SQL Execution Subagent", "Starting SQL Analysis", task_description)
    try:
        agent = create_sql_agent(api_key=api_key, model_id=model_id)
        response = agent(task_description)
        result_text = str(response)
        store.add_trace("SQL Execution Subagent", "Completed", "SQL execution & self-correction complete", status="complete")
        return result_text
    except Exception as e:
        logger.warning(f"SQL agent primary model encountered error ({e}); attempting fallback model...")
        try:
            fallback_agent = create_sql_agent(api_key=api_key, model_id=FALLBACK_MODEL)
            response = fallback_agent(task_description)
            result_text = str(response)
            store.add_trace("SQL Execution Subagent", "Completed (Fallback)", "SQL execution complete via fallback model", status="complete")
            return result_text
        except Exception as fallback_err:
            err = f"SQL Execution Subagent error: {str(fallback_err)}"
            logger.error(err)
            store.add_trace("SQL Execution Subagent", "Error", err, status="error")
            return err
