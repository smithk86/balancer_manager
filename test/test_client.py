from uuid import uuid4

import pytest
import httpx

from py_balancer_manager import Client, BalancerManagerError


def test_version(balancer_manager, httpd_version):
    assert balancer_manager.httpd_version == httpd_version


@pytest.mark.asyncio
async def test_bad_url():
    client = Client(f'http://{uuid4()}.com/balancer-manager', timeout=1)
    with pytest.raises(httpx.exceptions.NetworkError) as excinfo:
        await client.balancer_manager()
    assert 'Name or service not known' in str(excinfo.value)


@pytest.mark.asyncio
async def test_bad_balancer_manager():
    client = Client('https://www.google.com', timeout=1)
    with pytest.raises(BalancerManagerError) as excinfo:
        await client.balancer_manager()
    assert 'could not parse text from the first "dt" element' in str(excinfo.value)
