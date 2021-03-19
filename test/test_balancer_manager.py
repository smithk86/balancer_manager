from uuid import UUID
from datetime import datetime

import pytest
from packaging import version

from py_balancer_manager import BalancerManager, BalancerManagerError, Client, Cluster, MultipleExceptions, Route
from py_balancer_manager.helpers import TrafficData
from py_balancer_manager.status import Statuses, Status


def test_properties(balancer_manager):
    assert type(balancer_manager.client) is Client
    assert type(balancer_manager.date) is datetime
    assert isinstance(balancer_manager.httpd_version, version._BaseVersion)
    assert type(balancer_manager.httpd_compile_date) is datetime
    assert isinstance(balancer_manager.openssl_version, version._BaseVersion)
    assert type(balancer_manager.holistic_error_status) is bool

    for cluster in balancer_manager.clusters:
        assert type(cluster.balancer_manager) is BalancerManager
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
            assert type(route.traffic_to) is TrafficData
            assert type(route.traffic_from) is TrafficData
            assert type(route.session_nonce_uuid) is UUID
            assert type(route._status) is Statuses
            assert type(route._status.ok) is Status
            assert type(route._status.error) is Status
            for status_name in route.mutable_statuses():
                assert type(route.status(status_name)) is Status


def test_version(balancer_manager, httpd_version):
    assert balancer_manager.httpd_version == httpd_version


@pytest.mark.asyncio
async def test_date(balancer_manager):
    """ confirm the date attribute is updated """
    first_datetime = balancer_manager.date
    await balancer_manager.update()
    last_datetime = balancer_manager.date
    assert first_datetime < last_datetime


@pytest.mark.asyncio
async def test_cluster_does_not_exist(balancer_manager):
    with pytest.raises(BalancerManagerError) as excinfo:
        balancer_manager.cluster('does_not_exist')
    assert 'could not locate cluster name in list of clusters: does_not_exist' in str(excinfo.value)


@pytest.mark.asyncio
async def test_route_status_changes(balancer_manager):
    route = balancer_manager.cluster('cluster0').route('route00')
    for status_name in route.mutable_statuses():
        status_value = route.status(status_name).value

        # toggle status to the oposite value
        kwargs = {status_name: not status_value}

        # continue with route testing
        await route.edit(**kwargs)

        # assert new status value
        assert route.status(status_name).value is not status_value

        # toggle status back to original value
        await route.edit(**{
            'force': True,
            status_name: status_value
        })

        # assert original status value
        assert route.status(status_name).value is status_value


@pytest.mark.asyncio
async def test_cluster_lbsets(httpd_instance, balancer_manager):
    cluster = balancer_manager.cluster('cluster4')
    lbsets = cluster.lbsets()
    assert len(lbsets) == 2
    assert len(lbsets[0]) == 5
    assert len(lbsets[1]) == 5

    assert cluster.active_lbset == 0

    # test bad lbset number
    with pytest.raises(BalancerManagerError) as excinfo:
        cluster.lbset(99)
    assert 'lbset does not exist: 99' in str(excinfo.value)

    # verify before change
    for route in cluster.lbset(1):
        assert route.status('disabled').value is False

    # do change
    await cluster.edit_lbset(1, disabled=True)
    # verify after change
    for route in cluster.lbset(1):
        assert route.status('disabled').value is True
    # verify active lbset
    assert cluster.active_lbset == 0

    # do change
    await cluster.edit_lbset(1, disabled=False)
    # verify after change
    for route in cluster.lbset(1):
        assert route.status('disabled').value is False
    # verify active lbset
    assert cluster.active_lbset == 0

    # do change
    await cluster.edit_lbset(0, disabled=True)
    # verify after change
    for route in cluster.lbset(0):
        assert route.status('disabled').value is True
    # verify active lbset
    assert cluster.active_lbset == 1

    # test an enforce that throws exceptions
    with pytest.raises(MultipleExceptions):
        try:
            httpd_instance.container.pause()
            await cluster.edit_lbset(1, disabled=True)
        finally:
            httpd_instance.container.unpause()


@pytest.mark.asyncio
async def test_taking_traffic(balancer_manager):
    cluster = balancer_manager.cluster('cluster2')

    assert cluster.route('route20').taking_traffic is True
    assert cluster.route('route21').taking_traffic is True
    assert cluster.route('route22').taking_traffic is False
    assert cluster.route('route23').taking_traffic is False

    await cluster.route('route20').edit(disabled=True, hot_standby=True)

    assert cluster.route('route20').taking_traffic is False
    assert cluster.route('route21').taking_traffic is True
    assert cluster.route('route22').taking_traffic is False
    assert cluster.route('route23').taking_traffic is False


@pytest.mark.asyncio
async def test_route_disable_last(balancer_manager):
    cluster = balancer_manager.cluster('cluster3')

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
async def test_standby_activated(balancer_manager):
    cluster = balancer_manager.cluster('cluster2')

    for route in cluster.routes:
        await route.edit(disabled=False)

    #assert cluster.standby_activated is False
    await cluster.route('route20').edit(disabled=True)
    await cluster.route('route21').edit(disabled=True)
    #assert cluster.standby_activated is True
