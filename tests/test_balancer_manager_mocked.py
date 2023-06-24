import re
from pathlib import Path

import httpx
import pytest
from pytest_httpx import HTTPXMock

from httpd_manager import Cluster, HealthCheck
from .test_balancer_manager import HttpxBalancerManager, validate_properties


dir_ = Path(__file__).parent
pytestmark = pytest.mark.asyncio


def add_mocked_response(httpx_mock: HTTPXMock, file_: str | Path, **kwargs):
    data_dir = dir_.joinpath("data")
    with open(data_dir / file_, "r") as fh:
        payload = fh.read()
    httpx_mock.add_response(
        url="http://testserver.local/balancer-manager", text=payload, **kwargs
    )


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
async def test_balancer_manager(httpx_mock: HTTPXMock, version: str, filename: Path):
    add_mocked_response(httpx_mock, filename)

    balancer_manager = await HttpxBalancerManager.parse_from_url(
        "http://testserver.local/balancer-manager"
    )
    validate_properties(balancer_manager)

    assert version == balancer_manager.httpd_version

    # cluster3 object should have 10 routes
    assert len(balancer_manager.cluster("cluster3").routes) == 10
    # cluster4 object should exist and not throw an exception
    assert isinstance(balancer_manager.cluster("cluster4"), Cluster)


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
async def test_status_errors(
    httpx_mock: HTTPXMock, status_code: int, error_message: str
):
    httpx_mock.add_response(
        url="http://testserver.local/balancer-manager", status_code=status_code, text=""
    )
    with pytest.raises(httpx.HTTPStatusError, match=f".*{error_message}.*"):
        await HttpxBalancerManager.parse_from_url(
            "http://testserver.local/balancer-manager"
        )


async def test_with_route_gc(httpx_mock: HTTPXMock):
    # create BalancerManager with mock-1
    add_mocked_response(httpx_mock, "balancer-manager-mock-1.html")
    balancer_manager = await HttpxBalancerManager.parse_from_url(
        "http://testserver.local/balancer-manager"
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


async def test_bad_payload(httpx_mock: HTTPXMock, test_files_dir: Path):
    with test_files_dir.joinpath("server-status-mock-1.html").open("r") as fh:
        httpx_mock.add_response(
            url="http://testserver.local/balancer-manager", text=fh.read()
        )

    with pytest.raises(
        ValueError,
        match=r"initial html validation failed; is this really an Httpd Balancer Manager page?",
    ):
        await HttpxBalancerManager.parse_from_url(
            "http://testserver.local/balancer-manager"
        )


async def test_hcheck(httpx_mock: HTTPXMock, test_files_dir: Path):
    with test_files_dir.joinpath("balancer-manager-2.4.56-hcheck.html").open("r") as fh:
        httpx_mock.add_response(
            url="http://testserver.local/balancer-manager", text=fh.read()
        )

        balancer_manager = await HttpxBalancerManager.parse_from_url(
            "http://testserver.local/balancer-manager"
        )

        for route in balancer_manager.cluster("cluster4").routes.values():
            assert route.hcheck is None

        for route in balancer_manager.cluster("cluster5").routes.values():
            assert type(route.hcheck) is HealthCheck

        route51 = balancer_manager.cluster("cluster5").route("route51")
        assert route51.status.hcheck_failure.value is False

        route52 = balancer_manager.cluster("cluster5").route("route52")
        assert route52.status.hcheck_failure.value is True
