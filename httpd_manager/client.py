from __future__ import annotations

import logging
from contextvars import ContextVar
from functools import partial
from inspect import iscoroutinefunction
from typing import Any, Callable, Dict, TYPE_CHECKING

import httpx


if TYPE_CHECKING:
    from .balancer_manager import BalancerManager
    from .server_status import ServerStatus


logger = logging.getLogger(__name__)


class Client:
    def __init__(
        self,
        base_url: str,
        server_status_path="/server-status",
        balancer_manager_path="/balancer-manager",
        async_parse_handler=None,
        **http_client_kwargs,
    ):
        headers = http_client_kwargs.pop("headers", {})
        headers["Referer"] = base_url
        http_client_kwargs.update({"base_url": base_url, "headers": headers})

        assert not (
            async_parse_handler and not iscoroutinefunction(async_parse_handler)
        ), "async_parse_handler must be a coroutine"

        self.server_status_path: str = server_status_path
        self.balancer_manager_path: str | None = balancer_manager_path
        self.async_parse_handler: Callable | None = async_parse_handler
        self.http_client_kwargs = http_client_kwargs

    def http_client(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(**self.http_client_kwargs)

    async def _sync_handler(self, handler: Callable, *args, **kwargs) -> Any:
        assert not iscoroutinefunction(handler), "handler must not be a coroutine"
        if self.async_parse_handler:
            return await self.async_parse_handler(partial(handler, *args, **kwargs))
        else:
            return handler(*args, **kwargs)

    async def server_status(self, include_workers=False) -> ServerStatus:
        from .server_status import ServerStatus

        return await ServerStatus.create(
            client=self,
            include_workers=include_workers,
        )

    async def balancer_manager(self, use_lxml=True) -> BalancerManager:
        from .balancer_manager import BalancerManager

        return await BalancerManager.create(client=self)
