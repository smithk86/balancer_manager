import re
import pytest
import random
from datetime import datetime
from uuid import UUID

from get_vars import get_var
from py_balancer_manager import Client, Cluster, Route, BalancerManagerError, BalancerManagerParseError, NotFound


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

    client.refresh()

    def fin():
        client.close()

    request.cls.server = server
    request.cls.client = client


@pytest.mark.usefixtures("fixture_client")
class TestClient():

    def test_version(self):

        assert self.client.apache_version_is(self.server['version'])

    def test_routes(self):

        for route in self.client.get_routes():
            assert type(route) is Route

    def test_route_update(self):

        """ insure timestamp is update when refresh is True """

        current_datetime = self.client.updated_datetime
        self.client.get_routes(refresh=True)
        new_datetime = self.client.updated_datetime

        assert current_datetime < new_datetime

    def test_validate_clusters_and_routes(self):

        uuid_pattern = re.compile(r'[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}')

        for cluster in self.client.get_clusters():
            assert type(self.client) is Client
            assert cluster.max_members is None or type(cluster.max_members) == int
            assert cluster.max_members_used is None or type(cluster.max_members_used) == int
            assert type(cluster.sticky_session) == str
            assert cluster.disable_failover is None or type(cluster.disable_failover) == bool
            assert type(cluster.timeout) == int
            assert type(cluster.failover_attempts) == int
            assert type(cluster.method) == str
            assert cluster.path is None or type(cluster.path) == str
            assert cluster.active is None or type(cluster.active) == bool

            for route in cluster.get_routes():
                assert type(route.cluster) == Cluster
                assert type(route.worker) == str
                assert type(route.name) == str
                assert type(route.priority) == int
                assert type(route.route_redir) == str
                assert type(route.factor) == int
                assert type(route.set) == int
                assert type(route.status_ok) == bool
                assert type(route.status_error) == bool
                assert route.status_ignore_errors is None or type(route.status_ignore_errors) == bool
                assert route.status_draining_mode is None or type(route.status_draining_mode) == bool
                assert type(route.status_disabled) == bool
                assert type(route.status_hot_standby) == bool
                assert type(route.elected) == int
                assert route.busy is None or type(route.busy) == int
                assert route.load is None or type(route.load) == int
                assert type(route.traffic_to) == str
                assert type(route.traffic_to_raw) == int
                assert type(route.traffic_from) == str
                assert type(route.traffic_from_raw) == int
                assert type(route.session_nonce_uuid) is UUID

    def test_route_status_changes(self):

        for status in ['status_disabled', 'status_hot_standby', 'status_draining_mode', 'status_ignore_errors']:

            route = self._get_random_route()

            if route is None:
                raise ValueError('no route was returned; please check the server')

            status_value = getattr(route, status)

            # toggle status to the oposite value
            kwargs = {status: not status_value}

            # ensure immutable statuses cannot be modified
            if self.client.apache_version_is('2.2') and status != 'status_disabled':
                with pytest.raises(BalancerManagerError) as excinfo:
                    route.change_status(**kwargs)
                assert 'is immutable for this version of apache' in str(excinfo.value)
                continue

            # continue with route testing
            route.change_status(**kwargs)

            # assert new status value
            assert getattr(route, status) is not status_value

            # toggle status back to original value
            route.change_status(**{
                status: status_value
            })

            # assert original status value
            assert getattr(route, status) is status_value

    def test_purge_oudated_cluster(self):

        # create new cluster which will not be updated in a refresh
        cluster = self.client.new_cluster()
        cluster.name = '__testing_cluster__'
        cluster.updated_datetime = datetime.now()

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
        route.updated_datetime = datetime.now()

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
        get_var('url_with_bad_hostname'),
        timeout=5
    )

    with pytest.raises(BalancerManagerError):
        client.refresh()


def test_bad_balancer_manager():

    client = Client(
        get_var('url_for_non-balancer-manager'),
        timeout=5
    )

    with pytest.raises(BalancerManagerParseError) as excinfo:
        client.refresh()
    assert 'could not parse text from the first "dt" element' in str(excinfo.value)


def test_bad_auth():

    for server_url in [s.get('url') for s in get_var('servers')]:
        with pytest.raises(BalancerManagerError) as excinfo:
            Client(server_url).refresh()
        assert '401 Client Error' in str(excinfo.value)
