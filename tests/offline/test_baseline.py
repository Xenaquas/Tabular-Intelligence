"""Runtime, imports, and test-entry-point contracts without service calls."""

import importlib
import socket
import tomllib
from pathlib import Path

import pytest
from pytest_socket import SocketBlockedError

from core.runtime import require_supported_python


@pytest.mark.parametrize("version", [(3, 10), (3, 11)])
def test_old_python_rejected(version):
    with pytest.raises(RuntimeError, match="Python 3.12"):
        require_supported_python(version)


@pytest.mark.parametrize("version", [(3, 12), (3, 13), (3, 14)])
def test_supported_python_accepted(version):
    require_supported_python(version)


def test_project_requires_python_312():
    root = Path(__file__).resolve().parents[2]
    project = tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8"))
    assert project["project"]["requires-python"] == ">=3.12"


def test_network_is_blocked():
    with pytest.warns(UserWarning, match="socket.socket"):
        with pytest.raises(SocketBlockedError):
            socket.socket()


def test_local_dotenv_loading_is_disabled(tmp_path, monkeypatch):
    import os
    from dotenv import load_dotenv

    monkeypatch.delenv("TABULAR_BASELINE_DOTENV_SENTINEL", raising=False)
    local_env = tmp_path / ".env"
    local_env.write_text("TABULAR_BASELINE_DOTENV_SENTINEL=must_not_load\n", encoding="utf-8")
    assert load_dotenv(local_env, override=True) is False
    assert "TABULAR_BASELINE_DOTENV_SENTINEL" not in os.environ


@pytest.mark.parametrize("name", [
    "config", "core.db_engine", "core.metadata_store", "core.semantic_index",
    "core.nomic_embeddings", "core.output_schemas", "core.agents.llm_factory",
    "core.agents.profiler_agent", "core.agents.semantic_agent", "core.agents.sql_agent",
    "core.agents.stats_agent", "core.agents.supervisor", "core.tools.artifact_store",
    "core.tools.profiling_tools", "core.tools.sql_tools", "core.tools.stats_tools",
    "core.tools.viz_tools", "test_verification", "test_bedrock_integration",
    "demo_live_swarm",
])
def test_active_imports_do_not_construct_clients(name, monkeypatch):
    import boto3
    import requests

    def forbidden(*args, **kwargs):
        pytest.fail("Import attempted service client construction or HTTP request")

    monkeypatch.setattr(boto3, "client", forbidden)
    monkeypatch.setattr(boto3.Session, "client", forbidden)
    monkeypatch.setattr(requests.sessions.Session, "request", forbidden)
    importlib.import_module(name)


def test_real_sdk_and_optional_capabilities_import():
    import strands
    from core.agents import supervisor
    from core.agents.llm_factory import BedrockModel, ChatBedrockConverse
    from core.semantic_index import FAISS_AVAILABLE, RAPIDFUZZ_AVAILABLE
    from core.tools.stats_tools import SCIPY_AVAILABLE

    assert supervisor.Agent is strands.Agent
    assert BedrockModel is not None
    assert ChatBedrockConverse is not None
    assert FAISS_AVAILABLE and RAPIDFUZZ_AVAILABLE and SCIPY_AVAILABLE


def test_supervisor_contract_with_deterministic_agent(engine, monkeypatch):
    from core.agents.supervisor import OrchestratorSupervisor

    def build(supervisor, model_name):
        supervisor.agent = lambda prompt: "Synthetic baseline response"

    monkeypatch.setattr(OrchestratorSupervisor, "_build_agent", build)
    result = OrchestratorSupervisor().analyze("Synthetic question", "fixture")
    assert result["summary"] == "Synthetic baseline response"
    assert result["error"] is None
    assert result["trace"][-1]["action"] == "Synthesis Complete"


def test_offline_entry_point_propagates_failure(monkeypatch):
    import test_verification

    monkeypatch.setattr(pytest, "main", lambda args: 1)
    assert test_verification.main() == 1


def test_live_entry_point_requires_opt_in(monkeypatch):
    import sys
    import test_bedrock_integration

    monkeypatch.setattr(sys, "argv", ["test_bedrock_integration.py"])
    with pytest.raises(SystemExit) as error:
        test_bedrock_integration.main()
    assert error.value.code == 2


def test_live_entry_point_propagates_failure(monkeypatch):
    import sys
    import test_bedrock_integration

    seen = []
    monkeypatch.setattr(sys, "argv", ["test_bedrock_integration.py", "--run-nomic"])
    monkeypatch.setattr(pytest, "main", lambda args: seen.extend(args) or 1)
    assert test_bedrock_integration.main() == 1
    assert "--run-nomic" in seen and "--run-bedrock" not in seen
