from uuid import uuid4

import pytest
import httpx

from py_balancer_manager import Client, BalancerManager, BalancerManagerError


@pytest.mark.asyncio
async def test_bad_url():
    client = Client(f'http://{uuid4()}.com/balancer-manager', insecure=False, username=None, password=None, timeout=1)
    with pytest.raises(httpx.NetworkError) as excinfo:
        await client._http_get_payload()
    assert 'Name or service not known' in str(excinfo.value)


@pytest.mark.asyncio
async def test_bad_balancer_manager():
    balancer_manager = BalancerManager(client={
        'url': 'https://www.google.com',
        'timeout': 1
    })
    client = balancer_manager.client
    with pytest.raises(BalancerManagerError) as excinfo:
        payload = await client._http_get_payload()
        await client._parse(payload, balancer_manager)
    assert 'could not parse text from the first "dt" element' in str(excinfo.value)
