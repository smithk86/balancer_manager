from __future__ import annotations

import logging
from collections import OrderedDict
from typing import Any, Generator

from pydantic import validator

from .route import ImmutableRoute
from ...utils import RegexPatterns
from ...models import ParsableModel


logger = logging.getLogger(__name__)


class ImmutableCluster(ParsableModel, allow_mutation=False):
    name: str
    max_members: int
    max_members_used: int
    sticky_session: str | None
    disable_failover: bool
    timeout: int
    failover_attempts: int
    method: str
    path: str
    active: bool
    routes: dict[str, ImmutableRoute]
    active_lbset: int | None = None
    number_of_eligible_routes: int = 0
    standby: bool = False

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for route in self.routes.values():
            route.set_cluster(self)

    @validator("active_lbset", always=True)
    def _get_active_lbset(cls, v, values) -> int | None:
        _lbsets = cls._get_lbsets(values["routes"])
        for number, lbset in _lbsets.items():
            for route in lbset:
                if route.status.ok.value is True:
                    return number
        return None

    @validator("standby", always=True)
    def _get_standby(cls, v, values) -> bool:
        """
        return True if hot_standby routes are active
        """

        if values["active_lbset"] is None:
            return False
        else:
            for route in cls._get_lbset(values["routes"], values["active_lbset"]):
                if (
                    route.status.ok.value is True
                    and route.status.hot_standby.value is False
                ):
                    return False
            return True

    @validator("number_of_eligible_routes", always=True)
    def _get_number_of_eligible_routes(cls, v, values) -> int:
        return len(cls._get_eligible_routes(values["routes"]))

    def route(self, name: str):
        return self.routes[name]

    def lbsets(self) -> dict[int, list[ImmutableRoute]]:
        return self._get_lbsets(self.routes)

    def lbset(self, number: int) -> list[ImmutableRoute]:
        return self._get_lbset(self.routes, number)

    def eligible_routes(self) -> list[ImmutableRoute]:
        return self._get_eligible_routes(self.routes)

    @staticmethod
    def _get_eligible_routes(routes: dict[str, ImmutableRoute]) -> list[ImmutableRoute]:
        """
        return list of ImmutableRoutes that are capable of
        accepting incoming traffic
        """

        return [
            route
            for route in routes.values()
            if (
                route.status.error.value is False
                and route.status.disabled.value is False
                and route.status.draining_mode.value is not True
            )
        ]

    @staticmethod
    def _get_lbsets(
        routes: dict[str, ImmutableRoute]
    ) -> dict[int, list[ImmutableRoute]]:
        lbset_dict: dict[int, list[ImmutableRoute]] = dict()
        for route in routes.values():
            if route.lbset not in lbset_dict:
                lbset_dict[route.lbset] = list()
            lbset_dict[route.lbset].append(route)
        return OrderedDict(sorted(lbset_dict.items()))

    @classmethod
    def _get_lbset(
        cls, routes: dict[str, ImmutableRoute], number: int
    ) -> list[ImmutableRoute]:
        _lbsets = cls._get_lbsets(routes)
        assert number in _lbsets, f"lbset {number} does not exist"
        return _lbsets[number]

    @classmethod
    def _get_parsed_pairs(
        cls, data: dict[str, str], **kwargs
    ) -> Generator[tuple[str, Any], None, None]:
        _routes: list[ImmutableRoute] = kwargs.get("routes", [])

        m = RegexPatterns.BALANCER_URI.match(data["name"])
        name = m.group(1)
        yield ("name", name)

        m = RegexPatterns.ROUTE_USED.match(data["max_members"])
        yield ("max_members", int(m.group(1)))
        yield ("max_members_used", int(m.group(2)))
        yield (
            "sticky_session",
            None if data["sticky_session"] == "(None)" else data["sticky_session"],
        )
        yield ("disable_failover", "On" in data["disable_failover"])
        yield ("timeout", int(data["timeout"]))
        yield ("failover_attempts", int(data["failover_attempts"]))
        yield ("method", data["method"])
        yield ("path", data["path"])
        yield ("active", "Yes" in data["active"])
        yield ("routes", {x.name: x for x in _routes if x.cluster == name})
