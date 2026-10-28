import sqlite3
import json
import threading
from pathlib import Path
from typing import Dict, Any, List, Optional
from config import DATA_DIR, logger

class SQLiteMetadataStore:
    """
    Dedicated SQLite storage engine for persisting table metadata, dataset catalogs,
    and query execution history. DuckDB remains the primary in-memory analytical engine.
    """
    _instance = None
    _lock = threading.Lock()

    def __init__(self, db_path: Optional[str] = None):
        if db_path is None:
            DATA_DIR.mkdir(parents=True, exist_ok=True)
            self.db_path = str(DATA_DIR / "metadata.db")
        else:
            self.db_path = db_path
            
        self._init_db()
        logger.info(f"Initialized SQLiteMetadataStore at '{self.db_path}'")

    @classmethod
    def get_instance(cls) -> "SQLiteMetadataStore":
        with cls._lock:
            if cls._instance is None:
                cls._instance = cls()
            return cls._instance

    def _get_connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, timeout=10)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self):
        """Creates the metadata catalog tables if they do not exist."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS dataset_catalog (
                    table_name TEXT PRIMARY KEY,
                    display_name TEXT NOT NULL,
                    row_count INTEGER,
                    column_count INTEGER,
                    memory_mb REAL,
                    columns_json TEXT,
                    schema_json TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS query_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    table_name TEXT,
                    user_prompt TEXT NOT NULL,
                    executed_sql TEXT,
                    execution_status TEXT,
                    row_count INTEGER,
                    duration_ms REAL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            conn.commit()

    def save_dataset_metadata(self, table_name: str, display_name: str, meta: Dict[str, Any]):
        """Persists or updates dataset metadata in SQLite."""
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    INSERT OR REPLACE INTO dataset_catalog 
                    (table_name, display_name, row_count, column_count, memory_mb, columns_json, schema_json, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                """, (
                    table_name,
                    display_name,
                    meta.get("row_count", 0),
                    meta.get("column_count", 0),
                    meta.get("memory_mb", 0.0),
                    json.dumps(meta.get("columns", [])),
                    json.dumps(meta.get("schema", {}))
                ))
                conn.commit()
        except Exception as e:
            logger.error(f"Failed to save metadata in SQLite for table '{table_name}': {e}")

    def log_query_execution(
        self,
        table_name: str,
        user_prompt: str,
        executed_sql: Optional[str] = None,
        status: str = "success",
        row_count: int = 0,
        duration_ms: float = 0.0
    ):
        """Logs a query execution record into SQLite query history."""
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    INSERT INTO query_history (table_name, user_prompt, executed_sql, execution_status, row_count, duration_ms)
                    VALUES (?, ?, ?, ?, ?, ?)
                """, (table_name, user_prompt, executed_sql, status, row_count, duration_ms))
                conn.commit()
        except Exception as e:
            logger.error(f"Failed to log query history in SQLite: {e}")

    def get_dataset_metadata(self, table_name: str) -> Optional[Dict[str, Any]]:
        """Retrieves stored dataset metadata from SQLite."""
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT * FROM dataset_catalog WHERE table_name = ?", (table_name,))
                row = cursor.fetchone()
                if row:
                    return {
                        "table_name": row["table_name"],
                        "display_name": row["display_name"],
                        "row_count": row["row_count"],
                        "column_count": row["column_count"],
                        "memory_mb": row["memory_mb"],
                        "columns": json.loads(row["columns_json"]) if row["columns_json"] else [],
                        "schema": json.loads(row["schema_json"]) if row["schema_json"] else {},
                        "created_at": row["created_at"]
                    }
        except Exception as e:
            logger.error(f"Failed to retrieve metadata from SQLite: {e}")
        return None

    def list_datasets(self) -> List[Dict[str, Any]]:
        """Returns all registered datasets in SQLite catalog."""
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT * FROM dataset_catalog ORDER BY created_at DESC")
                return [dict(row) for row in cursor.fetchall()]
        except Exception as e:
            logger.error(f"Failed to list datasets from SQLite: {e}")
            return []
