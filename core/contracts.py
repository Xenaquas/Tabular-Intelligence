"""Lightweight Contracts and Abstract Interfaces for Tabular Intelligence.

Decouples agent tools, statistical computations, and visualization engines
from concrete underlying database implementations (DuckDB, Oracle, etc.).
"""

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Protocol, Tuple, Union, runtime_checkable
import pandas as pd
import numpy as np


@dataclass
class QueryResult:
    """Standardized result envelope returned by any query executor."""
    dataframe: Optional[pd.DataFrame] = None
    total_rows: int = 0
    is_truncated: bool = False
    execution_time_ms: float = 0.0
    provenance_source: str = "unknown"  # e.g., "duckdb", "oracle"
    error: Optional[str] = None
    violation_type: Optional[str] = None

    @property
    def success(self) -> bool:
        return self.error is None and self.dataframe is not None


@runtime_checkable
class DataSource(Protocol):
    """Protocol defining the required capabilities of any data source backend."""

    def execute_sql(
        self,
        query: str,
        params: Optional[Union[List[Any], Dict[str, Any], Tuple[Any, ...]]] = None,
        max_rows: Optional[int] = None,
        timeout_seconds: Optional[float] = None
    ) -> Tuple[Optional[pd.DataFrame], Optional[str]]:
        """Executes a query and returns (result_df, error_str)."""
        ...

    def get_table_names(self) -> List[str]:
        """Returns the list of accessible tables/views in this data source."""
        ...

    def get_table_columns(self, table_name: str) -> List[str]:
        """Returns the list of column names for the specified table."""
        ...


def resolve_data_source() -> DataSource:
    """
    Dynamically resolves the active DataSource from the current ExecutionContext.
    Falls back to the default DatabaseEngine if outside an active context.
    """
    try:
        from core.execution_context import get_current_context
        ctx = get_current_context()
        if ctx is not None:
            if ctx.data_source_type == "oracle":
                if ctx.oracle_engine is None:
                    from core.oracle_engine import OracleEngine
                    ctx.oracle_engine = OracleEngine.get_instance()
                return ctx.oracle_engine
            return ctx.db_engine
    except (ImportError, Exception):
        pass

    from core.db_engine import DatabaseEngine
    return DatabaseEngine.get_instance()


class AnalyticsInput:
    """
    Decoupled data extraction adapter. Provides clean, validated pandas Series
    and DataFrames to statistical and visualization tools independently of
    whether the active store is DuckDB or Oracle.
    """

    @staticmethod
    def get_numeric_series(
        table_name: str,
        column_name: str,
        source: Optional[DataSource] = None
    ) -> Tuple[Optional[pd.Series], Optional[str]]:
        """
        Fetches a non-null numeric series for a given table and column.
        Case-insensitive column matching is applied automatically.
        """
        ds = source or resolve_data_source()
        clean_tbl = table_name.strip()
        clean_col = column_name.strip()

        # Query column directly from the active engine
        sql = f"SELECT {clean_col} FROM {clean_tbl} WHERE {clean_col} IS NOT NULL"
        df, err = ds.execute_sql(sql)
        if err or df is None or df.empty:
            return None, err or f"No non-null data found for column '{clean_col}' in '{clean_tbl}'"

        # Match column case-insensitively
        target_col = None
        for c in df.columns:
            if c.upper() == clean_col.upper():
                target_col = c
                break
        if not target_col:
            target_col = df.columns[0]

        series = pd.to_numeric(df[target_col], errors="coerce").dropna()
        if series.empty:
            return None, f"Column '{clean_col}' contains no valid numeric values."
        return series, None

    @staticmethod
    def get_dataframe(
        table_name: str,
        columns: Optional[List[str]] = None,
        limit: Optional[int] = None,
        source: Optional[DataSource] = None
    ) -> Tuple[Optional[pd.DataFrame], Optional[str]]:
        """
        Fetches a DataFrame for analysis or visualization from the active source.
        Adapts query syntax (e.g. LIMIT vs ROWNUM) according to the engine type.
        """
        ds = source or resolve_data_source()
        clean_tbl = table_name.strip()
        cols_clause = ", ".join(columns) if columns else "*"

        is_oracle = getattr(ds, "mode", None) is not None or "oracle" in type(ds).__name__.lower()
        if limit and limit > 0:
            if is_oracle:
                sql = f"SELECT {cols_clause} FROM {clean_tbl} WHERE ROWNUM <= {limit}"
            else:
                sql = f"SELECT {cols_clause} FROM {clean_tbl} LIMIT {limit}"
        else:
            sql = f"SELECT {cols_clause} FROM {clean_tbl}"

        df, err = ds.execute_sql(sql)
        if err or df is None:
            return None, err or f"Failed to retrieve data from '{clean_tbl}'"
        return df, None
