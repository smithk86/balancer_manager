from __future__ import annotations

import logging
from collections import OrderedDict
from typing import Any, Generator

from pydantic import validator

from .route import Route
from ...utils import RegexPatterns
from ...models import ParsableModel


logger = logging.getLogger(__name__)


def get_electable_routes(routes: dict[str, Route]) -> list[Route]:
    """
    return list of Routes that are capable of
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


class Cluster(ParsableModel, validate_assignment=True):
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
    routes: dict[str, Route]
    number_of_electable_routes: int = 0

    @validator("number_of_electable_routes", always=True)
    def validator_number_of_electable_routes(cls, _, values) -> int:
        return len(get_electable_routes(values.get("routes", {})))

    def route(self, name: str):
        return self.routes[name]

    def lbsets(self) -> dict[int, list[Route]]:
        lbset_dict: dict[int, list[Route]] = dict()
        for route in self.routes.values():
            if route.lbset not in lbset_dict:
                lbset_dict[route.lbset] = list()
            lbset_dict[route.lbset].append(route)
        return OrderedDict(sorted(lbset_dict.items()))

    def lbset(self, number: int) -> list[Route]:
        _lbsets = self.lbsets()
        if number not in _lbsets:
            raise ValueError(f"lbset {number} does not exist")
        return _lbsets[number]

    @classmethod
    def _get_parsed_pairs(
        cls, data: dict[str, str], **kwargs
    ) -> Generator[tuple[str, Any], None, None]:
        _routes: list[Route] = kwargs.get("routes", [])

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
