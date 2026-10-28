from typing import Optional, Dict, Any
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

def set_agent_context(api_key: Optional[str] = None, model_config: Optional[Dict[str, str]] = None):
    global _CURRENT_API_KEY, _CURRENT_MODEL_CONFIG
    _CURRENT_API_KEY = api_key
    if model_config:
        _CURRENT_MODEL_CONFIG = model_config

@tool
def delegate_to_data_profiler(task_description: str) -> str:
    """
    Delegates schema and null profiling tasks to the Data Profiler Subagent.
    Use this tool when you need column data types, missing value percentages, or dataset structure.
    
    Args:
        task_description (str): Detailed instructions for the Data Profiler.
        
    Returns:
        str: Schema summary, missing value report, or column profiles.
    """
    model_id = _CURRENT_MODEL_CONFIG.get("profiler", SUBAGENT_MODEL)
    return run_profiler(task_description, api_key=_CURRENT_API_KEY, model_id=model_id)

@tool
def delegate_to_semantic_resolver(task_description: str) -> str:
    """
    Delegates entity resolution tasks to the Semantic Value Resolver Subagent.
    Use this tool when the user's question mentions fuzzy, colloquial, or ambiguous entities (e.g. 'corporate buyers', 'west stores', 'office tech')
    to map them to exact categorical column names and SQL string literals via the local FAISS Nomic index.
    
    Args:
        task_description (str): Entities or terms to resolve against the dataset index.
        
    Returns:
        str: Exact column and value matches or deterministic fallback notification.
    """
    model_id = _CURRENT_MODEL_CONFIG.get("semantic", SUBAGENT_MODEL)
    return run_semantic_resolver(task_description, api_key=_CURRENT_API_KEY, model_id=model_id)

@tool
def delegate_to_sql_analyst(task_description: str) -> str:
    """
    Delegates SQL query generation and execution to the Analytical SQL Execution Subagent.
    Use this tool for calculating totals, sums, averages, rankings, group-by breakdowns, and comparisons (e.g. 'Which policy types generate the most revenue?').
    
    Args:
        task_description (str): Instructions specifying the required analytical SQL metrics and table name.
        
    Returns:
        str: Formatted execution results, markdown table, or self-healed SQL query summary.
    """
    model_id = _CURRENT_MODEL_CONFIG.get("sql", SUPERVISOR_MODEL)
    return run_sql_analyst(task_description, api_key=_CURRENT_API_KEY, model_id=model_id)

@tool
def delegate_to_stats_visualizer(task_description: str) -> str:
    """
    Delegates statistical analysis (distributions, spread, mean, median, IQR, percentiles, correlations, outliers) and Plotly chart generation.
    Use this tool whenever the user asks for distributions, histograms, box plots, line charts, bar charts, outliers, or correlation matrices.
    
    Args:
        task_description (str): Instructions specifying the column, distribution statistics required, and visualization type.
        
    Returns:
        str: Computed statistical metrics (Mean, Median, IQR, Min/Max) and confirmation of rendered Plotly chart.
    """
    model_id = _CURRENT_MODEL_CONFIG.get("stats", SUBAGENT_MODEL)
    return run_stats_visualizer(task_description, api_key=_CURRENT_API_KEY, model_id=model_id)

SUPERVISOR_SYSTEM_PROMPT = """You are the Lead Analytical Orchestrator in an autonomous multi-agent Tabular Intelligence Swarm.
You receive natural-language analytical questions, derive execution plans, delegate tasks to specialized subagents via tool wrappers, and deliver comprehensive, fact-grounded, numerical answers.

Subagent Routing Guidelines:
1. For Ranked / Comparative / Aggregation questions (e.g. "Which policy types generate the most revenue?", "Top selling categories"):
   - Delegate to `delegate_to_sql_analyst` to calculate exact sums, counts, and percentages.
   - For visual charts, also delegate to `delegate_to_stats_visualizer` to generate a bar chart.
2. For Distribution / Spread / Central Tendency questions (e.g. "What's the distribution of annual premiums?", "Age distribution"):
   - Delegate to `delegate_to_stats_visualizer` to compute exact distribution metrics (Mean, Median, Standard Deviation, Min, Max, Quartiles) and generate a histogram or box plot.
3. For Outlier / Anomaly questions:
   - Delegate to `delegate_to_stats_visualizer` to detect outliers with bounds and extreme values.
4. For Fuzzy Entity Resolution:
   - Delegate to `delegate_to_semantic_resolver`.

Strict Response Rules:
- FACTUAL & NUMERICAL: Always state the exact numbers, dollar amounts, averages, medians, totals, and percentages derived by your subagents. NEVER give empty generalizations like "check the chart" or "spread is visible in the visual".
- DIRECT & STRUCTURED: Provide the direct answer first, followed by the exact numerical breakdown / key statistics, and a concise 1-sentence analytical takeaway.
- NO HALLUCINATED IMAGES: NEVER output markdown image tags (`![...](...)`). Interactive Plotly charts are automatically rendered by the web UI canvas.
- ESCAPE DOLLAR SIGNS: Write currency amounts cleanly (e.g. $10,200 or USD 10,200).
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
            system_prompt=SUPERVISOR_SYSTEM_PROMPT
        )

    def analyze(self, user_query: str, active_table: str) -> Dict[str, Any]:
        """
        Runs the full multi-agent swarm analysis for a user query with automatic fallback.
        """
        store = ArtifactStore.get_instance()
        store.reset()
        store.add_trace("Orchestrator Supervisor", "Planning", f"Query: '{user_query}' on table '{active_table}'")
        
        prompt = f"""Active Table: `{active_table}`
User Analytical Request: "{user_query}"

Analyze this request and coordinate your subagents to compute exact numerical metrics, execute SQL aggregations/statistics, and render visualizations. Provide a direct, fact-rich answer with exact numbers and clear takeaways."""
        
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
                    "summary": f"❌ **Multi-Agent Orchestration Error**\n\n{err_msg}",
                    "sql": artifacts.get("last_sql"),
                    "dataframe": artifacts.get("last_dataframe"),
                    "chart": artifacts.get("last_chart_spec"),
                    "trace": artifacts.get("agent_trace", []),
                    "error": str(e)
                }

        artifacts = store.get_all()
        return {
            "summary": final_summary,
            "sql": artifacts.get("last_sql"),
            "dataframe": artifacts.get("last_dataframe"),
            "chart": artifacts.get("last_chart_spec"),
            "chart_title": artifacts.get("last_chart_title"),
            "chart_type": artifacts.get("last_chart_type"),
            "trace": artifacts.get("agent_trace", []),
            "error": artifacts.get("error")
        }
