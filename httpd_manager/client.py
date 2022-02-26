from __future__ import annotations

import asyncio
import logging
import ssl
import sys
import warnings
from concurrent.futures import Executor
from typing import Any, Optional

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
        self._http_client_kwargs = http_client_kwargs
        self.__http_client: Optional[httpx.AsyncClient] = None

    def __del__(self) -> None:
        if self.__http_client and self.__http_client._state is ClientState.OPENED:
            warnings.warn(
                f"py_httpd_manager.Client for {self.endpoint} "
                "was not properly closed",
                UserWarning,
            )

    @property
    def _http_client(self) -> httpx.AsyncClient:
        if (
            self.__http_client is None
            or self.__http_client._state is ClientState.CLOSED
        ):
            self.__http_client = httpx.AsyncClient(**self._http_client_kwargs)
        return self.__http_client

    async def __aenter__(self) -> Client:
        if self._http_client._state is ClientState.UNOPENED:
            await self._http_client.__aenter__()
        return self

    async def __aexit__(self, *args, **kwargs) -> None:
        if self._http_client._state is not ClientState.CLOSED:
            await self._http_client.__aexit__(*args, **kwargs)

    async def close(self) -> None:
        await self._http_client.aclose()

    @property
    def loop(self) -> asyncio.AbstractEventLoop:
        return asyncio.get_running_loop()

    @property
    def use_lxml(self) -> bool:
        _installed = "lxml" in sys.modules
        return not (self.disable_lxml is True or _installed is False)

    async def run_in_executor(self, *args) -> Any:
        return await self.loop.run_in_executor(self.executor, *args)

    async def get(self, path) -> httpx.Response:
        url = f"{self.endpoint}{path}"
        r = await self._http_client.get(url)
        _raise_for_status(r)
        return r

    async def post(self, path, data) -> httpx.Response:
        url = f"{self.endpoint}{path}"
        r = await self._http_client.post(url, headers={"Referer": url}, data=data)
        _raise_for_status(r)
        return r

    async def server_status(self, include_workers=False) -> ServerStatus:
        return await ServerStatus(self).update(include_workers=include_workers)

    async def balancer_manager(self) -> BalancerManager:
        return await BalancerManager(self).update()
