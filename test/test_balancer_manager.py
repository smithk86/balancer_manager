from uuid import UUID
from datetime import datetime

import pytest
from packaging import version

from httpd_manager import Bytes, Client, HttpdManagerError, MultipleExceptions
from httpd_manager.balancer_manager import *


def test_properties(balancer_manager):
    assert type(balancer_manager.client) is Client
    assert type(balancer_manager.date) is datetime
    assert isinstance(balancer_manager.httpd_version, version.Version)
    assert type(balancer_manager.httpd_built_date) is datetime
    assert isinstance(balancer_manager.openssl_version, version._BaseVersion)
    assert type(balancer_manager.health) is bool

    for cluster in balancer_manager.values():
        assert type(cluster.balancer_manager) is BalancerManager
        assert type(cluster.max_members) is int
        assert type(cluster.max_members_used) is int
        assert cluster.sticky_session is None or type(cluster.sticky_session) is str
        assert (
            cluster.disable_failover is None or type(cluster.disable_failover) is bool
        )
        assert type(cluster.timeout) is int
        assert type(cluster.failover_attempts) == int
        assert type(cluster.method) is str
        assert type(cluster.path) == str
        assert type(cluster.active) == bool
        assert type(cluster.health) is bool

        for route in cluster.values():
            assert type(route) is Route
            assert type(route.cluster) is Cluster
            assert type(route.worker) is str
            assert type(route.name) is str
            assert type(route.priority) is int
            assert type(route.route_redir) is str
            assert type(route.factor) is float
            assert type(route.lbset) is int
            assert type(route.elected) is int
            assert type(route.busy) is int
            assert type(route.load) is int
            assert type(route._to) is Bytes
            assert type(route.to) is int
            assert type(route._from_) is Bytes
            assert type(route.from_) is int
            assert type(route.session_nonce_uuid) is UUID
            assert type(route.health) is bool
            assert type(route.status) is dict
            assert len(route) >= 7
            assert type(route["ok"]) is ImmutableStatus
            assert type(route["error"]) is ImmutableStatus
            assert type(route["ignore_errors"]) is Status
            assert type(route["draining_mode"]) is Status
            assert type(route["disabled"]) is Status
            assert type(route["hot_standby"]) is Status
            assert type(route["hot_spare"]) is Status
            assert type(route["stopped"]) is Status
            assert type(route.health) is bool


@pytest.mark.asyncio
async def test_properties_without_lxml(balancer_manager):
    _original_disable_lxml = balancer_manager.client.disable_lxml
    try:
        balancer_manager.client.disable_lxml = True
        assert balancer_manager.client.use_lxml is False
        async with balancer_manager:
            await balancer_manager.update()
            test_properties(balancer_manager)
    finally:
        balancer_manager.client.disable_lxml = _original_disable_lxml


def test_version(balancer_manager, httpd_version):
    assert balancer_manager.httpd_version == httpd_version


@pytest.mark.asyncio
async def test_date(balancer_manager):
    """confirm the date attribute is updated"""
    first_datetime = balancer_manager.date
    async with balancer_manager.client:
        await balancer_manager.update()
    last_datetime = balancer_manager.date
    assert first_datetime < last_datetime


@pytest.mark.asyncio
async def test_cluster_does_not_exist(balancer_manager):
    with pytest.raises(HttpdManagerError) as excinfo:
        balancer_manager["does_not_exist"]
    assert "cluster does not exist" in str(excinfo.value)
    assert "cluster: does_not_exist" in str(excinfo.value)


@pytest.mark.asyncio
async def test_route_status_changes(balancer_manager):
    async with balancer_manager.client:
        route = balancer_manager["cluster0"]["route00"]
        for status_name in route.mutable_keys():
            status_value = route[status_name].value

            # toggle status to the oposite value
            kwargs = {status_name: not status_value}

            # continue with route testing
            await route.edit(**kwargs)

            # assert new status value
            assert route[status_name].value is not status_value

            # toggle status back to original value
            await route.edit(**{"force": True, status_name: status_value})

            # assert original status value
            assert route[status_name].value is status_value


@pytest.mark.asyncio
async def test_cluster_lbsets(httpd_instance, balancer_manager):
    async with balancer_manager.client:
        cluster = balancer_manager["cluster4"]
        lbsets = cluster.lbsets
        assert len(lbsets) == 2
        assert len(lbsets[0]) == 5
        assert len(lbsets[1]) == 5

        assert cluster.active_lbset == 0

        # test bad lbset number
        with pytest.raises(HttpdManagerError) as excinfo:
            cluster.lbset(99)
        assert "lbset does not exist" in str(excinfo.value)
        assert "lbset number: 99" in str(excinfo.value)

        # verify before change
        for route in cluster.values():
            assert route["disabled"].value is False

        # do change
        await cluster.edit_lbset(1, disabled=True)
        # verify after change
        for route in cluster.lbset(1):
            assert route["disabled"].value is True
        # verify active lbset
        assert cluster.active_lbset == 0

        # do change
        await cluster.edit_lbset(1, disabled=False)
        # verify after change
        for route in cluster.lbset(1):
            assert route["disabled"].value is False
        # verify active lbset
        assert cluster.active_lbset == 0

        # do change
        await cluster.edit_lbset(0, disabled=True)
        # verify after change
        for route in cluster.lbset(0):
            assert route["disabled"].value is True
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
async def test_accepting_requests(balancer_manager):
    cluster = balancer_manager["cluster2"]

    assert cluster["route20"].accepting_requests is True
    assert cluster["route21"].accepting_requests is True
    assert cluster["route22"].accepting_requests is False
    assert cluster["route23"].accepting_requests is False

    async with balancer_manager.client:
        await cluster["route20"].edit(disabled=True, hot_standby=True)

    assert cluster["route20"].accepting_requests is False
    assert cluster["route21"].accepting_requests is True
    assert cluster["route22"].accepting_requests is False
    assert cluster["route23"].accepting_requests is False


@pytest.mark.asyncio
async def test_route_disable_last(balancer_manager):
    async with balancer_manager.client:
        cluster = balancer_manager["cluster3"]
        try:
            with pytest.raises(HttpdManagerError) as excinfo:
                for route in cluster.values():
                    await route.edit(disabled=True)
            assert "cannot disable final active route" in str(excinfo.value)
            assert "cluster: cluster3" in str(excinfo.value)
            assert "route: route31" in str(excinfo.value)
        finally:
            for route in cluster.values():
                await route.edit(disabled=False)

        try:
            for route in cluster.values():
                await route.edit(force=True, disabled=True)
        finally:
            for route in cluster.values():
                await route.edit(disabled=False)


@pytest.mark.asyncio
async def test_standby(balancer_manager):
    async with balancer_manager.client:
        cluster = balancer_manager["cluster2"]

        for route in cluster.values():
            await route.edit(disabled=False)

        assert cluster.standby is False
        await cluster["route20"].edit(disabled=True)
        await cluster["route21"].edit(disabled=True)
        assert cluster.standby is True
