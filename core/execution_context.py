"""Session-Scoped Execution Context and Data Isolation Framework.

Provides per-session isolation for:
- DuckDB analytical database instances
- Uploaded datasets and registered table metadata
- Categorical FAISS semantic vector indexes
- Multi-agent execution artifact stores and traces
- Conversational state and model configuration
"""

import logging
import threading
import time
import uuid
from contextvars import ContextVar
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Set

import pandas as pd

logger = logging.getLogger("TabularSwarm")

_current_context_var: ContextVar[Optional["ExecutionContext"]] = ContextVar("current_execution_context", default=None)


class ExecutionContext:
    """Encapsulates all state, storage, database connections, and artifacts for a single session."""

    def __init__(
        self,
        session_id: Optional[str] = None,
        db_engine: Optional[Any] = None,
        artifact_store: Optional[Any] = None,
        semantic_index: Optional[Any] = None,
        model_config: Optional[Dict[str, str]] = None,
        api_key: Optional[str] = None
    ):
        self.session_id: str = session_id or str(uuid.uuid4())
        self.created_at: float = time.time()
        self.last_accessed_at: float = time.time()
        self._is_closed: bool = False
        self._lock = threading.RLock()

        # Late-imported to avoid circular imports during module bootstrap
        from core.db_engine import DatabaseEngine
        from core.tools.artifact_store import ArtifactStore
        from core.semantic_index import SemanticValueIndex

        # Each session owns an isolated in-memory DuckDB database
        self.db_engine: DatabaseEngine = db_engine or DatabaseEngine(db_path=":memory:")

        # Each session owns an isolated artifact store and event listeners
        self.artifact_store: ArtifactStore = artifact_store or ArtifactStore()

        # Each session owns an isolated categorical semantic index
        self.semantic_index: SemanticValueIndex = semantic_index or SemanticValueIndex()

        # Session-specific model configuration & API credentials
        self.model_config: Dict[str, str] = dict(model_config or {})
        self.api_key: Optional[str] = api_key

        # Session-specific Oracle engine
        self.oracle_engine: Optional[Any] = None
        self.data_source_type: str = "duckdb"  # "duckdb" or "oracle"

        # Active dataset state
        self.active_table: Optional[str] = None
        self.active_dataset_name: Optional[str] = None
        self.table_metadata: Dict[str, Dict[str, Any]] = {}

        # Conversation history
        self.chat_history: List[Dict[str, Any]] = []

    def touch(self):
        """Updates last-accessed timestamp."""
        self.last_accessed_at = time.time()

    def activate(self):
        """Context manager enabling thread-local / async task context resolution for tool calls."""
        self.touch()
        token = _current_context_var.set(self)

        class _ContextScope:
            def __init__(self, ctx_token):
                self.token = ctx_token

            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc_val, exc_tb):
                _current_context_var.reset(self.token)

        return _ContextScope(token)

    def register_dataset(self, df: pd.DataFrame, table_name: str, display_name: str) -> Dict[str, Any]:
        """Registers a dataset into this session's private DuckDB instance and builds its private semantic index."""
        with self._lock:
            self.touch()
            meta = self.db_engine.register_dataframe(df, table_name)
            self.table_metadata[table_name] = meta
            self.active_table = table_name
            self.active_dataset_name = display_name

            # Build semantic index on the cleaned dataset columns
            clean_df = self.db_engine.get_clean_dataframe(table_name)
            if clean_df is not None:
                self.semantic_index.build_index_from_dataframe(clean_df, table_name)
            else:
                self.semantic_index.build_index_from_dataframe(df, table_name)

            logger.info(f"[Session {self.session_id[:8]}] Registered table '{table_name}' ({meta.get('row_count')} rows).")
            return meta

    def register_oracle_source(self, schema_name: Optional[str] = None) -> Dict[str, Any]:
        """Discovers Oracle schema, tables, and relationships, and indexes categorical samples into semantic index."""
        with self._lock:
            self.touch()
            from core.oracle_engine import OracleEngine
            from core.oracle_catalog import OracleCatalog

            if self.oracle_engine is None:
                self.oracle_engine = OracleEngine(schema=schema_name)
            elif schema_name:
                self.oracle_engine.schema = schema_name.upper()

            catalog = OracleCatalog(engine=self.oracle_engine)
            meta = catalog.discover_metadata(force_refresh=True)

            self.data_source_type = "oracle"
            tbl_names = list(meta.get("tables", {}).keys())
            tbl_str = ", ".join(tbl_names)
            self.active_table = tbl_str
            self.active_dataset_name = f"Oracle Relational Schema ({meta.get('schema', self.oracle_engine.schema)})"
            self.table_metadata[tbl_str] = meta

            # Build semantic index over representative sample data
            try:
                samples = catalog.load_table_samples_for_indexing(max_rows_per_table=500)
                if samples:
                    self.semantic_index.build_index_from_tables(samples)
            except Exception as e:
                logger.warning(f"Error indexing Oracle categorical samples into semantic index: {e}")

            logger.info(f"[Session {self.session_id[:8]}] Registered Oracle schema '{meta.get('schema')}' with tables: {tbl_str}.")
            return meta

    def close(self):
        """Releases session resources, closes DuckDB and Oracle pools, and clears artifacts."""
        with self._lock:
            if self._is_closed:
                return
            self._is_closed = True
            try:
                if hasattr(self.db_engine, "close"):
                    self.db_engine.close()
            except Exception as e:
                logger.debug(f"Error closing db_engine: {e}")

            try:
                if self.oracle_engine is not None and hasattr(self.oracle_engine, "close"):
                    self.oracle_engine.close()
            except Exception as e:
                logger.debug(f"Error closing oracle_engine: {e}")

            try:
                self.artifact_store.reset()
                self.artifact_store.clear_listeners()
            except Exception as e:
                logger.debug(f"Error resetting artifact_store: {e}")

            self.chat_history.clear()
            self.table_metadata.clear()
            logger.info(f"[Session {self.session_id[:8]}] Closed and released resources.")


class SessionRegistry:
    """Thread-safe registry managing independent session contexts."""

    _sessions: Dict[str, ExecutionContext] = {}
    _lock = threading.Lock()

    @classmethod
    def get_or_create(
        cls,
        session_id: Optional[str] = None,
        model_config: Optional[Dict[str, str]] = None,
        api_key: Optional[str] = None
    ) -> ExecutionContext:
        """Retrieves existing session context or creates a new isolated context with a secure identifier."""
        with cls._lock:
            sid = session_id or str(uuid.uuid4())
            if sid not in cls._sessions or cls._sessions[sid]._is_closed:
                ctx = ExecutionContext(
                    session_id=sid,
                    model_config=model_config,
                    api_key=api_key
                )
                cls._sessions[sid] = ctx
                return ctx
            return cls._sessions[sid]

    @classmethod
    def get(cls, session_id: str) -> Optional[ExecutionContext]:
        with cls._lock:
            return cls._sessions.get(session_id)

    @classmethod
    def close(cls, session_id: str):
        with cls._lock:
            ctx = cls._sessions.pop(session_id, None)
            if ctx:
                ctx.close()

    @classmethod
    def clear_all(cls):
        """Cleans up and terminates all registered sessions."""
        with cls._lock:
            for ctx in list(cls._sessions.values()):
                ctx.close()
            cls._sessions.clear()

    @classmethod
    def count(cls) -> int:
        with cls._lock:
            return len(cls._sessions)


def get_current_context() -> Optional[ExecutionContext]:
    """Returns the currently active ExecutionContext for this thread / async task, or None."""
    return _current_context_var.get()


def set_current_context(ctx: Optional[ExecutionContext]):
    """Explicitly sets or clears the current ExecutionContext for this thread."""
    _current_context_var.set(ctx)
