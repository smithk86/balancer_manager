from __future__ import annotations

import collections.abc
import logging
from collections import OrderedDict
from datetime import datetime
from typing import Dict, Iterator, List, Optional, TYPE_CHECKING

from ..errors import HttpdManagerError, MultipleExceptions
from .route import Route

if TYPE_CHECKING:
    from .manager import BalancerManager


logger = logging.getLogger(__name__)


class Cluster(collections.abc.Mapping):
    def __init__(self, balancer_manager, name):
        self.balancer_manager: BalancerManager = balancer_manager
        self.name: str = name
        self.max_members: Optional[int] = None
        self.max_members_used: Optional[int] = None
        self.sticky_session: Optional[str] = None
        self.disable_failover = None
        self.timeout: Optional[int] = None
        self.failover_attempts: Optional[int] = None
        self.method: Optional[str] = None
        self.path: Optional[str] = None
        self.active: Optional[bool] = None
        self._date: Optional[datetime] = None
        self.routes: Dict[str, Route] = dict()

    def __getitem__(self, key: str) -> Route:
        if self.routes is None:
            raise HttpdManagerError(
                "client contains no data\n"
                f"endpoint: {self.balancer_manager.client.endpoint}"
            )

        if key in self.routes:
            return self.routes[key]
        else:
            raise HttpdManagerError(
                "route does not exist\n"
                f"endpoint: {self.balancer_manager.client.endpoint}\n"
                f"cluster: {self.name}\n"
                f"route: {key}"
            )

    def __iter__(self) -> Iterator[str]:
        return iter(self.routes.keys())

    def __len__(self) -> int:
        return len(self.routes)

    @property
    def health(self) -> Optional[bool]:
        """
        return False if len(self) == 0 or
            if any route.health is False
        """

        if len(self) == 0:
            return None

        for route in self.values():
            if route.health is False:
                return False
        return True

    @property
    def lbsets(self) -> Dict[int, List[Route]]:
        lbset_dict: Dict[int, List[Route]] = dict()
        for route in self.values():
            if route.lbset not in lbset_dict:
                lbset_dict[route.lbset] = list()
            lbset_dict[route.lbset].append(route)
        return OrderedDict(sorted(lbset_dict.items()))

    def lbset(self, number) -> List[Route]:
        lbsets = self.lbsets
        if number in lbsets:
            return lbsets[number]
        else:
            raise HttpdManagerError(
                "lbset does not exist\n",
                f"endpoint: {self.balancer_manager.client.endpoint}\n"
                f"lbset number: {number}",
            )

    @property
    def active_lbset(self) -> Optional[int]:
        for number, lbset in self.lbsets.items():
            for route in lbset:
                if route["ok"].value is True:
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
                if route["ok"].value is True and route["hot_standby"].value is False:
                    return False
            return True

    @property
    def eligible_routes(self) -> int:
        return len(self._eligible_routes)

    @property
    def _eligible_routes(self) -> List[Route]:
        """
        return list of Routes that are capable of
        accepting incoming traffic
        """

        return list(
            route
            for route in self.values()
            if (
                route["error"].value is False
                and route["disabled"].value is False
                and route["draining_mode"].value is not True
            )
        )

    async def edit_lbset(
        self,
        lbset_number,
        force: bool = False,
        factor=None,
        lbset=None,
        route_redir=None,
        **status_value_kwargs,
    ) -> None:
        exceptions = []
        for route in self.lbset(lbset_number):
            try:
                await route.edit(
                    force=force,
                    factor=factor,
                    route_redir=route_redir,
                    **status_value_kwargs,
                )
            except Exception as e:
                logger.exception(e)
                exceptions.append(e)
        if len(exceptions) > 0:
            raise MultipleExceptions(exceptions)
