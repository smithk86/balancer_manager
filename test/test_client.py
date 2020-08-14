from uuid import uuid4

import pytest
import httpx

from py_balancer_manager import Client, BalancerManager, BalancerManagerError
from py_balancer_manager._parse import parse


@pytest.mark.asyncio
async def test_bad_url():
    async with Client(f'http://{uuid4()}.com/balancer-manager', insecure=False, username=None, password=None, timeout=1) as client:
        with pytest.raises(BalancerManagerError) as excinfo:
            await client.get()
        assert 'http call to apache failed' in str(excinfo.value)


@pytest.mark.asyncio
async def test_bad_balancer_manager():
    balancer_manager = BalancerManager(client={
        'url': 'https://www.google.com',
        'timeout': 1
    })
    async with balancer_manager.client:
        with pytest.raises(BalancerManagerError) as excinfo:
            payload = await balancer_manager.client.get()
            await parse(payload, balancer_manager)
    assert 'could not parse text from the first "dt" element' in str(excinfo.value)
