import json
import os
import random
from collections import namedtuple
from packaging import version

import docker
import pytest
from py_balancer_manager import Client


ContainerInfo = namedtuple('ContainerInfo', ['address', 'port', 'container'])


def pytest_addoption(parser):
    parser.addoption('--httpd-version', default='2.4.37')


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
    ports = client.api.inspect_container(container.id)['NetworkSettings']['Ports']
    port = ports['80/tcp'][0]

    def teardown():
        container.stop()
    request.addfinalizer(teardown)

    return ContainerInfo(
        address=port['HostIp'],
        port=int(port['HostPort']),
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

# @pytest.fixture(
#     params=[
#         {
#             'url': '__docker__',
#             'version': '2.2.34'
#         },
#         {
#             'url': '__docker__',
#             'version': '2.4.29'
#         }
#     ]
# )
# def validation_client(request):

#     module_directory = os.path.abspath(os.path.dirname(__file__))
#     server = request.param

#     with open(f'{module_directory}/data/test_validation_profile.json') as fh:
#         profile = json.load(fh)

#     if server['url'] == '__docker__':
#         server['container_info'] = container_info = httpd_instance(server['version'])
#         server['url'] = f'http://{container_info.address}:{container_info.port}/balancer-manager'

#     client = ValidationClient(
#         server['url'],
#         username='admin',
#         password='password',
#         profile=profile
#     )

#     if server['url'].startswith('mock'):
#         with open('{module_directory}/data/{data_file}'.format(module_directory=module_directory, data_file=server['data_file'])) as fh:
#             mock_data = fh.read()

#         mock_adapter = requests_mock.Adapter()
#         mock_adapter.register_uri('GET', '/balancer-manager', text=mock_data)
#         client.session.mount('mock', mock_adapter)

#     client.update()

#     def teardown():
#         client.close()
#         if 'container_info' in server:
#             container_info.container.stop()
#     request.addfinalizer(teardown)

#     request.cls.server = server
#     request.cls.client = client


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
