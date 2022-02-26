from uuid import uuid4

import pytest
import httpx
from httpx._client import ClientState

from httpd_manager import *
from httpd_manager.balancer_manager.parse import parse


@pytest.mark.asyncio
async def test_bad_url():
    async with Client(f"http://{uuid4()}.com", timeout=1) as client:
        with pytest.raises(httpx.ConnectError) as excinfo:
            await client.get("/balancer-manager")


@pytest.mark.asyncio
async def test_bad_payload():
    async with Client("https://www.google.com", timeout=1) as client:
        # server status
        balancer_manager = ServerStatus(client)
        request = await client.get("/")
        with pytest.raises(HttpdManagerError) as excinfo:
            parse(request)
        assert "payload validation failed" in str(excinfo.value)

        # balancer manager
        balancer_manager = BalancerManager(client)
        request = await client.get("/")
        with pytest.raises(HttpdManagerError) as excinfo:
            parse(request)
        assert "payload validation failed" in str(excinfo.value)


@pytest.mark.asyncio
async def test_multiple_client_sessions(py_httpd_client):
    py_httpd_client._http_client._state is ClientState.CLOSED
    await py_httpd_client.__aenter__()
    py_httpd_client._http_client._state is ClientState.OPENED
    await py_httpd_client.__aenter__()
    py_httpd_client._http_client._state is ClientState.OPENED
    await py_httpd_client.__aexit__()
    py_httpd_client._http_client._state is ClientState.CLOSED
    await py_httpd_client.__aexit__()
    py_httpd_client._http_client._state is ClientState.CLOSED


@pytest.mark.asyncio
async def test_unclosed_client():
    _client = Client(f"https://www.google.com", timeout=1)
    await _client.__aenter__()
    assert _client._http_client._state is ClientState.OPENED
    with pytest.warns(
        UserWarning,
        match=(
            "py_httpd_manager.Client for "
            "https://www.google.com was not properly closed"
        ),
    ):
        del _client
