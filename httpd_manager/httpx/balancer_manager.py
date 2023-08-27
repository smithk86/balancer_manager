from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable
from functools import partial
from typing import Any, Generic, TypeVar

from pydantic import HttpUrl

from ..base.balancer_manager.cluster import Cluster, ClusterType
from ..base.balancer_manager.manager import BalancerManager
from ..base.balancer_manager.route import Route
from ..executor import executor as executor_var
from ..models import ModelWithName
from .client import get_http_client

logger = logging.getLogger(__name__)


class HttpxBalancerManagerBase(BalancerManager[ClusterType], Generic[ClusterType]):
    async def update(self) -> None:
        async with get_http_client() as client:
            response = await client.get(str(self.url))
        response.raise_for_status()
        await self.update_from_payload(response.content)

    async def update_from_payload(self, payload: bytes, **extra: Any) -> None:
        model = await type(self).async_model_validate_payload(self.url, payload, **extra)
        for field, value in model:
            setattr(self, field, value)

    @classmethod
    async def async_model_validate_url(
        cls: type[HttpxBalancerManagerType],
        url: str | HttpUrl,
        context: dict[str, Any] | None = None,
        **extra: Any,
    ) -> HttpxBalancerManagerType:
        async with get_http_client() as client:
            response = await client.get(str(url))
        response.raise_for_status()
        return await cls.async_model_validate_payload(url, response.content, context=context, **extra)

    @classmethod
    async def async_model_validate_payload(
        cls: type[HttpxBalancerManagerType],
        url: str | HttpUrl,
        payload: bytes,
        context: dict[str, Any] | None = None,
        **extra: Any,
    ) -> HttpxBalancerManagerType:
        executor = executor_var.get()
        loop = asyncio.get_running_loop()
        handler = partial(cls.model_validate_payload, url, payload, context=context, **extra)
        return await loop.run_in_executor(executor, handler)

    async def edit_route(
        self,
        cluster: ModelWithName | str,
        route: ModelWithName | str,
        force: bool = False,
        factor: float | None = None,
        lbset: int | None = None,
        route_redir: str | None = None,
        status_changes: dict[str, bool] | None = None,
    ) -> None:
        status_changes = status_changes or {}

        # validate cluster
        cluster = self.cluster(cluster) if isinstance(cluster, str) else self.cluster(cluster.name)

        if not isinstance(cluster, Cluster):
            raise TypeError("cluster type must be inherited from httpd_manager.base.balancer_manager.Cluster")

        # validate route
        route = cluster.route(route) if isinstance(route, str) else cluster.route(route.name)

        if not isinstance(route, Route):
            raise TypeError("route type must be inherited from httpd_manager.base.balancer_manager.Route")

        # get a dict of Status objects
        updated_status_values = route.status.get_mutable_values()

        # prepare new values to be sent to server
        for _name, _value in status_changes.items():
            setattr(updated_status_values, _name, _value)

        # except routes with errors from throwing the "last-route" error
        if (
            force is True
            or route.status.error.value is True
            or route.status.disabled.value is True
            or route.status.draining_mode.value is True
        ):
            pass
        elif cluster.number_of_electable_routes <= 1 and (
            updated_status_values.disabled is True or updated_status_values.draining_mode is True
        ):
            raise ValueError("cannot disable final active route")

        payload = {
            "w_lf": factor if factor else route.factor,
            "w_ls": lbset if lbset else route.lbset,
            "w_wr": route.name,
            "w_rr": route_redir if route_redir else route.route_redir,
            "w": route.worker,
            "b": cluster.name,
            "nonce": str(route.session_nonce_uuid),
        }

        for _name, _status in route.status.mutable().items():
            payload_field = f"w_status_{_status.http_form_code}"
            payload[payload_field] = int(getattr(updated_status_values, _name))

        logger.debug(f"edit route cluster={cluster.name} route={route.name} payload={payload}")

        async with get_http_client() as client:
            response = await client.post(str(self.url), headers={"Referer": str(self.url)}, data=payload)
        response.raise_for_status()
        await self.update_from_payload(response.content)

    async def edit_lbset(
        self,
        cluster: ModelWithName | str,
        lbset_number: int,
        force: bool = False,
        factor: float | None = None,
        route_redir: str | None = None,
        status_changes: dict[str, bool] | None = None,
        exception_handler: Callable[[Exception], None] | None = None,
    ) -> None:
        status_changes = status_changes or {}

        # validate cluster
        cluster = self.cluster(cluster) if isinstance(cluster, str) else self.cluster(cluster.name)

        if not isinstance(cluster, Cluster):
            raise TypeError("cluster type must be inherited from httpd_manager.base.balancer_manager.Cluster")

        for route in cluster.lbset(lbset_number):
            try:
                await self.edit_route(
                    cluster=cluster.name,
                    route=route.name,
                    force=force,
                    factor=factor,
                    route_redir=route_redir,
                    status_changes=status_changes,
                )
            except Exception as e:
                logger.exception(f"route failed to be updated url={self.url} cluster={cluster.name} route={route.name}")
                if exception_handler:
                    exception_handler(e)
                else:
                    raise


HttpxBalancerManagerType = TypeVar("HttpxBalancerManagerType", bound=HttpxBalancerManagerBase[Any])
HttpxBalancerManager = HttpxBalancerManagerBase[Cluster[Route]]
