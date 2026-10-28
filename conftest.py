"""Block network during collection; live tests require per-service opt-in."""

import os

import pytest
import pytest_socket

# Tests must not read a developer's .env, including during module collection.
os.environ["PYTHON_DOTENV_DISABLED"] = "1"


def pytest_addoption(parser):
    parser.addoption("--run-bedrock", action="store_true", help="Allow paid Bedrock tests")
    parser.addoption("--run-nomic", action="store_true", help="Allow local Nomic tests")
    parser.addoption("--run-oracle", action="store_true", help="Allow local Oracle integration tests")


def pytest_sessionstart(session):
    pytest_socket.disable_socket()


def pytest_sessionfinish(session, exitstatus):
    pytest_socket.enable_socket()


def pytest_collection_modifyitems(config, items):
    for item in items:
        for service in ("bedrock", "nomic", "oracle"):
            if service in item.keywords and not config.getoption(f"--run-{service}"):
                item.add_marker(pytest.mark.skip(reason=f"Requires --run-{service}"))


@pytest.fixture(autouse=True)
def oracle_network(request):
    """Automatically enable socket for oracle-marked tests if --run-oracle is provided."""
    if request.node.get_closest_marker("oracle"):
        if not request.config.getoption("--run-oracle"):
            pytest.skip("Requires --run-oracle")
        from dotenv import dotenv_values
        from pathlib import Path
        env_vals = dotenv_values(Path(__file__).parent / ".env")
        for k, v in env_vals.items():
            if k not in os.environ and v:
                os.environ[k] = v
        import config
        if not config.ORACLE_PASSWORD and "ORACLE_PASSWORD" in os.environ:
            config.ORACLE_PASSWORD = os.environ["ORACLE_PASSWORD"]
        try:
            import core.oracle_engine
            core.oracle_engine.ORACLE_PASSWORD = os.environ.get("ORACLE_PASSWORD", "")
        except Exception:
            pass
        pytest_socket.enable_socket()
        try:
            yield
        finally:
            pytest_socket.disable_socket()
    else:
        yield


@pytest.fixture
def live_network(request):
    """Only explicitly opted-in, service-marked tests may enable network."""
    services = [name for name in ("bedrock", "nomic", "oracle") if request.node.get_closest_marker(name)]
    if not services or not all(request.config.getoption(f"--run-{name}") for name in services):
        pytest.fail("Network requires an explicit live-service marker and option")
    pytest_socket.enable_socket()
    try:
        yield
    finally:
        pytest_socket.disable_socket()
