from typing import Optional
from config import SUBAGENT_MODEL, FALLBACK_MODEL, logger
from core.agents.llm_factory import get_openrouter_model
from core.semantic_index import SemanticValueIndex
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

_semantic_index_instance: Optional[SemanticValueIndex] = None

def get_semantic_index() -> SemanticValueIndex:
    global _semantic_index_instance
    if _semantic_index_instance is None:
        _semantic_index_instance = SemanticValueIndex()
    return _semantic_index_instance

def set_semantic_index(index: SemanticValueIndex):
    global _semantic_index_instance
    _semantic_index_instance = index

@tool
def lookup_categorical_entity(query_term: str) -> str:
    """
    Searches the FAISS categorical vector index (powered by local Nomic Embeddings) for fuzzy or semantic matches against dataset column values.
    
    Args:
        query_term (str): The entity name, category, or colloquial term mentioned by the user (e.g. 'corporate buyers', 'west stores', 'office tech').
        
    Returns:
        str: The exact column name and SQL string literal match (e.g. customer_segment = 'Corporate') or deterministic fallback if unmatched.
    """
    index = get_semantic_index()
    store = ArtifactStore.get_instance()
    store.add_trace("Semantic Resolver", "FAISS Nomic Lookup", f"Resolving entity: '{query_term}'")
    
    result = index.resolve_entity(query_term)
    store.add_trace("Semantic Resolver", "Resolved Filter", result, status="complete")
    return result

SEMANTIC_SYSTEM_PROMPT = """You are the Semantic Value Resolver Subagent in a multi-agent tabular analytics swarm.
Your mission is to map fuzzy, colloquial, or misspelled user phrases (e.g., "west stores", "corporate buyers", "discounted orders") to exact column names and SQL string literals via the local FAISS index.

Rules:
1. Always call `lookup_categorical_entity` with user terms to find exact matches from the indexed dataset.
2. If matches are returned, report the exact column name and literal SQL condition (e.g., `customer_segment = 'Corporate'`).
3. If no match is found, state explicitly: "No exact match found; proceed with ILIKE or standard SQL filtering".
4. Never hallucinate category values not returned by the tool.
"""

def create_semantic_agent(api_key: Optional[str] = None, model_id: Optional[str] = None) -> Agent:
    """Instantiates the Semantic Value Resolver Subagent."""
    model = get_openrouter_model(
        model_name=model_id or SUBAGENT_MODEL,
        api_key=api_key
    )
    tools = [lookup_categorical_entity]
    return Agent(
        model=model,
        tools=tools,
        system_prompt=SEMANTIC_SYSTEM_PROMPT
    )

def run_semantic_resolver(task_description: str, api_key: Optional[str] = None, model_id: Optional[str] = None) -> str:
    """Executes a task against the Semantic Resolver Agent with fallback handling on rate limits."""
    store = ArtifactStore.get_instance()
    store.add_trace("Semantic Resolver", "Starting Resolution", task_description)
    try:
        agent = create_semantic_agent(api_key=api_key, model_id=model_id)
        response = agent(task_description)
        result_text = str(response)
        store.add_trace("Semantic Resolver", "Completed", "Semantic resolution complete", status="complete")
        return result_text
    except Exception as e:
        logger.warning(f"Semantic resolver primary model encountered error ({e}); attempting fallback...")
        try:
            fallback_agent = create_semantic_agent(api_key=api_key, model_id=FALLBACK_MODEL)
            response = fallback_agent(task_description)
            result_text = str(response)
            store.add_trace("Semantic Resolver", "Completed (Fallback)", "Semantic resolution complete via fallback model", status="complete")
            return result_text
        except Exception as fallback_err:
            # Deterministic direct index lookup fallback
            try:
                direct_res = get_semantic_index().resolve_entity(task_description)
                store.add_trace("Semantic Resolver", "Completed (Direct Lookup)", direct_res, status="complete")
                return direct_res
            except Exception:
                err = f"Semantic Resolver error: {str(fallback_err)}"
                logger.error(err)
                store.add_trace("Semantic Resolver", "Error", err, status="error")
                return err
