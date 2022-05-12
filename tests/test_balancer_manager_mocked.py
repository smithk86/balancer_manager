import re
from pathlib import Path

import httpx
import pytest

from httpd_manager import Cluster

from .test_balancer_manager import validate_properties


dir_ = Path(__file__).parent


@pytest.fixture
def mocked_client(create_client):
    return create_client("https://pytest-httpx")


def add_mocked_response(httpx_mock, file_, **kwargs):
    if isinstance(file_, str):
        file_ = dir_.joinpath("data").joinpath(file_)

    with open(file_, "r") as fh:
        payload = fh.read()
    httpx_mock.add_response(
        url="https://pytest-httpx/balancer-manager", text=payload, **kwargs
    )


def get_mocked_files():
    files = list()
    mock_stem_pattern = re.compile(r"^balancer-manager-([\d\.]*)$")

    for f in dir_.joinpath("data").glob("*.html"):
        m = mock_stem_pattern.match(f.stem)
        if m:
            version = m.group(1)
            files.append((version, f))

    # confirm the list of file is not empty
    assert len(files) > 0

    return files


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "version,filename", get_mocked_files(), ids=[x for x, _ in get_mocked_files()]
)
async def test_balancer_manager(mocked_client, httpx_mock, version, filename):
    add_mocked_response(httpx_mock, filename)

    balancer_manager = await mocked_client.balancer_manager()
    validate_properties(balancer_manager)

    assert version == balancer_manager.httpd_version

    # cluster3 object should have 10 routes
    assert len(balancer_manager.cluster("cluster3").routes) == 10
    # cluster4 object should exist and not throw an exception
    assert isinstance(balancer_manager.cluster("cluster4"), Cluster)


@pytest.mark.asyncio
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
async def test_status_errors(mocked_client, httpx_mock, status_code, error_message):
    httpx_mock.add_response(
        url="https://pytest-httpx/balancer-manager", status_code=status_code, text=""
    )
    with pytest.raises(httpx.HTTPStatusError, match=f".*{error_message}.*"):
        await mocked_client.balancer_manager()


@pytest.mark.asyncio
async def test_with_route_gc(mocked_client, httpx_mock):
    # create BalancerManager with mock-1
    add_mocked_response(httpx_mock, "balancer-manager-mock-1.html")
    balancer_manager = await mocked_client.balancer_manager()

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
