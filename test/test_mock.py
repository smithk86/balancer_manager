import os
import re
from pathlib import Path

import httpx
import pytest
import respx
from packaging import version as version_parser

from httpd_manager import Cluster, HttpdManagerError


dir_ = Path(os.path.dirname(os.path.realpath(__file__)))


async def update_mocked_client(manager, filename):
    with open(f"{dir_}/data/{filename}", "r") as fh:
        html_payload = fh.read()

    with respx.mock as respx_mock:
        respx_mock.get("http://respx").mock(
            return_value=httpx.Response(status_code=200, text=html_payload)
        )
        async with manager:
            return await manager.update()


def balancer_manager_files():
    filenames = list()
    mock_file_pattern = re.compile(r"^balancer-manager-([\d\.]*)\.html$")

    for f in os.listdir(f"{dir_}/data"):
        m = mock_file_pattern.match(f)
        if m:
            version_str = version_parser.parse(m.group(1))
            filenames.append((version_str, f))

    # confirm the list of file is not empty
    assert len(filenames) > 0

    return filenames


@pytest.mark.asyncio
@pytest.mark.parametrize("version,filename", balancer_manager_files())
async def test_balancer_manager(mocked_balancer_manager, version, filename):
    await update_mocked_client(mocked_balancer_manager, filename)

    assert version == mocked_balancer_manager.httpd_version

    # cluster3 object should have 10 routes
    assert len(mocked_balancer_manager["cluster3"]) == 10
    # cluster4 object should exist and not throw an exception
    assert type(mocked_balancer_manager["cluster3"]) is Cluster


@pytest.mark.asyncio
@pytest.mark.parametrize("status_code", [400, 401, 403, 500])
async def test_status_errors(mocked_balancer_manager, status_code):
    with respx.mock as respx_mock:
        respx_mock.get("http://respx").mock(
            return_value=httpx.Response(status_code=status_code, text="")
        )
        async with mocked_balancer_manager:
            with pytest.raises(HttpdManagerError) as excinfo:
                await mocked_balancer_manager.update()
            assert str(status_code) in str(excinfo.value)


@pytest.mark.asyncio
async def test_with_route_gc(mocked_balancer_manager):
    # update balancer-manager with mock-1
    await update_mocked_client(mocked_balancer_manager, "balancer-manager-mock-1.html")

    # cluster3 object should have 10 routes
    assert len(mocked_balancer_manager["cluster3"]) == 10
    # cluster4 object should exist
    assert "cluster4" in mocked_balancer_manager

    # update balancer-manager with mock-2
    await update_mocked_client(mocked_balancer_manager, "balancer-manager-mock-2.html")

    # cluster object should now be gone
    with pytest.raises(HttpdManagerError) as excinfo:
        mocked_balancer_manager["cluster4"]
    assert "cluster does not exist" in str(excinfo.value)
    assert "cluster: cluster4" in str(excinfo.value)

    # routes route35, route37, and route39 should be removed
    # confirm the number of routes
    assert len(mocked_balancer_manager["cluster3"]) == 7
