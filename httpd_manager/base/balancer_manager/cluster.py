from __future__ import annotations

import logging
from collections import OrderedDict
from collections.abc import Generator
from typing import TYPE_CHECKING, Any

from bs4 import Tag
from pydantic import BaseModel, computed_field

from ...utils import RegexPatterns
from .route import Route

if TYPE_CHECKING:
    from .manager import BalancerManager

logger = logging.getLogger(__name__)


def get_electable_routes(routes: dict[str, Route]) -> list[Route]:
    """Return list of Routes that are capable of accepting incoming traffic."""
    return [
        route
        for route in routes.values()
        if (
            route.status.error.value is False
            and route.status.disabled.value is False
            and route.status.draining_mode.value is not True
        )
    ]


class Cluster(BaseModel, validate_assignment=True):
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
    _manager: BalancerManager

    @computed_field  # type: ignore[misc]
    @property
    def number_of_electable_routes(self) -> int:
        return len(get_electable_routes(self.routes))

    def route(self, name: str) -> Route:
        return self.routes[name]

    def lbsets(self) -> dict[int, list[Route]]:
        lbset_dict: dict[int, list[Route]] = {}
        for route in self.routes.values():
            if route.lbset not in lbset_dict:
                lbset_dict[route.lbset] = []
            lbset_dict[route.lbset].append(route)
        return OrderedDict(sorted(lbset_dict.items()))

    def lbset(self, number: int) -> list[Route]:
        _lbsets = self.lbsets()
        if number not in _lbsets:
            raise ValueError(f"lbset {number} does not exist")
        return _lbsets[number]

    @classmethod
    def parse_values_from_tags(cls, name: str, values: dict[str, Tag]) -> Generator[tuple[str, Any], None, None]:
        yield ("name", name)
        m = RegexPatterns.ROUTE_USED.match(values["MaxMembers"].text)
        yield ("max_members", int(m.group(1)))
        yield ("max_members_used", int(m.group(2)))
        yield (
            "sticky_session",
            None if values["StickySession"].text == "(None)" else values["StickySession"].text,
        )
        yield ("disable_failover", "On" in values["DisableFailover"].text)
        yield ("timeout", values["Timeout"].text)
        yield ("failover_attempts", values["FailoverAttempts"].text)
        yield ("method", values["Method"].text)
        yield ("path", values["Path"].text)
        yield ("active", "Yes" in values["Active"].text)

    @classmethod
    def model_validate_tags(cls, name: str, values: dict[str, Tag], routes: dict[str, Route]) -> Cluster:
        model_values = dict(cls.parse_values_from_tags(name, values))
        model_values.update({"routes": routes})
        return cls.model_validate(model_values)
