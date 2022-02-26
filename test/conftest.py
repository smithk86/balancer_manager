# add the project directory to the pythonpath
import os.path
import sys
from pathlib import Path

dir_ = Path(os.path.dirname(os.path.realpath(__file__)))
sys.path.insert(0, str(dir_.parent))


import asyncio
import json
import logging
import os
import random
from collections import namedtuple
from concurrent.futures import ProcessPoolExecutor

import docker  # type: ignore
import httpx
import pytest
from packaging import version
from httpd_manager import BalancerManager, HttpdManagerError, Client

import docker_helpers


logger = logging.getLogger(__name__)
# logging.basicConfig(level=logging.DEBUG)


def pytest_addoption(parser):
    parser.addoption("--httpd-version", default="2.4.48")
    parser.addoption("--disable-docker", action="store_true", default=False)


@pytest.fixture(scope="session")
def httpd_version(request):
    v = request.config.getoption("httpd_version")
    return version.parse(v)


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
    return f"{dir_}/data"


@pytest.fixture(scope="session")
def httpd_instance(httpd_version):
    dir_ = os.path.dirname(os.path.abspath(__file__))
    tag = f"httpd_manager-pytest_httpd_1:{httpd_version}"

    docker.from_env().images.build(
        path=f"{dir_}/httpd",
        dockerfile="Dockerfile",
        tag=tag,
        buildargs={"FROM": f"httpd:{httpd_version}"},
    )

    with docker_helpers.run(tag, ports=["80/tcp"]) as container:
        yield container


@pytest.fixture
@pytest.mark.asyncio
async def py_httpd_client(httpd_instance):
    # build the url using the information about the docker container
    client = Client(
        f"http://localhost:{httpd_instance.ports['80/tcp']}",
        auth=("admin", "password"),
        executor=ProcessPoolExecutor(),
        timeout=0.25,
    )

    # wait until we can properly connect to Apache before return the URL
    while True:
        try:
            async with client:
                await client.get("/server-status")
            break
        except httpx.HTTPError:
            # apache is not ready
            await asyncio.sleep(0.25)

    return client


@pytest.fixture
@pytest.mark.asyncio
async def balancer_manager(py_httpd_client):
    async with py_httpd_client:
        return await py_httpd_client.balancer_manager()


@pytest.fixture
def mocked_client():
    return Client("http://respx")


@pytest.fixture
def mocked_balancer_manager(mocked_client):
    return BalancerManager(mocked_client)
