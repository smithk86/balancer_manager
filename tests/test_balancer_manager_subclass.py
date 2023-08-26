import re
from pathlib import Path
from typing import Any

import httpx
import pytest
from pydantic import model_validator
from pytest_httpx import HTTPXMock

from httpd_manager import Cluster, HealthCheck, Route
from httpd_manager.httpx import HttpxBalancerManagerBase

from .test_balancer_manager import validate_properties

dir_ = Path(__file__).parent
pytestmark = pytest.mark.asyncio


class CustomRoute(Route):
    route_is_ok: bool


class CustomCluster(Cluster[CustomRoute]):
    routes_are_ok: bool

    @model_validator(mode="before")
    @classmethod
    def model_validator(cls, values: dict[str, Any]) -> dict[str, Any]:
        values["routes_are_ok"] = True
        for route in values["routes"].values():
            route["route_is_ok"] = route["status"]["ok"]["value"] is True
            if route["route_is_ok"] is False:
                values["routes_are_ok"] = False
        return values


class CustomHttpxBalancerManager(HttpxBalancerManagerBase[CustomCluster]):
    custom_balancer_value: str


def add_mocked_response(httpx_mock: HTTPXMock, file_: str | Path, **kwargs: Any) -> None:
    data_dir = dir_.joinpath("data")
    with data_dir.joinpath(file_).open("r") as fh:
        payload = fh.read()
    httpx_mock.add_response(url="http://testserver.local/balancer-manager", text=payload, **kwargs)


def get_mocked_files() -> dict[str, tuple[str, Path]]:
    files = {}
    mock_stem_pattern = re.compile(r"^balancer-manager-(([\d\.]+).*)")

    for f in dir_.joinpath("data").glob("*.html"):
        m = mock_stem_pattern.match(f.stem)
        if m:
            key = m.group(1)
            version = m.group(2)
            files[key] = (version, f)

    # confirm the list of file is not empty
    assert len(files) > 0

    return files


@pytest.mark.parametrize(
    "version,filename",
    list(get_mocked_files().values()),
    ids=list(get_mocked_files().keys()),
)
async def test_balancer_manager(httpx_mock: HTTPXMock, version: str, filename: Path) -> None:
    add_mocked_response(httpx_mock, filename)

    balancer_manager = await CustomHttpxBalancerManager.async_model_validate_url(
        "http://testserver.local/balancer-manager",
        custom_balancer_value="hello world",
    )
    validate_properties(balancer_manager)

    assert version == balancer_manager.httpd_version

    # cluster3 object should have 10 routes
    assert len(balancer_manager.cluster("cluster3").routes) == 10
    # cluster4 object should exist and not throw an exception
    assert isinstance(balancer_manager.cluster("cluster4"), Cluster)

    assert type(balancer_manager) is CustomHttpxBalancerManager
    for cluster in balancer_manager.clusters.values():
        assert type(cluster) is CustomCluster
        for route in cluster.routes.values():
            assert type(route) is CustomRoute


@pytest.mark.parametrize(
    "status_code,error_message",
    [
        (400, "Client error '400 Bad Request' for url"),
        (401, "Client error '401 Unauthorized' for url"),
        (403, "Client error '403 Forbidden' for"),
        (500, "Server error '500 Internal Server Error' for url"),
    ],
    ids=[400, 401, 403, 500],
)
async def test_status_errors(httpx_mock: HTTPXMock, status_code: int, error_message: str) -> None:
    httpx_mock.add_response(url="http://testserver.local/balancer-manager", status_code=status_code, text="")
    with pytest.raises(httpx.HTTPStatusError, match=f".*{error_message}.*"):
        await CustomHttpxBalancerManager.async_model_validate_url("http://testserver.local/balancer-manager")


async def test_with_route_gc(httpx_mock: HTTPXMock) -> None:
    # create BalancerManager with mock-1
    add_mocked_response(httpx_mock, "balancer-manager-mock-1.html")
    balancer_manager = await CustomHttpxBalancerManager.async_model_validate_url(
        "http://testserver.local/balancer-manager",
        custom_balancer_value="hello world",
    )

    # cluster3 object should have 10 routes
    assert len(balancer_manager.cluster("cluster3").routes) == 10
    # cluster4 object should exist
    assert "cluster4" in balancer_manager.clusters

    # update BalancerManager with mock-2
    add_mocked_response(httpx_mock, "balancer-manager-mock-2.html")
    await balancer_manager.update()

    # cluster object should now be gone
    with pytest.raises(KeyError):
        balancer_manager.cluster("cluster4")

    # routes route35, route37, and route39 should be removed
    # confirm the number of routes
    assert len(balancer_manager.cluster("cluster3").routes) == 7


async def test_bad_payload(httpx_mock: HTTPXMock, test_files_dir: Path) -> None:
    with test_files_dir.joinpath("server-status-mock-1.html").open("r") as fh:
        httpx_mock.add_response(url="http://testserver.local/balancer-manager", text=fh.read())

    with pytest.raises(
        ValueError,
        match=r"initial html validation failed; is this really an Httpd Balancer Manager page?",
    ):
        await CustomHttpxBalancerManager.async_model_validate_url("http://testserver.local/balancer-manager")


async def test_hcheck(httpx_mock: HTTPXMock, test_files_dir: Path) -> None:
    with test_files_dir.joinpath("balancer-manager-2.4.56-hcheck.html").open("r") as fh:
        httpx_mock.add_response(url="http://testserver.local/balancer-manager", text=fh.read())

        balancer_manager = await CustomHttpxBalancerManager.async_model_validate_url(
            "http://testserver.local/balancer-manager",
            custom_balancer_value="hello world",
        )

        for route in balancer_manager.cluster("cluster4").routes.values():
            assert route.hcheck is None

        for route in balancer_manager.cluster("cluster5").routes.values():
            assert type(route.hcheck) is HealthCheck

        route51 = balancer_manager.cluster("cluster5").route("route51")
        assert route51.status.hcheck_failure and route51.status.hcheck_failure.value is False

        route52 = balancer_manager.cluster("cluster5").route("route52")
        assert route52.status.hcheck_failure and route52.status.hcheck_failure.value is True
