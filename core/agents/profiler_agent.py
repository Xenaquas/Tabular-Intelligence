from typing import Optional
from config import SUBAGENT_MODEL, FALLBACK_MODEL, logger
from core.agents.llm_factory import get_openrouter_model
from core.tools.profiling_tools import (
    get_dataset_schema,
    get_missing_values_report,
    get_column_cardinality_and_stats,
    preview_dataset_sample
)
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

PROFILER_SYSTEM_PROMPT = """You are the Data Profiling & Ingestion Subagent in a multi-agent tabular analytics swarm.
Your job is to inspect dataset schemas, detect missing/null values, evaluate categorical and numerical column distributions, and report structural facts.

Rules:
1. Always invoke the profiling tools (`get_dataset_schema`, `get_missing_values_report`, `get_column_cardinality_and_stats`, `preview_dataset_sample`) to fetch factual schema metadata.
2. Never hallucinate column names or data types; rely strictly on tool outputs.
3. Summarize findings in concise, structured Markdown tables without bloating context.
"""

def create_profiler_agent(api_key: Optional[str] = None, model_id: Optional[str] = None) -> Agent:
    """Instantiates the Ingestion & Profiling Subagent."""
    model = get_openrouter_model(
        model_name=model_id or SUBAGENT_MODEL,
        api_key=api_key
    )
    tools = [
        get_dataset_schema,
        get_missing_values_report,
        get_column_cardinality_and_stats,
        preview_dataset_sample
    ]
    return Agent(
        model=model,
        tools=tools,
        system_prompt=PROFILER_SYSTEM_PROMPT,
        callback_handler=None
    )

def run_profiler(task_description: str, api_key: Optional[str] = None, model_id: Optional[str] = None) -> str:
    """Executes a task against the Profiler Agent with automatic fallback on rate limits."""
    store = ArtifactStore.get_instance()
    store.add_trace("Profiler Subagent", "Schema & Null Profiling", task_description)
    try:
        agent = create_profiler_agent(api_key=api_key, model_id=model_id)
        response = agent(task_description)
        result_text = str(response)
        store.add_trace("Profiler Subagent", "Completed", "Profiled dataset structure", status="complete")
        return result_text
    except Exception as e:
        logger.warning(f"Profiler agent primary model encountered error ({e}); attempting fallback model...")
        try:
            fallback_agent = create_profiler_agent(api_key=api_key, model_id=FALLBACK_MODEL)
            response = fallback_agent(task_description)
            result_text = str(response)
            store.add_trace("Profiler Subagent", "Completed (Fallback)", "Profiled dataset structure via fallback model", status="complete")
            return result_text
        except Exception as fallback_err:
            err = f"Profiler Subagent error: {str(fallback_err)}"
            logger.error(err)
            store.add_trace("Profiler Subagent", "Error", err, status="error")
            return err
