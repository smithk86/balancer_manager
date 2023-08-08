import asyncio
import logging
from functools import partial
from typing import Callable

from pydantic import HttpUrl

from .client import get_http_client
from ..executor import executor as executor_var
from ..base import BalancerManager, Cluster, Route
from ..base.balancer_manager.manager import ValidatorContext


logger = logging.getLogger(__name__)


def parse_values_from_payload(
    url: str | HttpUrl, payload: bytes, context: ValidatorContext | None = None
) -> "HttpxBalancerManager":
    model_values = {"url": str(url)}
    model_values.update(dict(BalancerManager.parse_values_from_payload(payload, context=context)))
    return HttpxBalancerManager.model_validate(model_values)


class HttpxBalancerManager(BalancerManager):
    async def update(self) -> None:
        async with get_http_client() as client:
            response = await client.get(str(self.url))
        response.raise_for_status()
        await self.update_from_payload(response.content)

    async def update_from_payload(self, payload: bytes) -> None:
        new_model = await self.async_model_validate_payload(self.url, payload)
        for field, value in new_model:
            setattr(self, field, value)

    @classmethod
    async def async_model_validate_url(
        cls, url: str | HttpUrl, context: ValidatorContext | None = None
    ) -> "HttpxBalancerManager":
        async with get_http_client() as client:
            response = await client.get(str(url))
        response.raise_for_status()
        return await cls.async_model_validate_payload(url, response.text, context=context)

    @classmethod
    async def async_model_validate_payload(
        cls, url: str | HttpUrl, payload: str | bytes, context: ValidatorContext | None = None
    ) -> "HttpxBalancerManager":
        executor = executor_var.get()
        loop = asyncio.get_running_loop()
        handler = partial(parse_values_from_payload, url, payload, context=context)
        return await loop.run_in_executor(executor, handler)

    async def edit_route(
        self,
        cluster: Cluster | str,
        route: Route | str,
        force: bool = False,
        factor: float | None = None,
        lbset: int | None = None,
        route_redir: str | None = None,
        status_changes: dict[str, bool] = {},
    ) -> None:
        # validate cluster
        if isinstance(cluster, str):
            cluster = self.cluster(cluster)
        else:
            cluster = self.cluster(cluster.name)

        if not isinstance(cluster, Cluster):
            raise TypeError("cluster type must be inherited from httpd_manager.base.balancer_manager.Cluster")

        # validate route
        if isinstance(route, str):
            route = cluster.route(route)
        else:
            route = cluster.route(route.name)

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
        cluster: Cluster | str,
        lbset_number: int,
        force: bool = False,
        factor: float | None = None,
        route_redir: str | None = None,
        status_changes: dict[str, bool] = {},
        exception_handler: Callable | None = None,
    ) -> None:
        # validate cluster
        if isinstance(cluster, str):
            cluster = self.cluster(cluster)
        else:
            cluster = self.cluster(cluster.name)

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
                logger.exception(e)
                if exception_handler:
                    exception_handler(e)
                else:
                    raise
