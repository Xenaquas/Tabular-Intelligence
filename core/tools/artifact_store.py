import threading
import logging
import pandas as pd
from typing import Dict, Any, List, Optional, Callable

logger = logging.getLogger("TabularSwarm")

def safe_df_to_markdown(df: pd.DataFrame, index: bool = False) -> str:
    """
    Safely converts a DataFrame to Markdown table format.
    Falls back to manual pipe-separated table if tabulate is not installed.
    """
    if df is None or df.empty:
        return "*Empty DataFrame*"
    try:
        return df.to_markdown(index=index)
    except Exception:
        cols = list(df.columns)
        if index:
            cols = ["index"] + cols
            
        header = "| " + " | ".join(str(c) for c in cols) + " |"
        separator = "| " + " | ".join(["---"] * len(cols)) + " |"
        rows = []
        for idx, row in df.iterrows():
            vals = [str(idx)] if index else []
            for col in df.columns:
                val = row[col]
                vals.append(str(val) if pd.notna(val) else "")
            rows.append("| " + " | ".join(vals) + " |")
        return "\n".join([header, separator] + rows)

class ArtifactStore:
    """
    Thread-safe execution registry and artifact storage for multi-agent runs.
    Tracks intermediate subagent thoughts, executed queries, result DataFrames,
    and Plotly charts to render seamlessly in Streamlit's Live Agent Canvas.
    """
    _instance = None
    _lock = threading.Lock()

    def __init__(self):
        self._data: Dict[str, Any] = {
            "last_sql": None,
            "last_dataframe": None,
            "last_chart_spec": None,
            "last_chart_type": None,
            "last_chart_title": None,
            "agent_trace": [],
            "error": None
        }
        self._listeners: List[Callable[[Dict[str, Any]], None]] = []
        self._store_lock = threading.Lock()

    @classmethod
    def get_instance(cls) -> "ArtifactStore":
        with cls._lock:
            if cls._instance is None:
                cls._instance = cls()
            return cls._instance

    def add_listener(self, listener: Callable[[Dict[str, Any]], None]):
        """Registers a real-time listener for streaming agent trace updates."""
        with self._store_lock:
            if listener not in self._listeners:
                self._listeners.append(listener)

    def remove_listener(self, listener: Callable[[Dict[str, Any]], None]):
        """Removes a registered listener."""
        with self._store_lock:
            if listener in self._listeners:
                self._listeners.remove(listener)

    def clear_listeners(self):
        """Clears all registered listeners."""
        with self._store_lock:
            self._listeners.clear()

    def reset(self):
        """Resets the artifact store for a new conversational turn."""
        with self._store_lock:
            self._data = {
                "last_sql": None,
                "last_dataframe": None,
                "last_chart_spec": None,
                "last_chart_type": None,
                "last_chart_title": None,
                "agent_trace": [],
                "error": None
            }

    def add_trace(self, agent_name: str, action: str, details: str, status: str = "complete"):
        """Appends an execution step to the live trace list and notifies listeners."""
        step_data = {
            "agent": agent_name,
            "action": action,
            "details": details,
            "status": status
        }
        
        # CLI logging
        logger.info(f"[{agent_name}] {action} -> {details[:120] if details else ''}")
        
        with self._store_lock:
            self._data["agent_trace"].append(step_data)
            listeners_copy = list(self._listeners)

        for listener in listeners_copy:
            try:
                listener(step_data)
            except Exception as e:
                logger.debug(f"Error in trace listener: {e}")

    def set_sql(self, sql_query: str, result_df: Optional[pd.DataFrame] = None):
        """Sets the last generated SQL and associated result dataframe."""
        with self._store_lock:
            self._data["last_sql"] = sql_query
            if result_df is not None:
                self._data["last_dataframe"] = result_df

    def set_chart(self, chart_spec: Any, chart_type: str, title: str):
        """Stores the last generated Plotly chart figure or JSON spec."""
        with self._store_lock:
            self._data["last_chart_spec"] = chart_spec
            self._data["last_chart_type"] = chart_type
            self._data["last_chart_title"] = title

    def set_error(self, error_message: str):
        """Sets error details."""
        with self._store_lock:
            self._data["error"] = error_message

    def get_all(self) -> Dict[str, Any]:
        """Returns snapshot of current turn artifacts."""
        with self._store_lock:
            return dict(self._data)
