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
        dockerfile='Dockerfile-2.2' if httpd_version < version.parse('2.4') else 'Dockerfile',
        tag=tag,
        buildargs={
            'FROM': f'httpd:{httpd_version}'
        }
    )

    container_info = docker_helpers.run(tag, port=80)
    yield container_info
    container_info.container.stop()


@pytest.fixture
@pytest.mark.asyncio
async def client(httpd_instance, event_loop):
    client = Client(
        f'http://{httpd_instance.address}:{httpd_instance.port}/balancer-manager',
        username='admin',
        password='password',
        timeout=2,
        loop=event_loop
    )
    await client.update()
    yield client
    await client.close()


@pytest.fixture
@pytest.mark.asyncio
async def random_cluster(client):
    clusters = await client.get_clusters()
    if len(clusters) > 0:
        random_index = random.randrange(0, len(clusters) - 1) if len(clusters) > 1 else 0
        return clusters[random_index]
    raise ValueError('no clusters were found')


@pytest.fixture
@pytest.mark.asyncio
async def random_route(client):
    routes = await client.get_routes()
    if len(routes) > 0:
        random_index = random.randrange(0, len(routes) - 1) if len(routes) > 1 else 0
        return routes[random_index]
    raise ValueError('no routes were found')


@pytest.fixture
@pytest.mark.asyncio
async def validation_client(httpd_instance, event_loop):
    _dir = os.path.dirname(os.path.abspath(__file__))
    with open(f'{_dir}/data/test_validation_profile.json') as fh:
        profile = json.load(fh)

    client = ValidationClient(
        f'http://{httpd_instance.address}:{httpd_instance.port}/balancer-manager',
        username='admin',
        password='password',
        timeout=2,
        profile=profile,
        loop=event_loop
    )
    await client.update()
    yield client
    await client.close()


@pytest.fixture
@pytest.mark.asyncio
async def random_validated_routes(validation_client):
    random_routes = list()
    for cluster in await validation_client.get_clusters():
        routes = cluster.get_routes()
        if len(routes) > 1:
            random_index = random.randrange(0, len(routes) - 1) if len(routes) > 1 else 0
            random_routes.append(routes[random_index])
    if len(random_routes) == 0:
        raise ValueError('no routes were found')
    return random_routes
