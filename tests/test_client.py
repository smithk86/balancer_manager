import warnings
from typing import Callable
from uuid import uuid4

import pytest
import httpx

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
