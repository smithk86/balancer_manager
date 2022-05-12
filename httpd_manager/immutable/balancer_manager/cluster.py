from __future__ import annotations

import logging
from collections import OrderedDict
from typing import Any, Dict, Generator, List, Tuple

from .route import ImmutableRoute

from ...utils import BaseModel, RegexPatterns


logger = logging.getLogger(__name__)


class ImmutableCluster(BaseModel, allow_mutation=False):
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
    routes: Dict[str, ImmutableRoute]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for route in self.routes.values():
            route._cluster = self

    def route(self, name: str):
        return self.routes[name]

    @property
    def health(self) -> bool | None:
        """
        return False if len(self) == 0 or
            if any route.health is False
        """

        if len(self.routes) == 0:
            return None

        for route in self.routes.values():
            if route.health is False:
                return False
        return True

    @property
    def lbsets(self) -> Dict[int, List[ImmutableRoute]]:
        lbset_dict: Dict[int, List[ImmutableRoute]] = dict()
        for route in self.routes.values():
            if route.lbset not in lbset_dict:
                lbset_dict[route.lbset] = list()
            lbset_dict[route.lbset].append(route)
        return OrderedDict(sorted(lbset_dict.items()))

    def lbset(self, number: int) -> List[ImmutableRoute]:
        lbsets = self.lbsets
        assert number in lbsets, f"lbset {number} does not exist in {self.name}"
        return lbsets[number]

    @property
    def active_lbset(self) -> int | None:
        for number, lbset in self.lbsets.items():
            for route in lbset:
                if route.status.ok.value is True:
                    return number
        return None

    @property
    def standby(self) -> bool:
        """
        return True if hot_standby routes are active
        """

        if self.active_lbset is None:
            return False
        else:
            for route in self.lbset(self.active_lbset):
                if (
                    route.status.ok.value is True
                    and route.status.hot_standby.value is False
                ):
                    return False
            return True

    @property
    def number_of_eligible_routes(self) -> int:
        return len(self.eligible_routes())

    def eligible_routes(self) -> List[ImmutableRoute]:
        """
        return list of ImmutableRoutes that are capable of
        accepting incoming traffic
        """

        return list(
            route
            for route in self.routes.values()
            if (
                route.status.error.value is False
                and route.status.disabled.value is False
                and route.status.draining_mode.value is not True
            )
        )

    @staticmethod
    def _get_parsed_pairs(
        obj: Dict[str, str], routes: List[ImmutableRoute]
    ) -> Generator[Tuple[str, Any], None, None]:
        m = RegexPatterns.BALANCER_URI.match(obj["name"])
        name = m.group(1)
        yield ("name", name)

        m = RegexPatterns.ROUTE_USED.match(obj["max_members"])
        yield ("max_members", int(m.group(1)))
        yield ("max_members_used", int(m.group(2)))
        yield (
            "sticky_session",
            None if obj["sticky_session"] == "(None)" else obj["sticky_session"],
        )
        yield ("disable_failover", "On" in obj["disable_failover"])
        yield ("timeout", int(obj["timeout"]))
        yield ("failover_attempts", int(obj["failover_attempts"]))
        yield ("method", obj["method"])
        yield ("path", obj["path"])
        yield ("active", "Yes" in obj["active"])
        yield ("routes", {x.name: x for x in routes if x.cluster == name})
