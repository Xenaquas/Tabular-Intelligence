"""Compile repository sources and import active components with sockets blocked."""

import importlib
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from core.runtime import require_supported_python


def main():
    require_supported_python()
    import os
    import pytest_socket

    os.environ["PYTHON_DOTENV_DISABLED"] = "1"
    pytest_socket.disable_socket()
    try:
        sources = sorted(ROOT.glob("*.py"))
        for folder in ("core", "scripts", "tests"):
            sources.extend(sorted((ROOT / folder).rglob("*.py")))
        for source in sources:
            compile(source.read_text(encoding="utf-8-sig"), str(source), "exec")
        modules = [
            "config", "streamlit", "strands", "boto3", "botocore", "langchain_aws",
            "langchain_core", "duckdb", "numpy", "pandas", "openpyxl", "xlrd",
            "pyarrow", "faiss", "rapidfuzz", "requests", "scipy", "plotly",
            "dotenv", "pydantic", "tabulate", "core.db_engine", "core.metadata_store",
            "core.semantic_index", "core.nomic_embeddings", "core.output_schemas",
            "core.agents.llm_factory", "core.agents.profiler_agent",
            "core.agents.semantic_agent", "core.agents.sql_agent", "core.agents.stats_agent",
            "core.agents.supervisor", "core.tools.artifact_store", "core.tools.profiling_tools",
            "core.tools.sql_tools", "core.tools.stats_tools", "core.tools.viz_tools",
            "test_verification", "test_bedrock_integration", "demo_live_swarm",
        ]
        for name in modules:
            importlib.import_module(name)
        from strands import Agent
        from core.agents import supervisor
        from core.agents.llm_factory import BedrockModel, ChatBedrockConverse

        if supervisor.Agent is not Agent or BedrockModel is None or ChatBedrockConverse is None:
            raise RuntimeError("Real agent/model dependencies did not import")
    finally:
        pytest_socket.enable_socket()
    print(f"Compiled {len(sources)} source files; imported {len(modules)} modules with sockets blocked.")
    print("Legacy modules were compiled only. Streamlit UI and live services were not executed.")


if __name__ == "__main__":
    main()
