from contextlib import asynccontextmanager
from contextvars import ContextVar
from typing import Any, AsyncGenerator

from httpx import AsyncClient


http_client: ContextVar[AsyncClient] = ContextVar("http_client")


@asynccontextmanager
async def get_http_client(*args: Any, **kwargs: Any) -> AsyncGenerator[AsyncClient, None]:
    try:
        yield http_client.get()
    except LookupError:
        async with AsyncClient(*args, **kwargs) as client:
            token = http_client.set(client)
            yield client
        http_client.reset(token)
