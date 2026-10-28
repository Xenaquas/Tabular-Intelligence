import re
import threading
from typing import Any, Dict, List, Optional, Set, Tuple, Union

import duckdb
import pandas as pd

from config import logger
from core.sql_policy import SQLPolicy, SQLQueryResult


def normalize_column_name(raw_name: Any) -> str:
    """Normalizes a raw column name for SQL identifier compatibility.

    - Strips whitespace
    - Replaces non-alphanumeric characters with underscores
    - Prefixes with 'col_' if starting with a digit
    """
    cleaned = str(raw_name).strip()
    cleaned = re.sub(r"[^\w]+", "_", cleaned, flags=re.UNICODE)
    cleaned = cleaned.strip("_")
    if not cleaned or cleaned[0].isdigit():
        cleaned = f"col_{cleaned}"
    return cleaned


class DatabaseEngine:
    """Session-isolated DuckDB engine with centralized AST SQL validation,

    database-level security hardening, and serialized query execution.
    """

    _instance = None
    _lock = threading.Lock()
    _thread_local = threading.local()

    def __init__(self, db_path: str = ":memory:"):
        self.db_path = db_path
        self._conn = duckdb.connect(database=db_path)
        self._query_lock = threading.RLock()
        self._table_metadata: Dict[str, Dict[str, Any]] = {}
        self._cleaned_dfs: Dict[str, pd.DataFrame] = {}

        # Apply defense-in-depth database-level security restrictions
        self.sql_policy = SQLPolicy()
        SQLPolicy.configure_connection(self._conn)

        logger.info(f"Initialized DatabaseEngine with db_path='{db_path}' (External Access Disabled)")

    @classmethod
    def get_instance(cls, session_id: Optional[str] = None) -> "DatabaseEngine":
        """Returns the execution context's engine, a session's engine, or a new isolated engine instance."""
        # 1. Check active ExecutionContext (via contextvars)
        try:
            from core.execution_context import get_current_context
            ctx = get_current_context()
            if ctx is not None and ctx.db_engine is not None:
                return ctx.db_engine
        except ImportError:
            pass

        # 2. Check SessionRegistry if a session_id was explicitly supplied
        if session_id:
            try:
                from core.execution_context import SessionRegistry
                return SessionRegistry.get_or_create(session_id).db_engine
            except ImportError:
                pass

        # 3. Check thread-local active engine if registered in the current test / thread
        active = getattr(cls._thread_local, "active_engine", None)
        if active is not None:
            return active

        # 4. Return a fresh isolated instance to prevent cross-consumer data leakage
        return cls()

    def register_dataframe(self, df: pd.DataFrame, table_name: str) -> Dict[str, Any]:
        """Registers a Pandas DataFrame as a DuckDB table.

        - Normalizes column names consistently and uniquely.
        - Computes initial column-level metadata and memory footprint.
        """
        with self._query_lock:
            # Bind as active engine for this thread if outside of an explicit ExecutionContext
            self._thread_local.active_engine = self

            clean_df = df.copy()

            # Normalize column names and deduplicate collisions
            normalized_cols = [normalize_column_name(c) for c in clean_df.columns]
            unique_cols: List[str] = []
            seen: Dict[str, int] = {}
            for col in normalized_cols:
                if col not in seen:
                    seen[col] = 1
                    unique_cols.append(col)
                else:
                    seen[col] += 1
                    unique_cols.append(f"{col}_{seen[col]}")
            clean_df.columns = unique_cols

            # Derive revenue column if quantity & unit_price exist and revenue is not yet present
            if "quantity" in clean_df.columns and "unit_price" in clean_df.columns:
                if "revenue" not in clean_df.columns:
                    disc = (
                        clean_df["discount_pct"].astype(float)
                        if "discount_pct" in clean_df.columns
                        else 0.0
                    )
                    clean_df["revenue"] = (
                        clean_df["quantity"].astype(float)
                        * clean_df["unit_price"].astype(float)
                        * (1.0 - disc)
                    ).round(2)

            # Store cleaned DataFrame copy for semantic indexing consistency
            self._cleaned_dfs[table_name] = clean_df

            # Register in DuckDB
            view_name = f"{table_name}_df_view"
            self._conn.register(view_name, clean_df)
            self._conn.execute(f"CREATE OR REPLACE TABLE {table_name} AS SELECT * FROM {view_name}")
            self._conn.unregister(view_name)

            row_count = len(clean_df)
            col_count = len(clean_df.columns)
            memory_bytes = int(clean_df.memory_usage(deep=True).sum())
            memory_mb = round(memory_bytes / (1024 * 1024), 2)

            schema_info = self._get_table_schema_internal(table_name)

            metadata = {
                "table_name": table_name,
                "row_count": row_count,
                "column_count": col_count,
                "columns": list(clean_df.columns),
                "memory_bytes": memory_bytes,
                "memory_mb": memory_mb,
                "schema": schema_info
            }
            self._table_metadata[table_name] = metadata

            logger.info(f"Registered table '{table_name}' with {row_count} rows and {col_count} columns ({memory_mb} MB) [DuckDB]")
            return metadata

    def get_clean_dataframe(self, table_name: str) -> Optional[pd.DataFrame]:
        """Returns the in-memory cleaned DataFrame registered for the table."""
        return self._cleaned_dfs.get(table_name)

    def execute_sql(
        self,
        query: str,
        params: Optional[Union[List[Any], Dict[str, Any], Tuple[Any, ...]]] = None,
        max_rows: Optional[int] = None,
        timeout_seconds: Optional[float] = None
    ) -> Tuple[Optional[pd.DataFrame], Optional[str]]:
        """Executes a SQL query against the DuckDB instance with centralized AST security enforcement.

        Returns a tuple of (result_dataframe, error_message).
        When validation or execution fails, returns (None, structured_error_string).
        """
        allowed_tables: Set[str] = set(self._table_metadata.keys())

        # If tables exist in DuckDB but not in _table_metadata (e.g. registered directly in tests), include them
        try:
            raw_tables = self.get_all_tables()
            allowed_tables.update(raw_tables)
        except Exception:
            pass

        q_res: SQLQueryResult = self.sql_policy.execute_secure_query(
            conn=self._conn,
            query=query,
            query_lock=self._query_lock,
            allowed_tables=allowed_tables,
            params=params,
            max_rows=max_rows,
            timeout_seconds=timeout_seconds
        )

        if not q_res.success:
            return None, q_res.error

        return q_res.dataframe, None

    def _get_table_schema_internal(self, table_name: str) -> List[Dict[str, str]]:
        """Internal helper to query table schema directly from DuckDB."""
        try:
            desc_df = self._conn.execute(f"DESCRIBE {table_name}").fetchdf()
            schema_list = []
            for _, row in desc_df.iterrows():
                schema_list.append({
                    "column_name": str(row["column_name"]),
                    "column_type": str(row["column_type"]),
                    "null": str(row.get("null", "YES"))
                })
            return schema_list
        except Exception as e:
            logger.error(f"Failed to fetch schema for table {table_name}: {e}")
            return []

    def get_table_schema(self, table_name: str) -> List[Dict[str, str]]:
        """Public thread-safe method to get column name and type list."""
        with self._query_lock:
            return self._get_table_schema_internal(table_name)

    def get_table_schema_ddl(self, table_name: str) -> str:
        """Generates a clean DDL-like schema definition with sample values for LLM prompting."""
        with self._query_lock:
            cols = self._get_table_schema_internal(table_name)
            if not cols:
                return f"-- Table '{table_name}' does not exist or has no columns."

            sample_df = self._conn.execute(f"SELECT * FROM {table_name} LIMIT 3").fetchdf()

            lines = [f"CREATE TABLE {table_name} ("]
            col_defs = []
            for c in cols:
                cname = c["column_name"]
                ctype = c["column_type"]
                samples = sample_df[cname].dropna().unique().tolist()[:2]
                sample_str = f" -- Samples: {samples}" if samples else ""
                col_defs.append(f"    {cname} {ctype}{sample_str}")

            lines.append(",\n".join(col_defs))
            lines.append(");")
            return "\n".join(lines)

    def get_sample_rows(self, table_name: str, limit: int = 3) -> pd.DataFrame:
        """Fetches first N sample rows from table."""
        with self._query_lock:
            try:
                return self._conn.execute(f"SELECT * FROM {table_name} LIMIT {limit}").fetchdf()
            except Exception as e:
                logger.error(f"Failed to get sample rows for {table_name}: {e}")
                return pd.DataFrame()

    def get_all_tables(self) -> List[str]:
        """Returns list of registered table names in DuckDB."""
        with self._query_lock:
            try:
                df = self._conn.execute("SHOW TABLES").fetchdf()
                if "name" in df.columns:
                    return df["name"].tolist()
                elif len(df.columns) > 0:
                    return df[df.columns[0]].tolist()
                return []
            except Exception as e:
                logger.error(f"Error fetching table list: {e}")
                return []

    def get_table_metadata(self, table_name: str) -> Optional[Dict[str, Any]]:
        """Returns cached or refreshed metadata dictionary for a table."""
        return self._table_metadata.get(table_name)

    def get_table_names(self) -> List[str]:
        """Returns list of registered table names in DuckDB."""
        return self.get_all_tables()

    def get_table_columns(self, table_name: str) -> List[str]:
        """Returns column names for the given table in DuckDB."""
        cols = self.get_table_schema(table_name)
        return [c["column_name"] for c in cols]

    def close(self):
        """Cleanly closes the underlying DuckDB connection."""
        with self._query_lock:
            if getattr(self._thread_local, "active_engine", None) is self:
                self._thread_local.active_engine = None
            try:
                self._conn.close()
            except Exception:
                pass
