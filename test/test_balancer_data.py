from uuid import UUID
from datetime import datetime

import pytest
from packaging import version

from py_balancer_manager import BalancerData, BalancerManagerError, Client, Cluster, Route
from py_balancer_manager.status import Statuses, Status


def test_properties(balancer_data):
    assert type(balancer_data.client) is Client
    assert type(balancer_data.updated_datetime) is datetime
    assert type(balancer_data.httpd_version) is version.Version
    assert type(balancer_data.httpd_compile_datetime) is datetime
    assert type(balancer_data.openssl_version) is version.Version
    assert type(balancer_data.holistic_error_status) is bool

    for cluster in balancer_data.clusters:
        assert type(cluster.balancer_data) is BalancerData
        assert cluster.max_members is None or type(cluster.max_members) == int
        assert cluster.max_members_used is None or type(cluster.max_members_used) == int
        assert type(cluster.sticky_session) is str or cluster.sticky_session is False
        assert cluster.disable_failover is None or type(cluster.disable_failover) == bool
        assert type(cluster.timeout) is int
        assert type(cluster.failover_attempts) == int
        assert type(cluster.method) is str
        assert cluster.path is None or type(cluster.path) == str
        assert cluster.active is None or type(cluster.active) == bool

        for route in cluster.routes:
            assert type(route) is Route
            assert type(route.cluster) is Cluster
            assert type(route.worker) is str
            assert type(route.name) is str
            assert type(route.priority) is int
            assert type(route.route_redir) is str
            assert type(route.factor) is float
            assert type(route.lbset) is int
            assert type(route.elected) is int
            assert route.busy is None or type(route.busy) is int
            assert route.load is None or type(route.load) is int
            assert type(route.traffic_to) is str
            assert type(route.traffic_to_raw) is int
            assert type(route.traffic_from) is str
            assert type(route.traffic_from_raw) is int
            assert type(route.session_nonce_uuid) is UUID
            assert type(route._status) is Statuses
            assert type(route._status.ok) is Status
            assert type(route._status.error) is Status
            for status_name in route.mutable_statuses():
                assert type(route.status(status_name)) is Status


@pytest.mark.asyncio
async def test_updated_datetime(balancer_data):
    """ confirm the updated_datetime attribute is updated """
    first_datetime = balancer_data.updated_datetime
    await balancer_data.update()
    last_datetime = balancer_data.updated_datetime
    assert first_datetime < last_datetime


@pytest.mark.asyncio
async def test_cluster_does_not_exist(balancer_data):
    with pytest.raises(BalancerManagerError) as excinfo:
        balancer_data.cluster('does_not_exist')
    assert 'could not locate cluster name in list of clusters: does_not_exist' in str(excinfo.value)


@pytest.mark.asyncio
async def test_route_status_changes(random_route):
    for status_name in random_route.mutable_statuses():
        status_value = random_route.status(status_name).value

        # toggle status to the oposite value
        kwargs = {status_name: not status_value}

        # continue with route testing
        await random_route.edit(**kwargs)

        # assert new status value
        assert random_route.status(status_name).value is not status_value

        # toggle status back to original value
        await random_route.edit(**{
            'force': True,
            status_name: status_value
        })

        # assert original status value
        assert random_route.status(status_name).value is status_value


@pytest.mark.asyncio
async def test_taking_traffic(balancer_data):
    cluster = balancer_data.cluster('cluster2')

    cluster.route('route20').taking_traffic is True
    cluster.route('route21').taking_traffic is True
    cluster.route('route22').taking_traffic is False
    cluster.route('route23').taking_traffic is False

    await cluster.route('route20').edit(disabled=True, hot_standby=True)

    cluster.route('route20').taking_traffic is False
    cluster.route('route21').taking_traffic is True
    cluster.route('route22').taking_traffic is False
    cluster.route('route23').taking_traffic is False


@pytest.mark.asyncio
async def test_route_disable_last(balancer_data):
    cluster = balancer_data.cluster('cluster3')

    try:
        with pytest.raises(BalancerManagerError) as excinfo:
            for route in cluster.routes:
                await route.edit(disabled=True)
        assert 'cannot enable the "disabled" status for the last available route' in str(excinfo.value)
    finally:
        for route in cluster.routes:
            await route.edit(disabled=False)

    try:
        for route in cluster.routes:
            await route.edit(force=True, disabled=True)
    finally:
        for route in cluster.routes:
            await route.edit(disabled=False)


@pytest.mark.asyncio
async def test_standby_activated(balancer_data):
    cluster = balancer_data.cluster('cluster2')

    for route in cluster.routes:
        await route.edit(disabled=False)

    #assert cluster.standby_activated is False
    await cluster.route('route20').edit(disabled=True)
    await cluster.route('route21').edit(disabled=True)
    #assert cluster.standby_activated is True
