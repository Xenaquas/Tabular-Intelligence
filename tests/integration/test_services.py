"""Only explicit service flags allow these tests to contact real endpoints."""

import math

import pytest


@pytest.mark.integration
@pytest.mark.bedrock
def test_real_bedrock_synthetic_response(live_network):
    from strands import Agent
    from core.agents.llm_factory import get_bedrock_model

    agent = Agent(model=get_bedrock_model(), callback_handler=None)
    result = agent("Synthetic connectivity test. Reply with exactly BASELINE_OK.")
    assert str(result).strip() == "BASELINE_OK"


@pytest.mark.integration
@pytest.mark.nomic
def test_real_nomic_synthetic_embeddings(live_network):
    from core.nomic_embeddings import NomicEmbeddingsClient

    client = NomicEmbeddingsClient()
    health = client.check_health()
    assert health["connected"] and health["supported"], "Nomic is not ready"
    vectors = client.get_embeddings(["search_query: synthetic policy", "search_document: synthetic claim"])
    assert len(vectors) == 2
    assert len(vectors[0]) > 0 and len(vectors[0]) == len(vectors[1])
    assert all(math.isfinite(value) for vector in vectors for value in vector)
