import logging
import os
from collections.abc import AsyncGenerator, Generator
from pathlib import Path

import pytest
import pytest_asyncio
from _pytest.config import Config
from _pytest.fixtures import SubRequest
from _pytest.python import Function
from httpx import AsyncClient
from pytest import Parser
from pytest_docker.plugin import Services

from httpd_manager.base import Cluster, Route
from httpd_manager.httpx import HttpxBalancerManager
from httpd_manager.httpx.client import http_client

from .types import EnableAllRoutesHandler
from .utils import port_is_ready

dir_ = Path(__file__).parent
logger = logging.getLogger(__name__)


def pytest_addoption(parser: Parser) -> None:
    parser.addoption("--httpd-version", default="2.4.53")
    parser.addoption("--disable-docker", action="store_true", default=False)


@pytest.fixture(scope="session")
def httpd_version(request: SubRequest) -> str:
    return str(request.config.getoption("httpd_version", "latest"))


@pytest.fixture(scope="session")
def docker_compose_command() -> str:
    return "docker compose"


@pytest.fixture(scope="session")
def docker_setup(httpd_version: str) -> str:
    os.environ["HTTPD_VERSION"] = httpd_version
    return "up --build -d"


def pytest_collection_modifyitems(config: Config, items: list[Function]) -> None:
    if not config.getoption("disable_docker"):
        return
    else:
        _skip_docker = pytest.mark.skip(reason="skip tests that require the Docker Engine")
        for item in items:
            if hasattr(item, "fixturenames") and "docker_services" in item.fixturenames:
                item.add_marker(_skip_docker)


@pytest.fixture(scope="session")
def test_files_dir() -> Path:
    return dir_.joinpath("data")


@pytest.fixture(scope="session")
def httpd_endpoint(docker_ip: str, docker_services: Services) -> str:
    httpd_port = docker_services.port_for("httpd", 80)
    docker_services.wait_until_responsive(timeout=30.0, pause=0.1, check=lambda: port_is_ready(docker_ip, httpd_port))
    return f"http://{docker_ip}:{httpd_port}"


@pytest_asyncio.fixture
async def client() -> AsyncGenerator[AsyncClient, None]:
    async with AsyncClient(auth=("admin", "password")) as _client:
        yield _client


@pytest.fixture(autouse=True)
def set_client(client: AsyncClient) -> Generator[None, None, None]:
    token = http_client.set(client)
    yield
    http_client.reset(token)


@pytest.fixture
def enable_all_routes() -> EnableAllRoutesHandler:
    async def handler(balancer_manager: HttpxBalancerManager, cluster: Cluster[Route]) -> None:
        for route in cluster.routes.values():
            await balancer_manager.edit_route(cluster, route, status_changes={"disabled": False})

    return handler
