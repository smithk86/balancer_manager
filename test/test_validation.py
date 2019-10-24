import asyncio
import dataclasses
import pytest
from py_balancer_manager import ValidationClient, ValidatedRoute, ValidatedCluster

from py_balancer_manager.status import Status, ValidatedStatus
from py_balancer_manager.errors import MultipleExceptions


@pytest.mark.asyncio
async def test_routes(validation_client):
    assert type(await validation_client.get_routes()) is list
    for route in await validation_client.get_routes():
        assert type(route) is ValidatedRoute


@pytest.mark.asyncio
async def test_validate_clusters_and_routes(validation_client):
    # run enforce to normalize load-balancer
    await validation_client.enforce()
    await asyncio.sleep(1)
    assert validation_client.compliance_status is True

    assert validation_client.compliance_status is True
    assert type(validation_client.profile) is dict
    assert validation_client.all_routes_are_profiled is True
    # there should be a entry per cluster
    assert len(validation_client.profile) == len(await validation_client.get_clusters())

    assert type(validation_client) is ValidationClient
    for cluster in await validation_client.get_clusters():
        assert type(cluster) == ValidatedCluster
        assert type(cluster.client) is ValidationClient
        assert type(cluster.profile) is dict
        for route in cluster.get_routes():
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
async def test_all_routes_are_profiled(validation_client):
    # manually remove a route from the profile
    validation_client.profile['cluster0'].pop('route00')
    # update
    await validation_client.update()
    # validate client
    assert validation_client.compliance_status is True
    assert validation_client.all_routes_are_profiled is False
    # validate cluster0
    cluster0 = await validation_client.get_cluster('cluster0')
    assert cluster0.compliance_status is True
    assert cluster0.all_routes_are_profiled is False
    # validate route
    route00 = cluster0.get_route('route00')
    assert route00.compliance_status is None
    route01 = cluster0.get_route('route01')
    assert route01.compliance_status is True


@pytest.mark.asyncio
async def test_compliance_manually(validation_client, random_validated_routes):
    # run enforce to normalize load-balancer
    await validation_client.enforce()
    assert validation_client.compliance_status is True

    for route in random_validated_routes:
        status_disabled = route._status.disabled.value
        assert route._status.disabled.value is status_disabled
        assert route.compliance_status is True
        assert validation_client.compliance_status is True
        await route.edit(force=True, disabled=not status_disabled)

        assert route._status.disabled.value is not status_disabled
        assert route.compliance_status is False
        assert validation_client.compliance_status is False
        await route.edit(force=True, disabled=status_disabled)

        assert route._status.disabled.value is status_disabled
        assert route.compliance_status is True
        assert validation_client.compliance_status is True


@pytest.mark.asyncio
async def test_compliance_with_enforce(httpd_instance, validation_client, random_validated_routes):
    # run enforce to normalize load-balancer
    await validation_client.enforce()
    assert validation_client.compliance_status is True

    for route in random_validated_routes:
        assert route.compliance_status is True
        await route.edit(force=True, disabled=not route._status.disabled.value)
        assert route.compliance_status is False

    assert validation_client.compliance_status is False
    await validation_client.enforce()
    assert validation_client.compliance_status is True

    for route in random_validated_routes:
        assert route.compliance_status is True
        await route.edit(force=True, disabled=not route._status.disabled.value)
        assert route.compliance_status is False

    # test an enforce that throws exceptions
    with pytest.raises(MultipleExceptions):
        try:
            httpd_instance.container.pause()
            await validation_client.enforce()
        finally:
            httpd_instance.container.unpause()
