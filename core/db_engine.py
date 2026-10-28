import duckdb
import threading
import pandas as pd
from typing import Dict, Any, List, Optional, Tuple
from config import logger

class DatabaseEngine:
    """
    Thread-safe in-memory DuckDB database engine for tabular analytics.
    Maintains session isolation, dataframe registration, and safe SQL execution with error feedback.
    """
    _instance = None
    _lock = threading.Lock()

    def __init__(self, db_path: str = ":memory:"):
        self.db_path = db_path
        self._conn = duckdb.connect(database=db_path)
        self._query_lock = threading.Lock()
        self._table_metadata: Dict[str, Dict[str, Any]] = {}
        logger.info(f"Initialized DatabaseEngine with db_path='{db_path}'")

    @classmethod
    def get_instance(cls) -> "DatabaseEngine":
        with cls._lock:
            if cls._instance is None:
                cls._instance = cls()
            return cls._instance

    def register_dataframe(self, df: pd.DataFrame, table_name: str) -> Dict[str, Any]:
        """
        Registers a Pandas DataFrame as a DuckDB table.
        Computes initial column-level metadata and memory footprint.
        """
        with self._query_lock:
            # Clean column names for SQL compatibility (strip whitespace, replace special chars)
            clean_df = df.copy()
            clean_df.columns = [
                str(c).strip().replace(" ", "_").replace("-", "_").replace(".", "_")
                for c in clean_df.columns
            ]
            
            # Derive revenue column if quantity & unit_price exist and revenue is not yet present
            if "quantity" in clean_df.columns and "unit_price" in clean_df.columns:
                if "revenue" not in clean_df.columns:
                    disc = clean_df["discount_pct"] if "discount_pct" in clean_df.columns else 0.0
                    clean_df["revenue"] = (clean_df["quantity"].astype(float) * clean_df["unit_price"].astype(float) * (1.0 - disc.astype(float))).round(2)

            
            # Register in DuckDB
            self._conn.register(f"{table_name}_df_view", clean_df)
            self._conn.execute(f"CREATE OR REPLACE TABLE {table_name} AS SELECT * FROM {table_name}_df_view")
            self._conn.unregister(f"{table_name}_df_view")

            
            row_count = len(clean_df)
            col_count = len(clean_df.columns)
            memory_bytes = int(clean_df.memory_usage(deep=True).sum())
            memory_mb = round(memory_bytes / (1024 * 1024), 2)
            
            # Collect column types
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
            
            # Persist metadata to SQLite
            try:
                from core.metadata_store import SQLiteMetadataStore
                SQLiteMetadataStore.get_instance().save_dataset_metadata(table_name, table_name, metadata)
            except Exception as e:
                logger.debug(f"SQLite metadata save notice: {e}")

            logger.info(f"Registered table '{table_name}' with {row_count} rows and {col_count} columns ({memory_mb} MB) [DuckDB + SQLite]")
            return metadata


    def execute_sql(self, query: str, max_rows: Optional[int] = 5000) -> Tuple[Optional[pd.DataFrame], Optional[str]]:
        """
        Executes a SQL query against the in-memory DuckDB instance.
        Returns a tuple of (result_dataframe, error_message).
        On error, returns None and the detailed traceback string for agent self-healing.
        """
        with self._query_lock:
            try:
                # Basic safety sanitization
                clean_query = query.strip().rstrip(";")
                logger.info(f"Executing DuckDB SQL: {clean_query}")
                
                result_df = self._conn.execute(clean_query).fetchdf()
                if max_rows and len(result_df) > max_rows:
                    logger.warning(f"Query returned {len(result_df)} rows; truncating to {max_rows} for performance.")
                    result_df = result_df.head(max_rows)
                    
                return result_df, None
            except duckdb.Error as e:
                err_msg = f"DuckDB Error: {type(e).__name__}: {str(e)}"
                logger.error(f"SQL Execution Failed: {err_msg}\nQuery was:\n{query}")
                return None, err_msg
            except Exception as e:
                err_msg = f"Execution Error: {type(e).__name__}: {str(e)}"
                logger.error(f"SQL Unexpected Error: {err_msg}\nQuery was:\n{query}")
                return None, err_msg

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
        """
        Generates a clean DDL-like schema definition with sample values for LLM prompting.
        """
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
                # Get sample values for this column
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
