import os
import time
import threading
from typing import Optional, Dict, Any, List, Tuple, Union
import pandas as pd
from config import (
    ORACLE_HOST,
    ORACLE_PORT,
    ORACLE_SERVICE_NAME,
    ORACLE_USER,
    ORACLE_PASSWORD,
    ORACLE_SCHEMA,
    ORACLE_ALLOWED_SCHEMAS,
    ORACLE_ALLOWED_TABLES,
    ORACLE_MODE,
    ORACLE_POOL_MIN,
    ORACLE_POOL_MAX,
    ORACLE_TIMEOUT_SECONDS,
    logger
)

try:
    import oracledb
    ORACLE_AVAILABLE = True
except ImportError:
    oracledb = None
    ORACLE_AVAILABLE = False


class OracleEngine:
    """
    Hardened, connection-pooled Oracle Database Adapter powered by python-oracledb.
    Features:
    - Pure Thin mode by default (no Instant Client binary dependencies).
    - Optional Thick mode support for legacy Oracle features.
    - Connection pooling with automatic session-state reset.
    - Read-only transaction enforcement ('SET TRANSACTION READ ONLY').
    - Strict query timeout cancellation.
    - Standardized pandas DataFrame conversion.
    """
    _instance: Optional["OracleEngine"] = None

    def __init__(
        self,
        host: Optional[str] = None,
        port: Optional[int] = None,
        service_name: Optional[str] = None,
        user: Optional[str] = None,
        password: Optional[str] = None,
        schema: Optional[str] = None,
        allowed_schemas: Optional[List[str]] = None,
        allowed_tables: Optional[List[str]] = None,
        mode: Optional[str] = None,
        pool_min: Optional[int] = None,
        pool_max: Optional[int] = None,
        timeout_seconds: Optional[float] = None
    ):
        self.host = host or ORACLE_HOST
        self.port = port or ORACLE_PORT
        self.service_name = service_name or ORACLE_SERVICE_NAME
        self.user = user or ORACLE_USER
        self.password = password or os.getenv("ORACLE_PASSWORD") or ORACLE_PASSWORD
        self.schema = (schema or ORACLE_SCHEMA).upper()
        self.allowed_schemas = [s.upper() for s in (allowed_schemas or ORACLE_ALLOWED_SCHEMAS)]
        self.allowed_tables = [t.upper() for t in (allowed_tables or ORACLE_ALLOWED_TABLES)]
        self.mode = (mode or ORACLE_MODE).lower()
        self.pool_min = pool_min or ORACLE_POOL_MIN
        self.pool_max = pool_max or ORACLE_POOL_MAX
        self.timeout_seconds = timeout_seconds or ORACLE_TIMEOUT_SECONDS

        self.dsn = f"{self.host}:{self.port}/{self.service_name}"
        self._pool: Optional[Any] = None
        self._lock = threading.Lock()
        self._version: Optional[str] = None

        if ORACLE_AVAILABLE and self.mode == "thick":
            try:
                oracledb.init_oracle_client()
                logger.info("Oracle Client initialized in Thick mode.")
            except Exception as e:
                logger.warning(f"Could not initialize Thick mode ({e}); falling back to Thin mode.")
                self.mode = "thin"

    @classmethod
    def get_instance(cls) -> "OracleEngine":
        """
        Retrieves the session-scoped OracleEngine from active ExecutionContext if available,
        otherwise returns thread/module singleton.
        """
        try:
            from core.execution_context import get_current_context
            ctx = get_current_context()
            if ctx is not None:
                if not hasattr(ctx, "oracle_engine") or ctx.oracle_engine is None:
                    ctx.oracle_engine = cls()
                return ctx.oracle_engine
        except (ImportError, Exception):
            pass

        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def get_pool(self):
        """Lazily creates and returns the connection pool."""
        if not ORACLE_AVAILABLE:
            raise RuntimeError("python-oracledb is not installed.")

        if self._pool is None:
            with self._lock:
                if self._pool is None:
                    logger.info(f"Creating Oracle connection pool [{self.user}@{self.dsn}] (min={self.pool_min}, max={self.pool_max})")
                    self._pool = oracledb.create_pool(
                        user=self.user,
                        password=self.password,
                        dsn=self.dsn,
                        min=self.pool_min,
                        max=self.pool_max,
                        increment=1
                    )
        return self._pool

    def check_connection(self) -> Dict[str, Any]:
        """Pings the Oracle database and returns connection health and server metadata."""
        if not ORACLE_AVAILABLE:
            return {
                "connected": False,
                "error": "python-oracledb is not installed.",
                "message": "🔴 python-oracledb missing"
            }

        try:
            pool = self.get_pool()
            with pool.acquire() as conn:
                self._version = conn.version
                cur = conn.cursor()
                cur.execute("SELECT 1 FROM DUAL")
                res = cur.fetchone()[0]
                if res == 1:
                    return {
                        "connected": True,
                        "version": conn.version,
                        "dsn": self.dsn,
                        "schema": self.schema,
                        "mode": "Thin" if not hasattr(conn, "is_thin_mode") or conn.is_thin_mode() else "Thick",
                        "message": f"🟢 Oracle Connected ({conn.version} Thin Mode)"
                    }
        except Exception as e:
            return {
                "connected": False,
                "error": str(e),
                "message": f"🔴 Oracle Connection Failed: {str(e)}"
            }

        return {"connected": False, "error": "Unknown connection state", "message": "🔴 Oracle Unavailable"}

    def execute_sql(
        self,
        query: str,
        params: Optional[Union[List[Any], Dict[str, Any], Tuple[Any, ...]]] = None,
        max_rows: Optional[int] = None,
        timeout_seconds: Optional[float] = None
    ) -> Tuple[Optional[pd.DataFrame], Optional[str]]:
        """
        Executes an authorized SQL query against Oracle in a read-only transaction.

        Args:
            query: SQL query to execute.
            params: Parameters for parameter binding.
            max_rows: Optional limit on returned rows.
            timeout_seconds: Query deadline in seconds.

        Returns:
            Tuple[Optional[pd.DataFrame], Optional[str]]: (result_df, error_string)
        """
        if not ORACLE_AVAILABLE:
            return None, "Oracle Error: python-oracledb is not installed."

        clean_query = query.strip().rstrip(";")
        if not clean_query:
            return None, "Oracle Error: Empty query provided."

        effective_timeout = timeout_seconds or self.timeout_seconds
        pool = self.get_pool()

        conn = None
        cur = None
        timer = None
        timed_out = threading.Event()

        try:
            conn = pool.acquire()
            cur = conn.cursor()

            # Set session schema and enforce read-only transaction
            if self.schema:
                cur.execute(f"ALTER SESSION SET CURRENT_SCHEMA = {self.schema}")
            cur.execute("SET TRANSACTION READ ONLY")

            # Setup timeout cancellation
            def cancel_query():
                timed_out.set()
                try:
                    if conn:
                        conn.cancel()
                except Exception:
                    pass

            if effective_timeout and effective_timeout > 0:
                timer = threading.Timer(effective_timeout, cancel_query)
                timer.daemon = True
                timer.start()

            # Execute query with parameters if provided
            if params:
                cur.execute(clean_query, params)
            else:
                cur.execute(clean_query)

            if timed_out.is_set():
                return None, f"Oracle Query Timeout: Execution exceeded {effective_timeout}s limit."

            # Fetch results
            if cur.description is None:
                # No rows (e.g. statement without result set)
                conn.rollback()
                return pd.DataFrame(), None

            col_names = [desc[0] for desc in cur.description]

            if max_rows is not None and max_rows > 0:
                rows = cur.fetchmany(max_rows)
            else:
                rows = cur.fetchall()

            # Convert rows to standard Python types (handling Decimal, LOB, Date)
            clean_rows = []
            for r in rows:
                clean_row = []
                for val in r:
                    if val is None:
                        clean_row.append(None)
                    elif hasattr(val, "read"):
                        # Oracle LOB object
                        clean_row.append(val.read())
                    else:
                        clean_row.append(val)
                clean_rows.append(clean_row)

            df = pd.DataFrame(clean_rows, columns=col_names)

            # Clean rollback to end read-only transaction snapshot
            conn.rollback()
            return df, None

        except Exception as e:
            if timed_out.is_set():
                err_msg = f"Oracle Query Timeout: Execution exceeded {effective_timeout}s limit."
            else:
                err_msg = f"Oracle Execution Error: {str(e)}"
            logger.warning(err_msg)
            if conn:
                try:
                    conn.rollback()
                except Exception:
                    pass
            return None, err_msg

        finally:
            if timer is not None:
                timer.cancel()
            if cur is not None:
                try:
                    cur.close()
                except Exception:
                    pass
            if conn is not None:
                try:
                    pool.release(conn)
                except Exception:
                    pass

    def close(self):
        """Closes the connection pool and releases resources."""
        with self._lock:
            if self._pool is not None:
                try:
                    self._pool.close()
                    logger.info("Oracle connection pool closed.")
                except Exception as e:
                    logger.debug(f"Error closing Oracle pool: {e}")
                self._pool = None

    def get_table_names(self) -> List[str]:
        """Returns authorized table names."""
        if self.allowed_tables:
            return list(self.allowed_tables)
        df, err = self.execute_sql("SELECT table_name FROM user_tables")
        if df is not None and not df.empty:
            return df["TABLE_NAME"].tolist()
        return []

    def get_table_columns(self, table_name: str) -> List[str]:
        """Returns column names for the given table."""
        clean_tbl = table_name.strip().upper()
        df, err = self.execute_sql(f"SELECT column_name FROM user_tab_cols WHERE table_name = '{clean_tbl}' ORDER BY column_id")
        if df is not None and not df.empty:
            return df["COLUMN_NAME"].tolist()
        df_sample, _ = self.execute_sql(f"SELECT * FROM {clean_tbl} WHERE ROWNUM <= 1")
        if df_sample is not None:
            return list(df_sample.columns)
        return []
