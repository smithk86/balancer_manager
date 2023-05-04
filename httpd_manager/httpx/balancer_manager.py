import asyncio
import logging
from functools import partial
from typing import Callable

from pydantic import HttpUrl

from .client import http_client
from ..executor import executor
from ..base import (
    BalancerManager,
    Cluster,
    Route,
    ParsedBalancerManager,
)


logger = logging.getLogger(__name__)


class HttpxBalancerManager(BalancerManager):
    async def update(self) -> None:
        client = http_client.get()
        response = await client.get(self.url)
        response.raise_for_status()

        await self._update_from_payload(response.text)

    async def _update_from_payload(self, payload: str) -> None:
        new_model = await self.async_parse_payload(self.url, payload=payload)
        for field, value in new_model:
            setattr(self, field, value)

    @classmethod
    async def parse_from_url(cls, url: str | HttpUrl) -> "HttpxBalancerManager":
        client = http_client.get()
        response = await client.get(url)
        response.raise_for_status()

        return await cls.async_parse_payload(url, response.text)

    @classmethod
    async def async_parse_payload(
        cls, url: str | HttpUrl, payload: str, **kwargs
    ) -> "HttpxBalancerManager":
        _executor = executor.get()
        _loop = asyncio.get_running_loop()
        _func = partial(cls.parse_payload, url=url, payload=payload, **kwargs)
        return await _loop.run_in_executor(_executor, _func)

    @classmethod
    def parse_payload(cls, url: str | HttpUrl, payload: str) -> "HttpxBalancerManager":  # type: ignore[override]
        parsed_model = ParsedBalancerManager.parse_payload(payload)
        model_props = dict(cls._get_parsed_pairs(parsed_model))
        model_props["url"] = url
        return cls.parse_obj(model_props)

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
            raise TypeError(
                "cluster type must be inherited from httpd_manager.base.balancer_manager.Cluster"
            )

        # validate route
        if isinstance(route, str):
            route = cluster.route(route)
        else:
            route = cluster.route(route.name)

        if not isinstance(route, Route):
            raise TypeError(
                "route type must be inherited from httpd_manager.base.balancer_manager.Route"
            )

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
            updated_status_values.disabled is True
            or updated_status_values.draining_mode is True
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

        logger.debug(
            f"edit route cluster={cluster.name} route={route.name} payload={payload}"
        )

        client = http_client.get()
        response = await client.post(
            self.url, headers={"Referer": self.url}, data=payload
        )
        response.raise_for_status()
        await self._update_from_payload(response.text)

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
            raise TypeError(
                "cluster type must be inherited from httpd_manager.base.balancer_manager.Cluster"
            )

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
