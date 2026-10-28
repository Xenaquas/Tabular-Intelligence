from typing import Optional
from config import SUBAGENT_MODEL, FALLBACK_MODEL, logger
from core.agents.llm_factory import get_openrouter_model
from core.tools.stats_tools import (
    calculate_correlation_matrix,
    detect_outliers_iqr_zscore,
    calculate_distribution_stats,
    calculate_growth_metrics
)
from core.tools.viz_tools import generate_plotly_chart
from core.tools.artifact_store import ArtifactStore

try:
    from strands import Agent
except ImportError:
    class Agent:
        def __init__(self, model, tools, system_prompt):
            self.model = model
            self.tools = tools
            self.system_prompt = system_prompt
        def __call__(self, prompt):
            return f"Agent execution placeholder for: {prompt}"

STATS_SYSTEM_PROMPT = """You are the Advanced Statistics & Charting Subagent in a multi-agent tabular analytics swarm.
Your job is to compute exact mathematical statistics (mean, median, standard deviation, IQR, percentiles, outliers, correlations) and generate high-contrast Plotly visualizations.

Execution Rules:
1. For distribution, spread, percentiles, or summary questions on a numeric column (e.g. 'distribution of customer age', 'spread of annual premiums'):
   - First call `calculate_distribution_stats` to get exact metrics (Mean, Median, Std Dev, Min, Max, Q1, Q3, IQR, Skewness).
   - Then call `generate_plotly_chart` with `chart_type='histogram'` or `chart_type='box'` (pass the column name as `x_col`).
   - ALWAYS output the exact statistical figures in your response text.
2. For outlier or anomaly detection:
   - Call `detect_outliers_iqr_zscore` and cite the exact cutoff bounds, outlier count, percentage, and extreme values.
3. For correlation or dependency checks:
   - Call `calculate_correlation_matrix` and state the correlation coefficient (r), direction, and p-value.
4. For trends or group breakdowns:
   - Call `generate_plotly_chart` (e.g. 'line' for trends, 'bar' for categorical comparisons, 'pie' for shares).
5. ALWAYS provide factual numbers, percentages, and statistical values in your summary text.
"""

def create_stats_agent(api_key: Optional[str] = None, model_id: Optional[str] = None) -> Agent:
    """Instantiates the Statistical & Visualization Subagent."""
    model = get_openrouter_model(
        model_name=model_id or SUBAGENT_MODEL,
        api_key=api_key
    )
    tools = [
        calculate_correlation_matrix,
        detect_outliers_iqr_zscore,
        calculate_distribution_stats,
        calculate_growth_metrics,
        generate_plotly_chart
    ]
    return Agent(
        model=model,
        tools=tools,
        system_prompt=STATS_SYSTEM_PROMPT,
        callback_handler=None
    )

def run_stats_visualizer(task_description: str, api_key: Optional[str] = None, model_id: Optional[str] = None) -> str:
    """Executes a task against the Statistical & Visualization Agent with fallback on rate limits."""
    store = ArtifactStore.get_instance()
    store.add_trace("Stats & Charting Subagent", "Statistical Computation", task_description)
    try:
        agent = create_stats_agent(api_key=api_key, model_id=model_id)
        response = agent(task_description)
        result_text = str(response)
        store.add_trace("Stats & Charting Subagent", "Completed", "Statistical computation & visualization complete", status="complete")
        return result_text
    except Exception as e:
        logger.warning(f"Stats visualizer primary model encountered error ({e}); attempting fallback...")
        try:
            fallback_agent = create_stats_agent(api_key=api_key, model_id=FALLBACK_MODEL)
            response = fallback_agent(task_description)
            result_text = str(response)
            store.add_trace("Stats & Charting Subagent", "Completed (Fallback)", "Statistical computation complete via fallback model", status="complete")
            return result_text
        except Exception as fallback_err:
            err = f"Stats & Charting Subagent error: {str(fallback_err)}"
            logger.error(err)
            store.add_trace("Stats & Charting Subagent", "Error", err, status="error")
            return err
