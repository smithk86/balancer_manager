from contextvars import ContextVar

from httpx import AsyncClient


http_client: ContextVar[AsyncClient] = ContextVar("http_client")
