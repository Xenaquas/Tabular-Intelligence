import traceback
from typing import Optional
import pandas as pd
from core.db_engine import DatabaseEngine
from core.tools.artifact_store import ArtifactStore, safe_df_to_markdown
from config import logger

try:
    from strands import tool
except ImportError:
    def tool(func):
        """Fallback decorator if strands is not imported."""
        return func

@tool
def execute_duckdb_sql(query: str) -> str:
    """
    Executes a strict DuckDB SQL query against the active dataset session.
    If the query fails, catches the DuckDB error and returns the exact error traceback
    so you can inspect the failure and autonomously fix/self-heal the SQL query.
    
    Args:
        query (str): The DuckDB SQL query to execute.
        
    Returns:
        str: On success, returns formatted markdown table and record count.
             On failure, returns detailed DuckDB error message and traceback for query repair.
    """
    engine = DatabaseEngine.get_instance()
    store = ArtifactStore.get_instance()
    
    clean_query = query.strip()
    if not clean_query:
        return "Error: Empty SQL query provided."
        
    store.add_trace("SQL Engine", "Executing Query", clean_query)
    
    try:
        df, error = engine.execute_sql(clean_query)
        if error:
            error_type = "REJECTED_QUERY" if "Policy Violation" in error else "EXECUTION_ERROR"
            status_val = "rejected_query" if "Policy Violation" in error else "failure"
            store.set_error(error, error_type=error_type, status=status_val)
            store.add_trace("SQL Engine", "Execution Error", error, status="error")
            return f"❌ DuckDB SQL Execution Failed ({error_type}):\n```\n{error}\n```\nPlease inspect the table schema and column names to self-heal and correct the SQL query."

        if df is None or df.empty:
            store.set_sql(clean_query, pd.DataFrame(), total_rows=0, is_truncated=False)
            store.set_status("success")
            store.add_trace("SQL Engine", "Completed", "Query returned 0 rows", status="complete")
            return f"Query executed successfully, but returned 0 rows.\nExecuted SQL:\n```sql\n{clean_query}\n```"

        row_count = len(df)
        col_count = len(df.columns)
        store.set_sql(clean_query, df, total_rows=row_count, is_truncated=False)
        store.set_status("success")
        store.add_trace("SQL Engine", "Completed", f"Returned {row_count} rows x {col_count} cols", status="complete")

        # Format preview for LLM text prompt
        preview_limit = min(row_count, 15)
        preview_df = df.head(preview_limit)
        preview_md = safe_df_to_markdown(preview_df, index=False)
        
        summary_msg = f"✅ Query Executed Successfully ({row_count:,} total rows, showing top {preview_limit}):\n\n{preview_md}"
        if row_count > preview_limit:
            summary_msg += f"\n\n*(Note: Displaying first {preview_limit} of {row_count:,} total rows. Full dataset stored in session context.)*"
            
        return summary_msg

    except Exception as e:
        tb = traceback.format_exc()
        err_msg = f"❌ Unhandled Exception during SQL execution:\n{str(e)}\n\nTraceback:\n{tb}"
        store.set_error(err_msg, error_type="UNHANDLED_EXCEPTION", status="failure")
        store.add_trace("SQL Engine", "Execution Exception", str(e), status="error")
        return f"{err_msg}\nPlease analyze the error and formulate an alternate valid SQL query."

@tool
def inspect_table_schema(table_name: str) -> str:
    """
    Returns the DDL table schema and column types for a given table name.
    
    Args:
        table_name (str): Table name in the DuckDB session.
        
    Returns:
        str: DuckDB DDL schema definition.
    """
    engine = DatabaseEngine.get_instance()
    return engine.get_table_schema_ddl(table_name)

@tool
def preview_table_data(table_name: str, limit: int = 3) -> str:
    """
    Fetches sample rows from a table to inspect data formats, date strings, and column value patterns.
    
    Args:
        table_name (str): Table name to preview.
        limit (int): Number of rows to preview (default 3).
        
    Returns:
        str: Markdown table of sample rows.
    """
    engine = DatabaseEngine.get_instance()
    df = engine.get_sample_rows(table_name, limit=limit)
    if df.empty:
        return f"Table `{table_name}` has no data or does not exist."
    return safe_df_to_markdown(df, index=False)

@tool
def execute_oracle_sql(query: str) -> str:
    """
    Executes a strict, read-only Oracle SQL query against the connected Oracle database.
    Enforces AST security policy, single-statement SELECT/CTE, schema authorization,
    and automatic self-healing error reporting.
    
    Args:
        query (str): The Oracle SQL query to execute.
        
    Returns:
        str: On success, returns formatted markdown table and record count.
             On failure, returns detailed Oracle error message and policy diagnostics for query repair.
    """
    from core.oracle_engine import OracleEngine
    from core.sql_policy import SQLPolicy
    
    engine = OracleEngine.get_instance()
    policy = SQLPolicy()
    store = ArtifactStore.get_instance()
    
    clean_query = query.strip()
    if not clean_query:
        return "Error: Empty Oracle SQL query provided."
        
    store.add_trace("Oracle SQL Engine", "Executing Oracle Query", clean_query)
    
    try:
        res = policy.execute_secure_oracle_query(engine, clean_query)
        if not res.success:
            error_msg = res.error or "Unknown Oracle Execution Error"
            error_type = "REJECTED_QUERY" if res.violation_type and "VIOLATION" in str(res.violation_type) else "EXECUTION_ERROR"
            status_val = "rejected_query" if error_type == "REJECTED_QUERY" else "failure"
            store.set_error(error_msg, error_type=error_type, status=status_val)
            store.add_trace("Oracle SQL Engine", "Execution Error", error_msg, status="error")
            return f"❌ Oracle SQL Execution Failed ({error_type}):\n```\n{error_msg}\n```\nPlease inspect the Oracle schema and column names to self-heal and correct the SQL query."

        df = res.dataframe
        if df is None or df.empty:
            store.set_sql(clean_query, pd.DataFrame(), total_rows=0, is_truncated=False)
            store.set_status("success")
            store.add_trace("Oracle SQL Engine", "Completed", "Query returned 0 rows", status="complete")
            return f"Query executed successfully, but returned 0 rows.\nExecuted SQL:\n```sql\n{clean_query}\n```"

        row_count = res.total_rows
        col_count = len(df.columns)
        store.set_sql(clean_query, df, total_rows=row_count, is_truncated=res.is_truncated)
        store.set_status("success")
        store.add_trace("Oracle SQL Engine", "Completed", f"Returned {row_count} rows x {col_count} cols", status="complete")

        preview_limit = min(row_count, 15)
        preview_df = df.head(preview_limit)
        preview_md = safe_df_to_markdown(preview_df, index=False)
        
        summary_msg = f"✅ Oracle Query Executed Successfully ({row_count:,} total rows, showing top {preview_limit}):\n\n{preview_md}"
        if row_count > preview_limit:
            summary_msg += f"\n\n*(Note: Displaying first {preview_limit} of {row_count:,} total rows. Full dataset stored in session context.)*"
            
        return summary_msg

    except Exception as e:
        tb = traceback.format_exc()
        err_msg = f"❌ Unhandled Exception during Oracle SQL execution:\n{str(e)}\n\nTraceback:\n{tb}"
        store.set_error(err_msg, error_type="UNHANDLED_EXCEPTION", status="failure")
        store.add_trace("Oracle SQL Engine", "Execution Exception", str(e), status="error")
        return f"{err_msg}\nPlease analyze the error and formulate an alternate valid Oracle SQL query."

@tool
def inspect_oracle_schema() -> str:
    """
    Returns the dynamic Oracle database schema, column types, primary keys, and foreign-key join relationships.
    
    Returns:
        str: Formatted markdown schema definition and verified foreign-key join paths.
    """
    from core.oracle_catalog import OracleCatalog
    catalog = OracleCatalog()
    return catalog.get_schema_markdown()

@tool
def preview_oracle_table(table_name: str, limit: int = 3) -> str:
    """
    Fetches sample rows from an Oracle table to inspect data patterns, values, and formats.
    
    Args:
        table_name (str): Oracle table name (e.g. 'USERS' or 'CLAIMS').
        limit (int): Number of sample rows to preview (default 3).
        
    Returns:
        str: Markdown table of sample rows.
    """
    from core.oracle_engine import OracleEngine
    engine = OracleEngine.get_instance()
    clean_tbl = table_name.strip().upper()
    df, err = engine.execute_sql(f"SELECT * FROM {clean_tbl} WHERE ROWNUM <= {limit}")
    if err or df is None or df.empty:
        return f"Table `{clean_tbl}` has no data or error: {err}"
    return safe_df_to_markdown(df, index=False)

