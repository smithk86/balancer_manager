import pytest

import httpx

from py_balancer_manager import Client, BalancerManagerError


def test_version(balancer_manager, httpd_version):
    assert balancer_manager.httpd_version == httpd_version


def test_asdict(client, client_url):
    client_dict = client.asdict()
    assert client_dict['url'] == client_url
    assert client_dict['insecure'] is False


@pytest.mark.asyncio
async def test_bad_url():
    client = Client('http://tG62vFWzyKNpvmpZA275zZMbQvbtuGJu.com/balancer-manager', timeout=5)
    with pytest.raises(httpx.exceptions.NetworkError) as excinfo:
        await client.balancer_manager()
    assert 'Name or service not known' in str(excinfo.value)


@pytest.mark.asyncio
async def test_bad_balancer_manager():
    client = Client('https://www.google.com', timeout=5)
    with pytest.raises(BalancerManagerError) as excinfo:
        await client.balancer_manager()
    assert 'could not parse text from the first "dt" element' in str(excinfo.value)
