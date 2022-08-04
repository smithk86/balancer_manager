from concurrent.futures import ProcessPoolExecutor
from datetime import datetime
from uuid import UUID

import httpx
import pytest
from pytest_docker.plugin import DockerComposeExecutor

from httpd_manager.balancer_manager import *


pytestmark = pytest.mark.anyio


def validate_properties(balancer_manager):
    assert isinstance(balancer_manager.date, datetime)
    assert isinstance(balancer_manager.httpd_version, str)
    assert isinstance(balancer_manager.httpd_built_date, datetime)
    assert isinstance(balancer_manager.openssl_version, str)

    for cluster in balancer_manager.clusters.values():
        assert isinstance(cluster.max_members, int)
        assert isinstance(cluster.max_members_used, int)
        assert (
            cluster.sticky_session is None or isinstance(cluster.sticky_session) is str
        )
        assert cluster.disable_failover is None or isinstance(
            cluster.disable_failover, bool
        )
        assert isinstance(cluster.timeout, int)
        assert isinstance(cluster.failover_attempts, int)
        assert isinstance(cluster.method, str)
        assert isinstance(cluster.path, str)
        assert isinstance(cluster.active, bool)

        for route in cluster.routes.values():
            assert isinstance(route, Route)
            assert isinstance(route.cluster, str)
            assert isinstance(route._cluster, Cluster)
            assert isinstance(route.worker, str)
            assert isinstance(route.name, str)
            assert isinstance(route.priority, int)
            assert isinstance(route.route_redir, str)
            assert isinstance(route.factor, float)
            assert isinstance(route.lbset, int)
            assert isinstance(route.elected, int)
            assert isinstance(route.busy, int)
            assert isinstance(route.load, int)
            assert isinstance(route.to_, int)
            assert isinstance(route.from_, int)
            assert isinstance(route.session_nonce_uuid, UUID)
            assert isinstance(route.status, RouteStatus)
            assert isinstance(route.status.ok, ImmutableStatus)
            assert isinstance(route.status.error, ImmutableStatus)
            assert isinstance(route.status.ignore_errors, Status)
            assert isinstance(route.status.draining_mode, Status)
            assert isinstance(route.status.disabled, Status)
            assert isinstance(route.status.hot_standby, Status)
            assert isinstance(route.status.hot_spare, Status)
            assert isinstance(route.status.stopped, Status)


async def test_properties(client):
    balancer_manager = await client.balancer_manager()
    validate_properties(balancer_manager)

    # test update
    _original_date = balancer_manager.date
    await balancer_manager.update()
    assert _original_date < balancer_manager.date


async def test_with_process_pool(client):
    with ProcessPoolExecutor(max_workers=10) as ppexec:
        _token = executor.set(ppexec)

        balancer_manager = await client.balancer_manager()
        validate_properties(balancer_manager)

        # test update
        _original_date = balancer_manager.date
        await balancer_manager.update()
        assert _original_date < balancer_manager.date

        executor.reset(_token)


async def test_httpd_version(client, httpd_version):
    balancer_manager = await client.balancer_manager()
    assert balancer_manager.httpd_version == httpd_version


async def test_cluster_does_not_exist(client):
    balancer_manager = await client.balancer_manager()
    with pytest.raises(KeyError, match=r"\'does_not_exist\'"):
        balancer_manager.cluster("does_not_exist")


async def test_route_status_changes(client):
    balancer_manager = await client.balancer_manager()

    # get route and do status update
    route_1 = balancer_manager.cluster("cluster0").route("route00")
    route_status_1 = route_1.status.copy(deep=True).mutable()

    # do the initial changes
    assert len(route_status_1) > 0
    for name, status in route_status_1.items():
        if type(status) == ImmutableStatus:
            continue

        # toggle status to the oposite value
        kwargs = {name: not status.value}
        # continue with route testing
        await balancer_manager.edit_route("cluster0", "route00", **kwargs)

    # verify change
    route_2 = balancer_manager.cluster("cluster0").route("route00")
    route_status_2 = route_2.status.mutable()
    assert len(route_status_2) > 0
    for name, status in route_status_2.items():
        # assert new status value
        assert route_status_1[name].value is not status.value
        # toggle status back to original value
        await balancer_manager.edit_route(
            "cluster0", "route00", **{"force": True, name: not status.value}
        )

    # verify original value again
    route_3 = balancer_manager.cluster("cluster0").route("route00")
    route_status_3 = route_3.status.mutable()
    for name, status in route_status_3.items():
        # assert originally value
        assert route_status_1[name].value is status.value


async def test_cluster_lbsets(client, docker_compose_file, docker_compose_project_name):
    docker_compose = DockerComposeExecutor(
        "docker-compose", docker_compose_file, docker_compose_project_name
    )

    balancer_manager = await client.balancer_manager()
    cluster = balancer_manager.cluster("cluster4")
    lbsets = cluster.lbsets
    assert len(lbsets) == 2
    assert len(lbsets[0]) == 5
    assert len(lbsets[1]) == 5

    assert cluster.active_lbset == 0

    # test bad lbset number
    with pytest.raises(AssertionError, match=r"lbset 99 does not exist"):
        cluster.lbset(99)

    # verify before change
    for route in cluster.routes.values():
        assert route.status.disabled.value is False

    # do change
    await balancer_manager.edit_lbset(cluster, 1, disabled=True)
    # verify after change
    cluster = balancer_manager.cluster("cluster4")
    for route in cluster.lbset(1):
        assert route.status.disabled.value is True
    # verify active lbset
    assert cluster.active_lbset == 0

    # do change
    await balancer_manager.edit_lbset(cluster, 1, disabled=False)
    # verify after change
    cluster = balancer_manager.cluster("cluster4")
    for route in cluster.lbset(1):
        assert route.status.disabled.value is False
    # verify active lbset
    assert cluster.active_lbset == 0

    # do change
    await balancer_manager.edit_lbset(cluster, 0, disabled=True)
    # verify after change
    cluster = balancer_manager.cluster("cluster4")
    for route in cluster.lbset(0):
        assert route.status.disabled.value is True
    # verify active lbset
    assert cluster.active_lbset == 1

    # test an enforce that throws exceptions
    edit_lbset_exceptions = list()

    def _exception_handler(e: Exception):
        edit_lbset_exceptions.append(e)

    try:
        docker_compose.execute("pause httpd")
        await balancer_manager.edit_lbset(
            cluster, 1, disabled=True, exception_handler=_exception_handler
        )
    finally:
        docker_compose.execute("unpause httpd")

    assert len(edit_lbset_exceptions) == 5
    for e in edit_lbset_exceptions:
        assert isinstance(e, httpx.ReadTimeout)


async def test_accepting_requests(client):
    balancer_manager = await client.balancer_manager()
    cluster = balancer_manager.cluster("cluster2")

    assert cluster.route("route20").accepting_requests is True
    assert cluster.route("route21").accepting_requests is True
    assert cluster.route("route22").accepting_requests is False
    assert cluster.route("route23").accepting_requests is False

    await balancer_manager.edit_route(
        "cluster2", "route20", disabled=True, hot_standby=True
    )
    cluster = balancer_manager.cluster("cluster2")

    assert cluster.route("route20").accepting_requests is False
    assert cluster.route("route21").accepting_requests is True
    assert cluster.route("route22").accepting_requests is False
    assert cluster.route("route23").accepting_requests is False


async def test_route_disable_last(client, enable_all_routes):
    balancer_manager = await client.balancer_manager()
    cluster = balancer_manager.cluster("cluster3")

    await enable_all_routes(balancer_manager, cluster)

    try:
        with pytest.raises(ValueError, match=r".*cannot disable final active route.*"):
            for route in cluster.routes.values():
                await balancer_manager.edit_route(cluster, route, disabled=True)
    finally:
        await enable_all_routes(balancer_manager, cluster)

    try:
        for route in cluster.routes.values():
            await balancer_manager.edit_route(cluster, route, force=True, disabled=True)
    finally:
        await enable_all_routes(balancer_manager, cluster)


async def test_standby(client, enable_all_routes):
    balancer_manager = await client.balancer_manager()

    await enable_all_routes(balancer_manager, balancer_manager.cluster("cluster2"))

    assert balancer_manager.cluster("cluster2").standby is False
    await balancer_manager.edit_route("cluster2", "route20", disabled=True)
    await balancer_manager.edit_route("cluster2", "route21", disabled=True)
    assert balancer_manager.cluster("cluster2").standby is True
