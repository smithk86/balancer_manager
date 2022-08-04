import logging
from typing import TYPE_CHECKING

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
        **http_client_kwargs,
    ):
        headers = http_client_kwargs.pop("headers", {})
        headers["Referer"] = base_url
        http_client_kwargs.update({"base_url": base_url, "headers": headers})

        self.base_url: str = base_url
        self.server_status_path: str = server_status_path
        self._balancer_manager_path: str | None = balancer_manager_path
        self.http_client_kwargs = http_client_kwargs

    def http_client(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(**self.http_client_kwargs)

    @property
    def balancer_manager_path(self) -> str:
        assert isinstance(
            self._balancer_manager_path, str
        ), "balancer_manager_path is not defined"
        return self._balancer_manager_path

    async def server_status(self, include_workers=False) -> "ServerStatus":
        from .server_status import ServerStatus

        return await ServerStatus.parse(
            client=self,
            include_workers=include_workers,
        )

    async def balancer_manager(self) -> "BalancerManager":
        from .balancer_manager import BalancerManager

        return await BalancerManager.parse(client=self)
