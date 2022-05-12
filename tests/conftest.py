import asyncio
import json
import logging
import os
import random
import time
from collections import namedtuple
from pathlib import Path
from typing import Callable

import docker
import httpx
import pytest
import pytest_asyncio
from httpd_manager import BalancerManager, Client

from . import docker_helpers


dir_ = Path(__file__).parent
logger = logging.getLogger(__name__)
# logging.basicConfig(level=logging.DEBUG)


def pytest_addoption(parser):
    parser.addoption("--httpd-version", default="2.4.48")
    parser.addoption("--disable-docker", action="store_true", default=False)


@pytest.fixture(scope="session")
def httpd_version(request):
    return request.config.getoption("httpd_version")


def pytest_collection_modifyitems(config, items):
    if not config.getoption("disable_docker"):
        return
    else:
        _skip_docker = pytest.mark.skip(
            reason="skip tests that require the Docker Engine"
        )
        for item in items:
            if hasattr(item, "fixturenames") and "httpd_instance" in item.fixturenames:
                item.add_marker(_skip_docker)


@pytest.fixture(scope="session")
def test_files_dir():
    return dir_.joinpath("data")


@pytest.fixture(scope="session")
def httpd_instance(httpd_version):
    tag = f"httpd_manager-pytest_httpd_1:{httpd_version}"

    docker.from_env().images.build(
        path=str(dir_.joinpath("httpd")),
        dockerfile="Dockerfile",
        tag=tag,
        buildargs={"FROM": f"httpd:{httpd_version}"},
    )

    with docker_helpers.run(tag, ports=["80/tcp"]) as container:
        # wait until we can properly connect to Apache before return the URL
        while True:
            try:
                with httpx.Client(
                    base_url=f"http://localhost:{container.ports['80/tcp']}"
                ) as _client:
                    _client.get("/server-status")
                break
            except httpx.HTTPError:
                # apache is not ready
                time.sleep(0.25)

        yield container


@pytest.fixture(scope="session")
def create_client(httpd_instance) -> Callable:
    # build the url using the information about the docker container

    def handler(base_url=None, **client_kwargs):
        base_url = (
            base_url
            if base_url
            else f"http://localhost:{httpd_instance.ports['80/tcp']}"
        )
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
            await balancer_manager.edit_route(cluster, route, disabled=False)

    return handler
