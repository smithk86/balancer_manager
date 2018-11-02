import os.path

import json
import pytest
import random

from test_client import httpd_instance
from py_balancer_manager import ValidationClient, ValidatedRoute, ValidatedCluster
import requests_mock


@pytest.fixture(
    scope='class',
    params=[
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
def validation_client(request):

    module_directory = os.path.abspath(os.path.dirname(__file__))
    server = request.param

    with open(f'{module_directory}/data/test_validation_profile.json') as fh:
        profile = json.load(fh)

    if server['url'] == '__docker__':
        server['container_info'] = container_info = httpd_instance(server['version'])
        server['url'] = f'http://{container_info.address}:{container_info.port}/balancer-manager'

    client = ValidationClient(
        server['url'],
        username='admin',
        password='password',
        profile=profile
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


@pytest.mark.usefixtures('validation_client')
class TestValidationClient():

    def test_routes(self):

        assert type(self.client.get_routes()) is list
        for route in self.client.get_routes():
            assert type(route) is ValidatedRoute

    def test_validate_clusters_and_routes(self):

        assert self.client.holistic_compliance_status is True
        assert type(self.client.profile) is dict
        assert self.client.all_routes_are_profiled is True
        # there should be a entry per cluster
        assert len(self.client.profile) == len(self.client.get_clusters())

        for cluster in self.client.get_clusters():
            assert type(self.client) is ValidationClient

            for route in cluster.get_routes():
                assert type(route.cluster) == ValidatedCluster
                assert route.compliance_status is True
                assert type(route.status_validation) is dict

    def test_compliance_manually(self):

        for route in self._get_random_routes():

            status_disabled = route.status_disabled

            assert route.status_disabled is status_disabled
            assert route.compliance_status is True
            assert self.client.holistic_compliance_status is True

            route.change_status(force=True, status_disabled=not status_disabled)

            assert route.status_disabled is not status_disabled
            assert route.compliance_status is False
            assert self.client.holistic_compliance_status is False

            route.change_status(force=True, status_disabled=status_disabled)

            assert route.status_disabled is status_disabled
            assert route.compliance_status is True
            assert self.client.holistic_compliance_status is True

    def test_compliance_with_enforce(self):

        assert self.client.holistic_compliance_status is True

        for route in self._get_random_routes():
            assert route.compliance_status is True
            route.change_status(force=True, status_disabled=not route.status_disabled)
            assert route.compliance_status is False

        assert self.client.holistic_compliance_status is False

        self.client.enforce()

        assert self.client.holistic_compliance_status is True

    def _get_random_routes(self):

        random_routes = list()
        for cluster in self.client.get_clusters():
            routes = cluster.get_routes()
            if len(routes) > 1:
                random_index = random.randrange(0, len(routes) - 1) if len(routes) > 1 else 0
                random_routes.append(routes[random_index])

        if len(random_routes) == 0:
            raise ValueError('no routes were found')

        return random_routes
