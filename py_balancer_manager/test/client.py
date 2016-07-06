import re
import pytest
import random

from get_vars import get_var
from py_balancer_manager import Client


@pytest.fixture(
    scope='class',
    params=get_var('servers')
)
def fixture_client(request):

    server = request.param

    client = Client(
        server['url'],
        insecure=server.get('insecure', False),
        username=server.get('username', None),
        password=server.get('password', None)
    )

    def fin():
        client.close()

    request.cls.server = server
    request.cls.client = client


@pytest.mark.usefixtures("fixture_client")
class TestClient():

    def test_version(self):

        assert self.client.apache_version_is(self.server['version'])

    def test_routes(self):

        assert type(self.client.get_routes()) is list

    def test_route_update(self):
        """ insure timestamp is update when use_cache is False """

        old_time = self.client.cache_routes_time
        self.client.get_routes(use_cache=False)
        new_time = self.client.cache_routes_time

        assert old_time < new_time

    def test_validate_routes(self):

        uuid_pattern = re.compile(r'[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}')

        for route in self.client.get_routes():

            assert type(route['worker']) == str
            assert type(route['route']) == str
            assert type(route['priority']) == int
            assert type(route['route_redir']) == str
            assert type(route['factor']) == int
            assert type(route['set']) == int
            assert type(route['status_ok']) == bool
            assert type(route['status_error']) == bool
            assert route['status_ignore_errors'] is None or type(route['status_ignore_errors']) == bool
            assert route['status_draining_mode'] is None or type(route['status_draining_mode']) == bool
            assert type(route['status_disabled']) == bool
            assert type(route['status_hot_standby']) == bool
            assert type(route['elected']) == int
            assert route['busy'] is None or type(route['busy']) == int
            assert route['load'] is None or type(route['load']) == int
            assert type(route['to']) == str
            assert type(route['to_raw']) == int
            assert type(route['from']) == str
            assert type(route['from_raw']) == int
            assert uuid_pattern.match(route['session_nonce_uuid'])
            assert type(route['cluster']) == str

    def test_route_status_changes(self):

        for status in ['status_disabled', 'status_hot_standby', 'status_draining_mode', 'status_ignore_errors']:

            route = self._get_random_route()

            # only test status_disabled with apache 2.2
            if self.client.apache_version_is('2.2') and status != 'status_disabled':
                continue

            status_value = route[status]

            # toggle status to the oposite value
            kwargs = {status: not status_value}
            self.client.change_route_status(route, **kwargs)
            updated_route = self.client.get_route(route['cluster'], route['route'])
            assert updated_route[status] is not status_value

            # toggle status back to original value
            kwargs = {status: status_value}
            self.client.change_route_status(route, **kwargs)
            updated_route = self.client.get_route(route['cluster'], route['route'])
            assert updated_route[status] is status_value

    def _get_random_route(self):

        routes = self.client.get_routes()
        if len(routes) > 0:
            random_index = random.randrange(0, len(routes) - 1) if len(routes) > 1 else 0
            return routes[random_index]
        else:
            return None
