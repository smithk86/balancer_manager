import asyncio
import dataclasses
import pytest
from py_balancer_manager import ValidatedBalancerManager, ValidationClient, ValidatedRoute, ValidatedCluster

from py_balancer_manager.status import Status, ValidatedStatus
from py_balancer_manager.errors import MultipleExceptions


def test_routes(validated_balancer_manager):
    assert type(validated_balancer_manager.clusters) is list
    for cluster in validated_balancer_manager.clusters:
        assert type(cluster.routes) is list
        for route in cluster.routes:
            assert type(route) is ValidatedRoute


@pytest.mark.asyncio
async def test_validate_clusters_and_routes(validated_balancer_manager):
    # run enforce to normalize load-balancer
    await validated_balancer_manager.enforce()
    await asyncio.sleep(1)
    assert validated_balancer_manager.compliance_status is True

    assert validated_balancer_manager.compliance_status is True
    assert type(validated_balancer_manager.profile) is dict
    assert validated_balancer_manager.all_routes_are_profiled is True
    # there should be a entry per cluster
    assert len(validated_balancer_manager.profile) == len(validated_balancer_manager.clusters)

    assert type(validated_balancer_manager) is ValidatedBalancerManager
    assert type(validated_balancer_manager.client) is ValidationClient
    for cluster in validated_balancer_manager.clusters:
        assert type(cluster) == ValidatedCluster
        assert type(cluster.balancer_manager) is ValidatedBalancerManager
        assert type(cluster.profile) is dict
        for route in cluster.routes:
            assert type(route.cluster) == ValidatedCluster
            assert type(route.profile) is list
            assert route.compliance_status is True
            mutable_statuses = route.mutable_statuses()
            for field in dataclasses.fields(route._status):
                status_name = field.name
                if status_name in mutable_statuses:
                    assert type(route.status(status_name)) is ValidatedStatus
                elif route.status(status_name):
                    assert type(route.status(status_name)) is Status


@pytest.mark.asyncio
async def test_all_routes_are_profiled(validated_balancer_manager):
    # manually remove a route from the profile
    validated_balancer_manager.profile['cluster0'].pop('route00')
    # update
    await validated_balancer_manager.update()
    # validate balancer manager
    assert validated_balancer_manager.compliance_status is True
    assert validated_balancer_manager.all_routes_are_profiled is False
    # validate cluster0
    cluster0 = validated_balancer_manager.cluster('cluster0')
    assert cluster0.compliance_status is True
    assert cluster0.all_routes_are_profiled is False
    # validate route
    route00 = cluster0.route('route00')
    assert route00.compliance_status is None
    route01 = cluster0.route('route01')
    assert route01.compliance_status is True


@pytest.mark.asyncio
async def test_compliance_manually(validated_balancer_manager):
    # run enforce to normalize load-balancer
    await validated_balancer_manager.enforce()
    assert validated_balancer_manager.compliance_status is True

    for cluster in validated_balancer_manager.clusters:
        for route in cluster.routes:
            status_disabled = route._status.disabled.value
            assert route._status.disabled.value is status_disabled
            assert route.compliance_status is True
            assert validated_balancer_manager.compliance_status is True
            await route.edit(force=True, disabled=not status_disabled)

            assert route._status.disabled.value is not status_disabled
            assert route.compliance_status is False
            assert validated_balancer_manager.compliance_status is False
            await route.edit(force=True, disabled=status_disabled)

            assert route._status.disabled.value is status_disabled
            assert route.compliance_status is True
            assert validated_balancer_manager.compliance_status is True


@pytest.mark.asyncio
async def test_compliance_with_enforce(httpd_instance, validated_balancer_manager):
    # run enforce to normalize load-balancer
    await validated_balancer_manager.enforce()
    assert validated_balancer_manager.compliance_status is True

    for cluster in validated_balancer_manager.clusters:
        for route in cluster.routes:
            assert route.compliance_status is True
            await route.edit(force=True, disabled=not route._status.disabled.value)
            assert route.compliance_status is False

    assert validated_balancer_manager.compliance_status is False
    await validated_balancer_manager.enforce()
    assert validated_balancer_manager.compliance_status is True

    for cluster in validated_balancer_manager.clusters:
        for route in cluster.routes:
            assert route.compliance_status is True
            await route.edit(force=True, disabled=not route._status.disabled.value)
            assert route.compliance_status is False

    # test an enforce that throws exceptions
    with pytest.raises(MultipleExceptions):
        try:
            httpd_instance.container.pause()
            await validated_balancer_manager.enforce()
        finally:
            httpd_instance.container.unpause()
