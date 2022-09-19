import logging
import os
import socket
from collections import namedtuple
from pathlib import Path
from typing import Callable

import pytest
from httpd_manager import Client


dir_ = Path(__file__).parent
logger = logging.getLogger(__name__)


def pytest_addoption(parser):
    parser.addoption("--httpd-version", default="2.4.53")
    parser.addoption("--disable-docker", action="store_true", default=False)


def port_is_ready(host: str, port: int, timeout: int = 5) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError as ex:
        return False


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.fixture(scope="session")
def httpd_version(request):
    return request.config.getoption("httpd_version")


@pytest.fixture(scope="session")
def docker_setup(httpd_version):
    os.environ["HTTPD_VERSION"] = httpd_version
    return "up --build -d"


def pytest_collection_modifyitems(config, items):
    if not config.getoption("disable_docker"):
        return
    else:
        _skip_docker = pytest.mark.skip(
            reason="skip tests that require the Docker Engine"
        )
        for item in items:
            if hasattr(item, "fixturenames") and "docker_services" in item.fixturenames:
                item.add_marker(_skip_docker)


@pytest.fixture(scope="session")
def test_files_dir():
    return dir_.joinpath("data")


@pytest.fixture(scope="session")
def create_client(docker_ip, docker_services) -> Callable:
    httpd_port = docker_services.port_for("httpd", 80)
    docker_services.wait_until_responsive(
        timeout=30.0, pause=0.1, check=lambda: port_is_ready(docker_ip, httpd_port)
    )

    def handler(base_url=None, **client_kwargs):
        base_url = base_url if base_url else f"http://{docker_ip}:{httpd_port}"
        return Client(
            base_url=base_url, auth=("admin", "password"), timeout=0.25, **client_kwargs
        )

    return handler


@pytest.fixture(scope="session")
def client(create_client) -> Client:
    return create_client()


@pytest.fixture(scope="session")
def enable_all_routes():
    async def handler(balancer_manager, cluster):
        for route in cluster.routes.values():
            await balancer_manager.edit_route(
                cluster, route, status_changes={"disabled": False}
            )

    return handler
