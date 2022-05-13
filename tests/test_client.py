import warnings
from typing import Callable
from uuid import uuid4

import pytest
import httpx
from httpx._client import ClientState

from httpd_manager import Client
from httpd_manager.immutable import ImmutableBalancerManager, ImmutableServerStatus


pytestmark = pytest.mark.anyio


async def test_bad_url(create_client):
    client = create_client(f"http://{uuid4()}.com")
    with pytest.raises(httpx.ConnectError) as excinfo:
        await client.server_status()


async def test_bad_payload(create_client):
    client = create_client("https://www.google.com")
    async with client.http_client() as http_client:
        # server status
        response = await http_client.get("/")

        with pytest.raises(AssertionError, match=r"^initial html validation failed.*"):
            ImmutableServerStatus.parse_payload(response.text)

        with pytest.raises(AssertionError, match=r"^initial html validation failed.*"):
            ImmutableBalancerManager.parse_payload(response.text)


async def test_async_parse_handler(create_client):
    async def _async_parse_handler(handler: Callable):
        warnings.warn("async_parse_handler has executed", UserWarning)
        return True

    client = create_client(async_parse_handler=_async_parse_handler)

    with pytest.warns(UserWarning):
        result = await client._sync_handler(lambda x: None)
    assert result is True
