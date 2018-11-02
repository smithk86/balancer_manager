import sys
import os.path
import re
import pytest
import random
import logging
import docker
from uuid import UUID
from datetime import datetime
from collections import namedtuple

import requests
import requests_mock
from pytz import utc
from tzlocal import get_localzone

from py_balancer_manager import Client, Cluster, Route, BalancerManagerError, BalancerManagerParseError, NotFound


ContainerInfo = namedtuple('ContainerInfo', ['address', 'port', 'container'])
if sys.version_info < (3, 0):
    str = unicode


def now():
    return utc.localize(datetime.utcnow())


def skip_mock_server(server):
    if server.get('url')[:4] == 'mock':
        pytest.skip('mock adapter')


def httpd_instance(version):
    dir_ = os.path.dirname(os.path.abspath(__file__))
    client = docker.from_env()
    tag = f'pytest_httpd:{version}'

    client.images.build(
        path=f'{dir_}/httpd',
        dockerfile='Dockerfile-2.2' if version.startswith('2.2') else 'Dockerfile',
        tag=tag,
        buildargs={
            'FROM': f'httpd:{version}'
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
    return ContainerInfo(
        address=port['HostIp'],
        port=int(port['HostPort']),
        container=container
    )


@pytest.fixture(
    scope='class',
    params=[
        {
            'url': 'mock://localhost/balancer-manager',
            'version': '2.4',
            'data_file': 'httpd_balancer_manager_2.4.23.html'
        },
        {
            'url': 'mock://localhost/balancer-manager',
            'version': '2.2',
            "data_file": 'httpd_balancer_manager_2.2.31.html'
        },
        {
            'url': '__docker__',
            'version': '2.2.34'
        },
        {
            'url': '__docker__',
            'version': '2.4.29'
        }
    ]
)
def client(request):

    module_directory = os.path.abspath(os.path.dirname(__file__))
    server = request.param

    if server['url'] == '__docker__':
        server['container_info'] = container_info = httpd_instance(server['version'])
        server['url'] = f'http://{container_info.address}:{container_info.port}/balancer-manager'

    client = Client(
        server['url'],
        username='admin',
        password='password'
    )

    if server['url'].startswith('mock'):
        with open('{module_directory}/data/{data_file}'.format(module_directory=module_directory, data_file=server['data_file'])) as fh:
            mock_data = fh.read()

        mock_adapter = requests_mock.Adapter()
        mock_adapter.register_uri('GET', '/balancer-manager', text=mock_data)
        client.session.mount('mock', mock_adapter)

    client.update()

    def teardown():
        client.close()
        if 'container_info' in server:
            container_info.container.stop()
    request.addfinalizer(teardown)

    request.cls.server = server
    request.cls.client = client


@pytest.mark.usefixtures('client')
class TestClient():

    def skip_mock_server(self):

        skip_mock_server(self.server)

    def test_version(self):

        assert self.client.httpd_version_is(self.server['version'])

    def test_routes(self):

        for route in self.client.get_routes():
            assert type(route) is Route

    def test_route_update(self):

        """ insure timestamp is update when refresh is True """

        current_datetime = self.client.updated_datetime
        self.client.get_routes(refresh=True)
        new_datetime = self.client.updated_datetime

        assert current_datetime < new_datetime

    def test_properties(self):

        assert type(self.client.logger) is logging.Logger
        assert type(self.client.url) is str
        assert type(self.client.timeout) is int
        assert type(self.client.updated_datetime) is datetime
        assert type(self.client.insecure) is bool
        assert type(self.client.httpd_version) is str
        assert type(self.client.httpd_compile_datetime) is datetime
        assert type(self.client.openssl_version) is str
        assert self.client.error is None
        assert type(self.client.clusters_ttl) is int
        assert type(self.client.session) is requests.Session
        assert type(self.client.holistic_error_status) is bool

        for cluster in self.client.get_clusters():
            assert type(self.client) is Client
            assert cluster.max_members is None or type(cluster.max_members) == int
            assert cluster.max_members_used is None or type(cluster.max_members_used) == int
            assert type(cluster.sticky_session) is str or cluster.sticky_session is False
            assert cluster.disable_failover is None or type(cluster.disable_failover) == bool
            assert type(cluster.timeout) is int
            assert type(cluster.failover_attempts) == int
            assert type(cluster.method) is str
            assert cluster.path is None or type(cluster.path) == str
            assert cluster.active is None or type(cluster.active) == bool

            for route in cluster.get_routes():
                assert type(route.cluster) is Cluster
                assert type(route.worker) is str
                assert type(route.name) is str
                assert type(route.priority) is int
                assert type(route.route_redir) is str
                assert type(route.factor) is float
                assert type(route.set) is int
                assert type(route.status_ok) is bool
                assert type(route.status_error) is bool
                assert route.status_ignore_errors is None or type(route.status_ignore_errors) is bool
                assert route.status_draining_mode is None or type(route.status_draining_mode) is bool
                assert type(route.status_disabled) is bool
                assert type(route.status_hot_standby)is bool
                assert type(route.elected) is int
                assert route.busy is None or type(route.busy) is int
                assert route.load is None or type(route.load) is int
                assert type(route.traffic_to) is str
                assert type(route.traffic_to_raw) is int
                assert type(route.traffic_from) is str
                assert type(route.traffic_from_raw) is int
                assert type(route.session_nonce_uuid) is UUID

    def test_route_status_changes(self):

        self.skip_mock_server()

        for status in ['status_disabled', 'status_hot_standby', 'status_draining_mode', 'status_ignore_errors']:

            route = self._get_random_route()

            if route is None:
                raise ValueError('no route was returned; please check the server')

            status_value = getattr(route, status)

            # toggle status to the oposite value
            kwargs = {status: not status_value}

            # ensure immutable statuses cannot be modified
            if self.client.httpd_version_is('2.2') and status != 'status_disabled':
                with pytest.raises(BalancerManagerError) as excinfo:
                    route.change_status(**kwargs)
                assert 'is immutable for this version of httpd' in str(excinfo.value)
                continue

            # continue with route testing
            route.change_status(**kwargs)

            # assert new status value
            assert getattr(route, status) is not status_value

            # toggle status back to original value
            route.change_status(**{
                'force': True,
                status: status_value
            })

            # assert original status value
            assert getattr(route, status) is status_value

    def test_route_disable_last(self):

        self.skip_mock_server()

        cluster = self._get_random_cluster()
        try:
            with pytest.raises(BalancerManagerError) as excinfo:
                for route in cluster.get_routes():
                    route.change_status(status_disabled=True)
            assert 'cannot enable the "disabled" status for the last available route' in str(excinfo.value)
        finally:
            for route in cluster.get_routes():
                route.change_status(status_disabled=False)

        try:
            for route in cluster.get_routes():
                route.change_status(force=True, status_disabled=True)
        finally:
            for route in cluster.get_routes():
                route.change_status(status_disabled=False)

    def test_purge_oudated_cluster(self):

        # create new cluster which will not be updated in a refresh
        cluster = self.client.new_cluster()
        cluster.name = '__testing_cluster__'
        cluster.updated_datetime = now()

        # get cluster without refresh
        cluster = self.client.get_cluster(cluster.name, refresh=False)
        assert type(cluster) is Cluster

        # get cluster with refresh
        with pytest.raises(NotFound) as excinfo:
            self.client.get_cluster(cluster.name, refresh=True)
        assert 'could not locate cluster name in list of clusters: __testing_cluster__' in str(excinfo.value)

    def test_purge_oudated_route(self):

        cluster = self._get_random_cluster()

        # create new route which will not be updated in a refresh
        route = cluster.new_route()
        route.name = '__testing_route__'
        route.updated_datetime = now()

        # get route without refresh
        route = self.client.get_cluster(cluster.name, refresh=False).get_route(route.name)
        assert type(route) is Route

        # get route with refresh
        with pytest.raises(NotFound) as excinfo:
            self.client.get_cluster(cluster.name, refresh=True).get_route(route.name)
        assert 'could not locate route name in list of routes: __testing_route__' in str(excinfo.value)

    def _get_random_cluster(self):

        clusters = self.client.get_clusters()
        if len(clusters) > 0:
            random_index = random.randrange(0, len(clusters) - 1) if len(clusters) > 1 else 0
            return clusters[random_index]

        raise ValueError('no clusters were found')

    def _get_random_route(self):

        routes = self.client.get_routes()
        if len(routes) > 0:
            random_index = random.randrange(0, len(routes) - 1) if len(routes) > 1 else 0
            return routes[random_index]

        raise ValueError('no routes were found')


def test_bad_url():

    client = Client(
        'http://tG62vFWzyKNpvmpZA275zZMbQvbtuGJu.com/balancer-manager',
        timeout=5
    )

    with pytest.raises(BalancerManagerError):
        client.update()


def test_bad_balancer_manager():

    client = Client(
        'https://www.google.com',
        timeout=5
    )

    with pytest.raises(BalancerManagerParseError) as excinfo:
        client.update()
    assert 'could not parse text from the first "dt" element' in str(excinfo.value)
