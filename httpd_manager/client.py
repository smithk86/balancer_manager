from __future__ import annotations

import asyncio
import logging
import ssl
import sys
import warnings
from concurrent.futures import Executor
from contextvars import ContextVar, Token
from typing import Any, Dict, Optional

import httpx
from httpx._client import ClientState

from .balancer_manager import BalancerManager
from .errors import HttpdManagerError
from .server_status import ServerStatus

logger = logging.getLogger(__name__)


try:
    import lxml  # type: ignore
except ModuleNotFoundError:
    logger.debug("lxml is not installed; " "parsing performance could be impacted")


def _raise_for_status(response: httpx.Response) -> None:
    try:
        response.raise_for_status()
    except httpx.HTTPError as e:
        raise HttpdManagerError(e)


class Client:
    def __init__(
        self,
        endpoint: str,
        server_status_path: str = "/server-status",
        balancer_manager_path: Optional[str] = "/balancer-manager",
        disable_lxml: bool = False,
        executor: Optional[Executor] = None,
        **http_client_kwargs,
    ):
        self.endpoint = endpoint
        self.server_status_path = server_status_path
        self.balancer_manager_path = balancer_manager_path
        self.disable_lxml = disable_lxml
        self.executor = executor
        self._http_client: ContextVar[httpx.AsyncClient] = ContextVar(
            "Client._http_client"
        )
        self._http_client_kwargs: Dict[str, Any] = http_client_kwargs
        self._http_client_token: Optional[Token] = None

    async def __aenter__(self) -> Client:
        if not self.http_client:
            self._http_client_token = self._http_client.set(
                httpx.AsyncClient(**self._http_client_kwargs)
            )
        return self

    async def __aexit__(self, *args, **kwargs) -> None:
        _client = self._http_client.get()
        await _client.aclose()
        if self._http_client_token:
            self._http_client.reset(self._http_client_token)
            self._http_client_token = None

    @property
    def http_client(self) -> Optional[httpx.AsyncClient]:
        return self._http_client.get(None)

    @property
    def loop(self) -> asyncio.AbstractEventLoop:
        return asyncio.get_running_loop()

    @property
    def use_lxml(self) -> bool:
        _installed = "lxml" in sys.modules
        return not (self.disable_lxml is True or _installed is False)

    async def run_in_executor(self, *args) -> Any:
        return await self.loop.run_in_executor(self.executor, *args)

    async def _request(self, method, path, *args, **kwargs) -> httpx.Response:
        url = f"{self.endpoint}{path}"
        headers = kwargs.pop("headers", {})
        headers["Referer"] = url
        if self.http_client:
            _response = await self.http_client.request(
                method, url, *args, headers=headers, **kwargs
            )
        else:
            async with httpx.AsyncClient(**self._http_client_kwargs) as _client:
                _response = await _client.request(
                    method, url, *args, headers=headers, **kwargs
                )
        _raise_for_status(_response)
        return _response

    async def get(self, path) -> httpx.Response:
        return await self._request("get", path)

    async def post(self, path, data) -> httpx.Response:
        return await self._request("post", path, data=data)

    async def server_status(self, include_workers=False) -> ServerStatus:
        return await ServerStatus(self).update(include_workers=include_workers)

    async def balancer_manager(self) -> BalancerManager:
        return await BalancerManager(self).update()

    def __del__(self) -> None:
        if self.http_client and self.http_client._state is ClientState.OPENED:
            warnings.warn(
                f"py_httpd_manager.Client for {self.endpoint} "
                "was not properly closed",
                UserWarning,
            )
