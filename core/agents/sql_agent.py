from typing import Optional
from config import SUPERVISOR_MODEL, FALLBACK_MODEL, logger
from core.agents.llm_factory import get_openrouter_model
from core.tools.sql_tools import (
    execute_duckdb_sql,
    inspect_table_schema,
    preview_table_data,
    execute_oracle_sql,
    inspect_oracle_schema,
    preview_oracle_table
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
Your job is to generate and execute strict, dialect-compliant SQL queries against the active database backend (DuckDB or Oracle) to accurately answer user questions.

MANDATORY EXECUTION RULE:
- You MUST ALWAYS call the appropriate execution tool (`execute_duckdb_sql` for DuckDB tables, or `execute_oracle_sql` for Oracle database queries).
- DO NOT just state the SQL query in text without executing it via the tool.

Backend Execution Routing:
1. Oracle Relational Database (e.g. USERS, CLAIMS):
   - Call `execute_oracle_sql(query=...)`.
   - Inspect schema & verified relationships using `inspect_oracle_schema()` or `preview_oracle_table(table_name=...)`.
   - Use standard Oracle/ANSI SQL: single quotes for text literals (e.g., `WHERE full_name = 'Rahul Mehta'`).
   - For joins, ALWAYS use verified foreign keys (e.g. `JOIN CLAIMS ON USERS.USER_ID = CLAIMS.USER_ID`).
   - Date formats: use `TO_DATE('YYYY-MM-DD', 'YYYY-MM-DD')` or ANSI date literals `DATE 'YYYY-MM-DD'`.
   - Row limits: use `WHERE ROWNUM <= n` or `FETCH FIRST n ROWS ONLY`.
2. DuckDB In-Memory Session:
   - Call `execute_duckdb_sql(query=...)`.
   - Column names with special chars wrapped in double quotes.
   - Mathematical calculations: guard against division by zero using `NULLIF(denominator, 0)`.

Self-Correction Loop:
- When a query fails or returns an error, inspect the schema diagnostics, analyze the exact failure, and autonomously formulate a corrected query.

Final Summary:
- State the final SQL query in a ```sql block followed by concise quantitative interpretation of the query results.
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
        preview_table_data,
        execute_oracle_sql,
        inspect_oracle_schema,
        preview_oracle_table
    ]
    return Agent(
        model=model,
        tools=tools,
        system_prompt=SQL_SYSTEM_PROMPT,
        callback_handler=None
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
