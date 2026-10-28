import re
from typing import Optional, Dict, Any, Tuple, List
from config import SUPERVISOR_MODEL, SUBAGENT_MODEL, FALLBACK_MODEL, OPENROUTER_API_KEY, logger
from core.agents.llm_factory import get_openrouter_model
from core.agents.profiler_agent import run_profiler
from core.agents.semantic_agent import run_semantic_resolver
from core.agents.sql_agent import run_sql_analyst
from core.agents.stats_agent import run_stats_visualizer
from core.tools.artifact_store import ArtifactStore

try:
    from strands import Agent, tool
except ImportError:
    class Agent:
        def __init__(self, model, tools, system_prompt):
            self.model = model
            self.tools = tools
            self.system_prompt = system_prompt
        def __call__(self, prompt):
            return f"Agent execution placeholder for: {prompt}"
    def tool(func):
        return func

_CURRENT_API_KEY: Optional[str] = None
_CURRENT_MODEL_CONFIG: Dict[str, str] = {}

def get_session_model_context() -> Tuple[Optional[str], Dict[str, str]]:
    """Retrieves session-isolated API key and model config if within an ExecutionContext,

    otherwise falls back to module state.
    """
    try:
        from core.execution_context import get_current_context
        ctx = get_current_context()
        if ctx is not None:
            return ctx.api_key or _CURRENT_API_KEY, ctx.model_config or _CURRENT_MODEL_CONFIG
    except ImportError:
        pass
    return _CURRENT_API_KEY, _CURRENT_MODEL_CONFIG

def set_agent_context(api_key: Optional[str] = None, model_config: Optional[Dict[str, str]] = None):
    global _CURRENT_API_KEY, _CURRENT_MODEL_CONFIG
    _CURRENT_API_KEY = api_key
    if model_config:
        _CURRENT_MODEL_CONFIG = model_config
    try:
        from core.execution_context import get_current_context
        ctx = get_current_context()
        if ctx is not None:
            if api_key:
                ctx.api_key = api_key
            if model_config:
                ctx.model_config.update(model_config)
    except ImportError:
        pass

@tool
def delegate_to_data_profiler(task_description: str) -> str:
    """Delegates schema and null profiling tasks to the Data Profiler Subagent.

    Use this tool when you need column data types, missing value percentages, or dataset structure.
    
    Args:
        task_description (str): Detailed instructions for the Data Profiler.
        
    Returns:
        str: Schema summary, missing value report, or column profiles.
    """
    api_key, model_config = get_session_model_context()
    model_id = model_config.get("profiler", SUBAGENT_MODEL)
    return run_profiler(task_description, api_key=api_key, model_id=model_id)

@tool
def delegate_to_semantic_resolver(task_description: str) -> str:
    """Delegates entity resolution tasks to the Semantic Value Resolver Subagent.

    Use this tool when the user's question mentions fuzzy, colloquial, or ambiguous entities (e.g. 'corporate buyers', 'west stores', 'office tech')
    to map them to exact categorical column names and SQL string literals via the local FAISS Nomic index.
    
    Args:
        task_description (str): Entities or terms to resolve against the dataset index.
        
    Returns:
        str: Exact column and value matches or deterministic fallback notification.
    """
    api_key, model_config = get_session_model_context()
    model_id = model_config.get("semantic", SUBAGENT_MODEL)
    return run_semantic_resolver(task_description, api_key=api_key, model_id=model_id)

@tool
def delegate_to_sql_analyst(task_description: str) -> str:
    """Delegates SQL query generation and execution to the Analytical SQL Execution Subagent.

    Use this tool for calculating totals, sums, averages, rankings, group-by breakdowns, and comparisons (e.g. 'Which policy types generate the most revenue?').
    
    Args:
        task_description (str): Instructions specifying the required analytical SQL metrics and table name.
        
    Returns:
        str: Formatted execution results, markdown table, or self-healed SQL query summary.
    """
    api_key, model_config = get_session_model_context()
    model_id = model_config.get("sql", SUPERVISOR_MODEL)
    return run_sql_analyst(task_description, api_key=api_key, model_id=model_id)

@tool
def delegate_to_stats_visualizer(task_description: str) -> str:
    """Delegates statistical analysis (distributions, spread, mean, median, IQR, percentiles, correlations, outliers) and Plotly chart generation.

    Use this tool whenever the user asks for distributions, histograms, box plots, line charts, bar charts, outliers, or correlation matrices.
    
    Args:
        task_description (str): Instructions specifying the column, distribution statistics required, and visualization type.
        
    Returns:
        str: Computed statistical metrics (Mean, Median, IQR, Min/Max) and confirmation of rendered Plotly chart.
    """
    api_key, model_config = get_session_model_context()
    model_id = model_config.get("stats", SUBAGENT_MODEL)
    return run_stats_visualizer(task_description, api_key=api_key, model_id=model_id)

OUT_OF_SCOPE_PATTERNS = [
    r"\btell\s+(me\s+)?a\s+joke\b",
    r"\bweather\s+(today|tomorrow|forecast)\b",
    r"\bwho\s+is\s+the\s+president\b",
    r"\bquantum\s+mechanics\b",
    r"\bignore\s+(all\s+)?(previous\s+)?instructions\b",
    r"\b(write|generate)\s+a\s+(poem|story|song)\b",
    r"\bpasswords?\s+or\s+hidden\b"
]

OUT_OF_SCOPE_REFUSAL_MESSAGE = (
    "I am a specialized Tabular Intelligence assistant scoped strictly to analyzing your connected dataset "
    "and authorized database schema. I cannot assist with general knowledge questions, creative writing, or non-data queries. "
    "Please ask an analytical question about your tables (e.g., summary statistics, claim amounts, user records, or distribution breakdowns)."
)

SUPERVISOR_SYSTEM_PROMPT = """You are the Lead Analytical Orchestrator in an autonomous multi-agent Tabular Intelligence Swarm.
You receive natural-language analytical questions, derive execution plans, delegate tasks to specialized subagents via tool wrappers, and deliver comprehensive, fact-grounded, numerical answers.

Scope & Grounding Boundaries:
- STRICT TABULAR SCOPE: You only answer questions grounded in the active connected dataset or database schema. If asked for jokes, weather, general trivia, politics, or arbitrary code generation, politely refuse and state that you are scoped to the connected tabular data.
- FACT-GROUNDED: Every quantitative claim, record count, or monetary total MUST be directly derived from actual subagent execution results. Never fabricate records or statistics.

Subagent Routing Guidelines:
1. For Ranked / Comparative / Aggregation / Relational Lookup questions:
   - Delegate to `delegate_to_sql_analyst` to execute queries across DuckDB or Oracle database tables.
   - For visual charts, also delegate to `delegate_to_stats_visualizer` to generate a chart.
2. For Distribution / Spread / Central Tendency / Outlier questions:
   - Delegate to `delegate_to_stats_visualizer`.
3. For Fuzzy Entity Resolution:
   - Delegate to `delegate_to_semantic_resolver`.

Entity Disambiguation Protocol (CRITICAL):
- When a user query refers to a person or entity that matches multiple records (for example, "user Rahul" in a database with multiple Rahuls):
  - Delegate to `delegate_to_sql_analyst` to find candidate users (e.g. `SELECT user_id, full_name, email, city FROM USERS WHERE LOWER(full_name) LIKE '%rahul%'`).
  - When multiple distinct candidates are found (e.g. User 1001 Rahul Sharma in Mumbai, User 1002 Rahul Mehta in Pune, User 1003 Rahul Sharma in Delhi):
    * DO NOT arbitrarily choose one candidate.
    * DO NOT merge claim records belonging to different users.
    * Ask the user for clarification, listing each matching candidate with User ID, Full Name, City, and Email!
- Once the user specifies a specific user (e.g., "1002" or "Rahul Mehta"):
  - Query their exact records (e.g. `WHERE user_id = 1002`).
  - State the exact claim count and amounts, ensuring summary text and table agree.

Strict Response Rules:
- FACTUAL & NUMERICAL: Always state the exact numbers, dollar/rupee amounts, averages, totals, and percentages derived by your subagents.
- DIRECT & STRUCTURED: Provide the direct answer first, followed by the exact numerical breakdown, and a concise 1-sentence analytical takeaway.
- NO HALLUCINATED IMAGES: NEVER output markdown image tags (`![...](...)`). Interactive Plotly charts are automatically rendered by the web UI canvas.
- ESCAPE DOLLAR SIGNS: Write currency amounts cleanly (e.g. $10,200 or ₹29,03,820).
- NO FLUFF: Omit conversational filler like "Let me know if you would like to drill deeper".
"""

class OrchestratorSupervisor:
    """
    Master Coordinator Agent managing multi-agent swarm execution for tabular intelligence.
    """
    def __init__(self, api_key: Optional[str] = None, model_config: Optional[Dict[str, str]] = None):
        self.api_key = (api_key or OPENROUTER_API_KEY or "").strip()
        self.model_config = model_config or {}
        set_agent_context(self.api_key, self.model_config)
        
        self.sup_model_id = self.model_config.get("supervisor", SUPERVISOR_MODEL)
        self.tools = [
            delegate_to_data_profiler,
            delegate_to_semantic_resolver,
            delegate_to_sql_analyst,
            delegate_to_stats_visualizer
        ]
        self._build_agent(self.sup_model_id)

    def _build_agent(self, model_name: str):
        self.model = get_openrouter_model(
            model_name=model_name,
            api_key=self.api_key
        )
        self.agent = Agent(
            model=self.model,
            tools=self.tools,
            system_prompt=SUPERVISOR_SYSTEM_PROMPT,
            callback_handler=None
        )

    def analyze(self, user_query: str, active_table: str, conversation_history: Optional[List[Dict[str, Any]]] = None) -> Dict[str, Any]:
        """
        Runs the full multi-agent swarm analysis for a user query with automatic fallback.
        """
        store = ArtifactStore.get_instance()
        store.reset()

        # Deterministic Out-of-Scope Authorization Gate
        clean_user_q = user_query.strip()
        for pat in OUT_OF_SCOPE_PATTERNS:
            if re.search(pat, clean_user_q, re.IGNORECASE):
                store.add_trace("Orchestrator Supervisor", "Scope Rejection", "Query is out of scope of connected tabular data.", status="complete")
                return {
                    "status": "out_of_scope",
                    "summary": OUT_OF_SCOPE_REFUSAL_MESSAGE,
                    "sql": None,
                    "dataframe": None,
                    "total_rows": 0,
                    "is_truncated": False,
                    "chart": None,
                    "trace": store.get_all().get("agent_trace", []),
                    "error": None,
                    "error_type": "OUT_OF_SCOPE"
                }

        store.add_trace("Orchestrator Supervisor", "Planning", f"Query: '{user_query}' on table '{active_table}'")

        recent_context = ""
        if conversation_history:
            turns = []
            for h in conversation_history[-4:]:
                role = "User" if h.get("role") == "user" else "Assistant"
                content = str(h.get("content", "")).strip()
                if content:
                    turns.append(f"{role}: {content[:300]}")
            if turns:
                recent_context = "Recent Conversation History:\n" + "\n".join(turns) + "\n\n"

        prompt = f"""Active Table / Schema: `{active_table}`
{recent_context}User Analytical Request: "{user_query}"

Analyze this request and coordinate your subagents to compute exact numerical metrics, execute SQL aggregations/statistics, and render visualizations. If the user is responding to a previous clarification (e.g. specifying an identity or User ID), query their specific records. Provide a direct, fact-rich answer with exact numbers and clear takeaways."""
        
        try:
            response = self.agent(prompt)
            final_summary = str(response)
            store.add_trace("Orchestrator Supervisor", "Synthesis Complete", "Completed response synthesis", status="complete")
        except Exception as primary_err:
            logger.warning(f"Supervisor primary model '{self.sup_model_id}' failed ({primary_err}); switching to fallback model '{FALLBACK_MODEL}'...")
            store.add_trace("Orchestrator Supervisor", "Fallback Routing", f"Switching to fallback model ({FALLBACK_MODEL}) due to rate limit/connection issue")
            try:
                self._build_agent(FALLBACK_MODEL)
                response = self.agent(prompt)
                final_summary = str(response)
                store.add_trace("Orchestrator Supervisor", "Synthesis Complete", "Completed response synthesis via fallback model", status="complete")
            except Exception as e:
                err_msg = f"Orchestrator Supervisor encountered an error: {str(e)}"
                logger.error(err_msg)
                store.add_trace("Orchestrator Supervisor", "Error", err_msg, status="error")
                artifacts = store.get_all()
                return {
                    "status": "failure",
                    "summary": f"❌ **Multi-Agent Orchestration Error**\n\n{err_msg}",
                    "sql": artifacts.get("last_sql"),
                    "dataframe": artifacts.get("last_dataframe"),
                    "total_rows": artifacts.get("total_rows", 0),
                    "is_truncated": artifacts.get("is_truncated", False),
                    "chart": artifacts.get("last_chart_spec"),
                    "trace": artifacts.get("agent_trace", []),
                    "error": str(e),
                    "error_type": "ORCHESTRATION_ERROR"
                }

        artifacts = store.get_all()
        err = artifacts.get("error")
        status_val = artifacts.get("status", "success")
        if err and status_val == "success":
            status_val = "failure"

        df_out = artifacts.get("last_dataframe")
        total_rows = artifacts.get("total_rows", len(df_out) if df_out is not None else 0)

        return {
            "status": status_val,
            "summary": final_summary,
            "sql": artifacts.get("last_sql"),
            "dataframe": df_out,
            "total_rows": total_rows,
            "is_truncated": artifacts.get("is_truncated", False),
            "chart": artifacts.get("last_chart_spec"),
            "chart_title": artifacts.get("last_chart_title"),
            "chart_type": artifacts.get("last_chart_type"),
            "trace": artifacts.get("agent_trace", []),
            "error": err,
            "error_type": artifacts.get("error_type")
        }
