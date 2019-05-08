import asyncio
import json
import os
import random
from collections import namedtuple
from packaging import version

import docker
import pytest
from py_balancer_manager import Client, ValidationClient

from helpers import wait_for_port


ContainerInfo = namedtuple('ContainerInfo', ['address', 'port', 'container'])


def pytest_addoption(parser):
    parser.addoption('--httpd-version', default='2.4.39')


@pytest.fixture(scope='session')
def httpd_version(request):
    v = request.config.getoption('httpd_version')
    return version.parse(v)


@pytest.fixture(scope='session')
def httpd_instance(request, httpd_version):
    _dir = os.path.dirname(os.path.abspath(__file__))
    client = docker.from_env()
    tag = f'pytest_httpd:{httpd_version}'

    client.images.build(
        path=f'{_dir}/httpd',
        dockerfile='Dockerfile-2.2' if httpd_version < version.parse('2.4') else 'Dockerfile',
        tag=tag,
        buildargs={
            'FROM': f'httpd:{httpd_version}'
        }
    )
    container = client.containers.run(
        tag,
        detach=True,
        auto_remove=True,
        ports={'80/tcp': ('127.0.0.1', None)}
    )

    def teardown():
        container.stop()
    request.addfinalizer(teardown)

    _ports = client.api.inspect_container(container.id)['NetworkSettings']['Ports']
    ip_address = _ports['80/tcp'][0]['HostIp']
    port = int(_ports['80/tcp'][0]['HostPort'])

    if asyncio.run(wait_for_port(ip_address, port, timeout=5)) is False:
        raise RuntimeException('httpd did not start within 5s')

    return ContainerInfo(
        address=ip_address,
        port=port,
        container=container
    )


@pytest.fixture
@pytest.mark.asyncio
async def client(request, httpd_instance, event_loop):
    client = Client(
        f'http://{httpd_instance.address}:{httpd_instance.port}/balancer-manager',
        username='admin',
        password='password',
        loop=event_loop
    )
    await client.update()

    def teardown():
        async def ateardown():
            await client.close()
        event_loop.run_until_complete(ateardown())
    request.addfinalizer(teardown)

    return client


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
async def validation_client(request, httpd_instance, event_loop):
    _dir = os.path.dirname(os.path.abspath(__file__))
    with open(f'{_dir}/data/test_validation_profile.json') as fh:
        profile = json.load(fh)

    client = ValidationClient(
        f'http://{httpd_instance.address}:{httpd_instance.port}/balancer-manager',
        username='admin',
        password='password',
        profile=profile,
        loop=event_loop
    )
    await client.update()

    def teardown():
        async def ateardown():
            await client.close()
        event_loop.run_until_complete(ateardown())
    request.addfinalizer(teardown)

    return client


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
