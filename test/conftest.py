# add the project directory to the pythonpath
import os.path
import sys
from pathlib import Path
dir_ = Path(os.path.dirname(os.path.realpath(__file__)))
sys.path.insert(0, str(dir_.parent))

# enable helpers_namespace before importing pytest
pytest_plugins = ['helpers_namespace']

import asyncio
import json
import logging
import os
import random
import re
from collections import namedtuple
from packaging import version

import docker
import httpx
import pytest
import respx
from packaging import version as version_parser
from py_balancer_manager import BalancerManager, ValidatedBalancerManager

import docker_helpers


logger = logging.getLogger(__name__)


def pytest_addoption(parser):
    parser.addoption('--httpd-version', required=True)


@pytest.fixture(scope='session')
def httpd_version(request):
    v = request.config.getoption('httpd_version')
    return version.parse(v)


@pytest.fixture(scope='session')
def httpd_instance(httpd_version):
    dir_ = os.path.dirname(os.path.abspath(__file__))
    tag = f'py_balancer_manager-pytest_httpd_1:{httpd_version}'

    docker.from_env().images.build(
        path=f'{dir_}/httpd',
        dockerfile='Dockerfile',
        tag=tag,
        buildargs={
            'FROM': f'httpd:{httpd_version}'
        }
    )

    container_info = docker_helpers.run(tag, ports=['80/tcp'])
    yield container_info
    container_info.container.stop()


@pytest.fixture
@pytest.mark.asyncio
async def client_url(httpd_instance):
    # build the url using the information about the docker container
    url = f"http://{httpd_instance.address}:{httpd_instance.ports['80/tcp']}/balancer-manager"
    # wait until we can properly connect to Apache before return the URL
    while True:
        try:
            async with httpx.AsyncClient() as client:
                await client.get(url)
            break
        except httpx.ConnectionClosed:
            logger.warning('apache is not ready')
            await asyncio.sleep(.25)
    return url


@pytest.fixture
@pytest.mark.asyncio
async def balancer_manager(client_url):
    return await BalancerManager(client={
        'url': client_url,
        'username': 'admin',
        'password': 'password',
        'timeout': .25
    }).update()


@pytest.fixture
@pytest.mark.asyncio
async def validated_balancer_manager(client_url):
    with open(f'{dir_}/data/test_validation_profile.json') as fh:
        profile = json.load(fh)
    return await ValidatedBalancerManager(client={
        'url': client_url,
        'username': 'admin',
        'password': 'password',
        'timeout': .25
    }, profile=profile).update()


@pytest.fixture
def mocked_balancer_manager():
    return BalancerManager(client={
        'url': 'http://respx/balancer-manager'
    })


@pytest.helpers.register
async def update_mocked_balancer_manager(balancer_manager, filename):
    with open(f'{dir_}/data/{filename}', 'r') as fh:
        html_payload = fh.read()

    with respx.mock:
        respx.get('http://respx/balancer-manager', content=html_payload)
        await balancer_manager.update()


@pytest.helpers.register
def mocked_balancer_manager_files():
    filenames = list()
    mock_file_pattern = re.compile(r'^balancer-manager-([\d\.]*)\.html$')

    for f in os.listdir(f'{dir_}/data'):
        m = mock_file_pattern.match(f)
        if m:
            version_str = version_parser.parse(m.group(1))
            filenames.append((version_str, f))

    # confirm the list of file is not empty
    assert len(filenames) > 0

    return filenames
