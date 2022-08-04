import asyncio
import logging
from functools import partial
from typing import Any, Callable, TypedDict

from pydantic import PrivateAttr

from .client import Client
from .executor import executor
from .immutable.balancer_manager import (
    ImmutableBalancerManager,
    ImmutableCluster,
    ImmutableRoute,
    ImmutableStatus,
    ParsedBalancerManager,
    RouteStatus,
    Status,
)


Route = ImmutableRoute
Cluster = ImmutableCluster
logger = logging.getLogger(__name__)


class ParseKwargs(TypedDict):
    client: Client


class BalancerManager(ImmutableBalancerManager):
    _client: Client = PrivateAttr()

    class Config:
        allow_mutation = True
        validate_assignment = True

    def __init__(self, *args, **kwargs):
        assert "client" in kwargs, "client argument is required"
        self._client = kwargs["client"]
        super().__init__(*args, **kwargs)

    async def update(self) -> None:
        async with self._client.http_client() as http_client:
            response = await http_client.get(self._client.balancer_manager_path)
        await self._update_from_payload(response.text)

    async def _update_from_payload(self, payload: str) -> None:
        new_model = await self.async_parse_payload(client=self._client, payload=payload)
        for field, value in new_model:
            setattr(self, field, value)

    @classmethod
    async def parse(cls, client: Client) -> "BalancerManager":
        async with client.http_client() as http_client:
            response = await http_client.get(client.balancer_manager_path)
        response.raise_for_status()

        return await cls.async_parse_payload(response.text, client=client)

    @classmethod
    async def async_parse_payload(
        cls, payload: str, client: Client, **kwargs
    ) -> "BalancerManager":
        _executor = executor.get()
        _loop = asyncio.get_running_loop()
        _func = partial(cls.parse_payload, payload=payload, client=client, **kwargs)
        return await _loop.run_in_executor(_executor, _func)

    @classmethod
    def parse_payload(cls, payload: str, **kwargs: ParseKwargs) -> "BalancerManager":
        parsed_model = ParsedBalancerManager.parse_payload(payload, **kwargs)
        model_props = dict(cls._get_parsed_pairs(parsed_model, **kwargs))
        return cls.parse_obj(model_props)

    async def edit_route(
        self,
        cluster: Cluster | str,
        route: Route | str,
        force: bool = False,
        factor: float | None = None,
        lbset: int | None = None,
        route_redir: str | None = None,
        **status_value_kwargs,
    ) -> None:
        # validate cluster
        if isinstance(cluster, str):
            cluster = self.cluster(cluster)
        else:
            cluster = self.cluster(cluster.name)
        assert isinstance(cluster, Cluster)

        # validate route
        if isinstance(route, str):
            route = cluster.route(route)
        else:
            route = cluster.route(route.name)
        assert isinstance(route, Route)

        # get a dict of Status objects
        _status: dict[str, Status] = route.status.mutable()

        # input validation
        for name in status_value_kwargs.keys():
            assert name in _status, f'status "{name}" does not exist'

        status_updates: dict[str, bool] = dict()
        # prepare new values to be sent to server
        for name in _status.keys():
            if name in status_value_kwargs:
                status_updates[name] = status_value_kwargs[name]
            else:
                status_updates[name] = _status[name].value

        # except routes with errors from throwing the "last-route" error
        if (
            force is True
            or route.status.error.value is True
            or route.status.disabled.value is True
            or route.status.draining_mode.value is True
        ):
            pass
        elif cluster.number_of_eligible_routes <= 1 and (
            status_updates.get("disabled") is True
            or status_updates.get("draining_mode") is True
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

        for status_name, new_value in status_updates.items():
            http_form_code = _status[status_name].http_form_code
            payload_field = f"w_status_{http_form_code}"
            payload[payload_field] = int(new_value)

        logger.debug(f"edit route cluster={cluster} route={route} payload={payload}")

        async with self._client.http_client() as http_client:
            response = await http_client.post(
                self._client.balancer_manager_path, data=payload
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
        exception_handler: Callable | None = None,
        **status_value_kwargs,
    ) -> None:
        # validate cluster
        if isinstance(cluster, str):
            cluster = self.cluster(cluster)
        else:
            cluster = self.cluster(cluster.name)
        assert isinstance(cluster, Cluster)

        for route in cluster.lbset(lbset_number):
            try:
                await self.edit_route(
                    cluster=cluster.name,
                    route=route.name,
                    force=force,
                    factor=factor,
                    route_redir=route_redir,
                    **status_value_kwargs,
                )
            except Exception as e:
                logger.exception(e)
                if exception_handler:
                    exception_handler(e)
                else:
                    raise
