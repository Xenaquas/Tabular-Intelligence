from typing import Optional
import pandas as pd
from core.db_engine import DatabaseEngine
from config import logger

from core.tools.artifact_store import safe_df_to_markdown

try:
    from strands import tool
except ImportError:
    def tool(func):
        """Fallback decorator if strands is not imported."""
        return func

@tool
def get_dataset_schema(table_name: str) -> str:
    """
    Inspects and returns the full structural schema, data types, and sample values of a table.
    
    Args:
        table_name (str): The name of the table in DuckDB to inspect.
        
    Returns:
        str: Markdown-formatted table schema with column names, SQL types, and representative sample values.
    """
    engine = DatabaseEngine.get_instance()
    cols = engine.get_table_schema(table_name)
    if not cols:
        return f"Error: Table '{table_name}' was not found in the database session."

    sample_df = engine.get_sample_rows(table_name, limit=3)
    
    lines = [f"### Table Schema for `{table_name}`:"]
    lines.append("| Column Name | DuckDB Type | Nullable | Sample Values |")
    lines.append("| :--- | :--- | :--- | :--- |")
    
    for c in cols:
        cname = c["column_name"]
        ctype = c["column_type"]
        null_status = c.get("null", "YES")
        samples = []
        if not sample_df.empty and cname in sample_df.columns:
            raw_samples = sample_df[cname].dropna().unique().tolist()[:2]
            samples = [f"'{s}'" if isinstance(s, str) else str(s) for s in raw_samples]
        sample_str = ", ".join(samples) if samples else "N/A"
        lines.append(f"| `{cname}` | `{ctype}` | {null_status} | {sample_str} |")
        
    return "\n".join(lines)

@tool
def get_missing_values_report(table_name: str) -> str:
    """
    Computes a comprehensive missing/null values report across all columns for a given table.
    
    Args:
        table_name (str): The name of the table to analyze.
        
    Returns:
        str: Markdown table detailing column-by-column missing count and missing percentage.
    """
    engine = DatabaseEngine.get_instance()
    meta = engine.get_table_metadata(table_name)
    if not meta:
        cols_info = engine.get_table_schema(table_name)
        if not cols_info:
            return f"Error: Table '{table_name}' not found."
        columns = [c["column_name"] for c in cols_info]
    else:
        columns = meta["columns"]

    # Construct aggregation SQL for nulls
    null_exprs = [f"COUNT(*) - COUNT({col}) AS {col}_nulls" for col in columns]
    query = f"SELECT COUNT(*) AS total_rows, {', '.join(null_exprs)} FROM {table_name}"
    
    res_df, err = engine.execute_sql(query)
    if err or res_df is None or res_df.empty:
        return f"Failed to compute missing value report: {err}"
        
    total_rows = int(res_df["total_rows"].iloc[0])
    lines = [f"### Missing Values Report for `{table_name}` (Total Rows: {total_rows:,}):"]
    lines.append("| Column Name | Missing Count | Missing Percentage |")
    lines.append("| :--- | :--- | :--- |")
    
    has_nulls = False
    for col in columns:
        null_count = int(res_df[f"{col}_nulls"].iloc[0])
        null_pct = (null_count / total_rows * 100.0) if total_rows > 0 else 0.0
        if null_count > 0:
            has_nulls = True
            lines.append(f"| `{col}` | **{null_count:,}** | **{null_pct:.2f}%** |")
        else:
            lines.append(f"| `{col}` | 0 | 0.00% |")
            
    if not has_nulls:
        lines.append("\n*Note: Dataset is clean with zero missing values detected.*")
    return "\n".join(lines)

@tool
def get_column_cardinality_and_stats(table_name: str, column_name: str) -> str:
    """
    Profiles an individual column for unique count, top distinct values, and frequency distribution.
    
    Args:
        table_name (str): The name of the table.
        column_name (str): The specific column to profile.
        
    Returns:
        str: Detailed summary of distinct values, top 10 frequencies, and cardinality metric.
    """
    engine = DatabaseEngine.get_instance()
    
    # Check distinct count and top values
    query_top = f"""
    SELECT 
        COALESCE(CAST({column_name} AS VARCHAR), '[NULL]') AS value,
        COUNT(*) AS frequency,
        ROUND(COUNT(*) * 100.0 / (SELECT COUNT(*) FROM {table_name}), 2) AS percentage
    FROM {table_name}
    GROUP BY 1
    ORDER BY frequency DESC
    LIMIT 10;
    """
    
    res_df, err = engine.execute_sql(query_top)
    if err or res_df is None:
        return f"Error profiling column '{column_name}': {err}"
        
    count_query = f"SELECT COUNT(DISTINCT {column_name}) AS distinct_cnt, COUNT(*) AS total_cnt FROM {table_name}"
    cnt_df, _ = engine.execute_sql(count_query)
    distinct_cnt = cnt_df["distinct_cnt"].iloc[0] if cnt_df is not None and not cnt_df.empty else "N/A"
    total_cnt = cnt_df["total_cnt"].iloc[0] if cnt_df is not None and not cnt_df.empty else "N/A"

    lines = [f"### Column Profile: `{column_name}` in `{table_name}`"]
    lines.append(f"- **Distinct Count:** {distinct_cnt:,} / {total_cnt:,} total records")
    lines.append("\n**Top 10 Values by Frequency:**")
    lines.append("| Rank | Value | Count | Share (%) |")
    lines.append("| :--- | :--- | :--- | :--- |")
    
    for i, (_, row) in enumerate(res_df.iterrows(), 1):
        lines.append(f"| {i} | `{row['value']}` | {int(row['frequency']):,} | {row['percentage']}% |")
        
    return "\n".join(lines)

@tool
def preview_dataset_sample(table_name: str, n_rows: int = 5) -> str:
    """
    Retrieves the first N sample records of a table formatted as a Markdown table.
    
    Args:
        table_name (str): The name of the table to preview.
        n_rows (int): Number of sample rows to retrieve (default 5, max 20).
        
    Returns:
        str: Formatted Markdown preview of table records.
    """
    engine = DatabaseEngine.get_instance()
    limit = min(max(1, n_rows), 20)
    df, err = engine.execute_sql(f"SELECT * FROM {table_name} LIMIT {limit}")
    if err or df is None:
        return f"Error fetching sample: {err}"
    if df.empty:
        return f"Table `{table_name}` is empty."
    return safe_df_to_markdown(df, index=False)
