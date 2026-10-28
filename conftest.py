"""Block network during collection; live tests require per-service opt-in."""

import os

import pytest
import pytest_socket

# Tests must not read a developer's .env, including during module collection.
os.environ["PYTHON_DOTENV_DISABLED"] = "1"


def pytest_addoption(parser):
    parser.addoption("--run-bedrock", action="store_true", help="Allow paid Bedrock tests")
    parser.addoption("--run-nomic", action="store_true", help="Allow local Nomic tests")


def pytest_sessionstart(session):
    pytest_socket.disable_socket()


def pytest_sessionfinish(session, exitstatus):
    pytest_socket.enable_socket()


def pytest_collection_modifyitems(config, items):
    for item in items:
        for service in ("bedrock", "nomic"):
            if service in item.keywords and not config.getoption(f"--run-{service}"):
                item.add_marker(pytest.mark.skip(reason=f"Requires --run-{service}"))


@pytest.fixture
def live_network(request):
    """Only explicitly opted-in, service-marked tests may enable network."""
    services = [name for name in ("bedrock", "nomic") if request.node.get_closest_marker(name)]
    if not services or not all(request.config.getoption(f"--run-{name}") for name in services):
        pytest.fail("Network requires an explicit live-service marker and option")
    pytest_socket.enable_socket()
    try:
        yield
    finally:
        pytest_socket.disable_socket()
