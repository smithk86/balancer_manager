import asyncio
import json
import os
import random
from collections import namedtuple
from packaging import version

import docker
import pytest
from py_balancer_manager import Client, ValidationClient

import docker_helpers


_dir = os.path.dirname(os.path.abspath(__file__))


def pytest_addoption(parser):
    parser.addoption('--httpd-version', default='2.4.39')


@pytest.fixture(scope='session')
def httpd_version(request):
    v = request.config.getoption('httpd_version')
    return version.parse(v)


@pytest.fixture(scope='session')
def httpd_instance(httpd_version):
    _dir = os.path.dirname(os.path.abspath(__file__))
    tag = f'pytest_httpd:{httpd_version}'

    docker.from_env().images.build(
        path=f'{_dir}/httpd',
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
def client_url(httpd_instance):
    return f"http://{httpd_instance.address}:{httpd_instance.ports['80/tcp']}/balancer-manager"


@pytest.fixture
def client(client_url):
    return Client(
        client_url,
        username='admin',
        password='password',
        timeout=.25
    )


@pytest.fixture
@pytest.mark.asyncio
async def balancer_manager(client):
    return await client.balancer_manager()


@pytest.fixture
def random_cluster(balancer_manager):
    clusters = balancer_manager.clusters
    if len(clusters) > 0:
        random_index = random.randrange(0, len(clusters) - 1) if len(clusters) > 1 else 0
        return clusters[random_index]
    raise ValueError('no clusters were found')


@pytest.fixture
def random_route(random_cluster):
    routes = random_cluster.routes
    if len(routes) > 0:
        random_index = random.randrange(0, len(routes) - 1) if len(routes) > 1 else 0
        return routes[random_index]
    raise ValueError('no routes were found')


@pytest.fixture
def validation_client(client_url):
    return ValidationClient(
        client_url,
        username='admin',
        password='password',
        timeout=.25
    )


@pytest.fixture
@pytest.mark.asyncio
async def validated_balancer_manager(validation_client):
    with open(f'{_dir}/data/test_validation_profile.json') as fh:
        profile = json.load(fh)
    return await validation_client.balancer_manager(profile=profile)
