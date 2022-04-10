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
    # there should be no active httpx client
    assert py_httpd_client.http_client is None
    # open a client
    await py_httpd_client.__aenter__()
    http_client1 = py_httpd_client.http_client
    assert isinstance(http_client1, httpx.AsyncClient)
    # open the same Client again
    await py_httpd_client.__aenter__()
    http_client2 = py_httpd_client.http_client
    assert isinstance(http_client2, httpx.AsyncClient)
    # these should be the same object
    assert http_client1 is http_client2
    # close
    await py_httpd_client.__aexit__()
    assert py_httpd_client.http_client is None

    # these should be completely different httpx.AsyncClient instances
    async with Client("http://localhost") as client1:
        assert isinstance(client1.http_client, httpx.AsyncClient)
        async with Client("http://localhost") as client2:
            assert isinstance(client2.http_client, httpx.AsyncClient)
            assert client1.http_client is not client2.http_client

    # both should now be closed and nulled
    assert client1.http_client is None
    assert client2.http_client is None


@pytest.mark.asyncio
async def test_unclosed_client():
    """
    Open a context-based http client without closing.
    This should throw a warning during clean up.
    """
    _client = Client("https://www.google.com", timeout=1)
    await _client.__aenter__()
    await _client._request("get", "/")
    assert _client.http_client._state is ClientState.OPENED
    with pytest.warns(
        UserWarning,
        match=(
            "py_httpd_manager.Client for "
            "https://www.google.com was not properly closed"
        ),
    ):
        del _client

    """
    do a non-context-based request which creates an ad-hoc http client
    this client will close on its own and should not throw any
    warnings about not being properly cleaned up
    """
    _client = Client("https://www.google.com", timeout=1)
    await _client._request("get", "/")
    assert _client.http_client is None
    with pytest.warns(None) as record:
        del _client
    assert len(record) == 0
