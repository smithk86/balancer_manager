import re
import pytest
import logging
from uuid import UUID
from datetime import datetime

import aiohttp
from packaging import version
from pytz import utc
from tzlocal import get_localzone

from py_balancer_manager import Client, Cluster, Route, BalancerManagerError
from py_balancer_manager.status import Statuses, Status


def now():
    return utc.localize(datetime.utcnow())


def test_version(client, httpd_version):
    assert client.httpd_version == httpd_version


@pytest.mark.asyncio
async def test_routes(client):
    for r in await client.get_routes():
        assert type(r) is Route


@pytest.mark.asyncio
async def test_route_update(client):
    """ insure timestamp is update when refresh is True """
    current_datetime = client.updated_datetime
    await client.get_routes(refresh=True)
    new_datetime = client.updated_datetime
    assert current_datetime < new_datetime


@pytest.mark.asyncio
async def test_properties(client):
    assert type(client.logger) is logging.Logger
    assert type(client.url) is str
    assert type(client.timeout) is int
    assert type(client.updated_datetime) is datetime
    assert type(client.insecure) is bool
    assert type(client.httpd_version) is version.Version
    assert type(client.httpd_compile_datetime) is datetime
    assert type(client.openssl_version) is version.LegacyVersion
    assert client.error is None
    assert type(client.clusters_ttl) is int
    assert type(client.session) is aiohttp.ClientSession
    assert type(client.holistic_error_status) is bool

    for cluster in await client.get_clusters():
        assert type(client) is Client
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
async def test_route_status_changes(client, random_route):
    for status_name in random_route.mutable_statuses():
        status_value = random_route.status(status_name).value

        # toggle status to the oposite value
        kwargs = {status_name: not status_value}

        # continue with route testing
        await random_route.change_status(**kwargs)

        # assert new status value
        assert random_route.status(status_name).value is not status_value

        # toggle status back to original value
        await random_route.change_status(**{
            'force': True,
            status_name: status_value
        })

        # assert original status value
        assert random_route.status(status_name).value is status_value


@pytest.mark.asyncio
async def test_route_disable_last(random_cluster):
    try:
        with pytest.raises(BalancerManagerError) as excinfo:
            for route in random_cluster.get_routes():
                await route.change_status(disabled=True)
        assert 'cannot enable the "disabled" status for the last available route' in str(excinfo.value)
    finally:
        for route in random_cluster.get_routes():
            await route.change_status(disabled=False)

    try:
        for route in random_cluster.get_routes():
            await route.change_status(force=True, disabled=True)
    finally:
        for route in random_cluster.get_routes():
            await route.change_status(disabled=False)


@pytest.mark.asyncio
async def test_purge_outdated_cluster(client):
    # create new cluster which will not be updated in a refresh
    cluster = client.new_cluster()
    cluster.name = '__testing_cluster__'
    cluster.updated_datetime = now()

    # get cluster without refresh
    cluster = await client.get_cluster(cluster.name, refresh=False)
    assert type(cluster) is Cluster

    # get cluster with refresh
    with pytest.raises(BalancerManagerError) as excinfo:
        await client.get_cluster(cluster.name, refresh=True)
    assert 'could not locate cluster name in list of clusters: __testing_cluster__' in str(excinfo.value)


@pytest.mark.asyncio
async def test_purge_outdated_route(client, random_cluster):
    # create new route which will not be updated in a refresh
    route = random_cluster.new_route()
    route.name = '__testing_route__'
    route.updated_datetime = now()
    route._status = Statuses(
        ok=Status(value=None, immutable=True, http_form_code=None),
        error=Status(value=None, immutable=True, http_form_code=None),
        ignore_errors=Status(value=None, immutable=True, http_form_code=None),
        draining_mode=Status(value=None, immutable=True, http_form_code=None),
        disabled=Status(value=None, immutable=True, http_form_code=None),
        hot_standby=Status(value=None, immutable=True, http_form_code=None),
        hot_spare=None,
        stopped=None
    )

    # get route without refresh
    route = (await client.get_cluster(random_cluster.name, refresh=False)).get_route(route.name)
    assert type(route) is Route

    # get route with refresh
    with pytest.raises(BalancerManagerError) as excinfo:
        (await client.get_cluster(random_cluster.name, refresh=True)).get_route(route.name)
    assert 'could not locate route name in list of routes: __testing_route__' in str(excinfo.value)


@pytest.mark.asyncio
async def test_standby_activated(client):
    cluster = await client.get_cluster('cluster3')

    for route in cluster.get_routes():
        await route.change_status(disabled=False)

    assert cluster.standby_activated is False
    await cluster.get_route('route30').change_status(disabled=True)
    await cluster.get_route('route31').change_status(disabled=True)
    assert cluster.standby_activated is True


@pytest.mark.asyncio
async def test_taking_traffic(client):
    cluster = await client.get_cluster('cluster2')
    assert cluster.get_route('route20').taking_traffic is True
    assert cluster.get_route('route21').taking_traffic is True
    assert cluster.get_route('route22').taking_traffic is False
    assert cluster.get_route('route23').taking_traffic is False
    await cluster.get_route('route20').change_status(disabled=True)
    await cluster.get_route('route20').change_status(hot_standby=True)
    assert cluster.get_route('route20').taking_traffic is False
    assert cluster.get_route('route21').taking_traffic is True
    assert cluster.get_route('route22').taking_traffic is False
    assert cluster.get_route('route23').taking_traffic is False


@pytest.mark.asyncio
async def test_bad_url():
    async with Client('http://tG62vFWzyKNpvmpZA275zZMbQvbtuGJu.com/balancer-manager', timeout=5) as client:
        with pytest.raises(aiohttp.ClientConnectorError):
            await client.update()


@pytest.mark.asyncio
async def test_bad_balancer_manager():
    async with Client('https://www.google.com', timeout=5) as client:
        with pytest.raises(BalancerManagerError) as excinfo:
            await client.update()
        assert 'could not parse text from the first "dt" element' in str(excinfo.value)
