from __future__ import annotations

import collections.abc
import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Dict, Iterator, Optional, Tuple
from uuid import UUID

from ..errors import HttpdManagerError
from ..helpers import Bytes


logger = logging.getLogger(__name__)
__all__ = ["ImmutableStatus", "Route", "Status"]


@dataclass
class ImmutableStatus:
    name: str
    value: bool


@dataclass
class Status(ImmutableStatus):
    http_form_code: Optional[str]


class Route(collections.abc.Mapping):
    def __init__(self, cluster, name):
        self.cluster: Cluster = cluster
        self.name: str = name
        self.worker: Optional[str] = None
        self.priority: Optional[int] = None
        self.route_redir: Optional[str] = None
        self.factor: Optional[float] = None
        self.lbset: Optional[int] = None
        self.elected: Optional[int] = None
        self.busy: Optional[int] = None
        self.load: Optional[int] = None
        self._to: Optional[Bytes] = None
        self._from_: Optional[Bytes] = None
        self.session_nonce_uuid: Optional[UUID] = None
        self.status = Dict[str, ImmutableStatus]
        self._date = Optional[datetime]

    def __getitem__(self, key: str) -> Status:
        if self.status is None:
            raise HttpdManagerError(
                "client contains no data\n"
                f"endpoint: {self.cluster.balancer_manager.client.endpoint}"
            )

        if key in self.status:
            return self.status[key]
        else:
            raise HttpdManagerError(
                "status does not exist\n"
                f"endpoint: {self.cluster.balancer_manager.client.endpoint}\n"
                f"cluster: {self.cluster.name}\n"
                f"route: {self.name}\n"
                f"status: {key}"
            )

    def __iter__(self) -> Iterator[str]:
        return iter(self.status.keys())

    def __len__(self) -> int:
        return len(self.status)

    def mutable_keys(self) -> Iterator[str]:
        return iter(
            key for key in self.__iter__() if type(self[key]) is not ImmutableStatus
        )

    def mutable_values(self) -> Iterator[Status]:
        return iter(val for val in self.values() if type(val) is not ImmutableStatus)

    def mutable_items(self) -> Iterator[Tuple[str, Status]]:
        return iter(
            (key, val) for key, val in self.items() if type(val) is not ImmutableStatus
        )

    @property
    def to(self) -> Optional[int]:
        return int(self._to) if self._to else None

    @property
    def from_(self) -> Optional[int]:
        return int(self._from_) if self._from_ else None

    @property
    def health(self) -> bool:
        """
        return False if self['error'] does not exist or
            if self['error'].value is True
        return True otherwise
        """

        return False if ("error" not in self or self["error"].value is True) else True

    @property
    def accepting_requests(self) -> bool:
        if self.lbset != self.cluster.active_lbset:
            return False
        else:
            return (
                self["error"].value is False
                and self["disabled"].value is False
                and self["draining_mode"].value is False
                and (self["hot_standby"].value is False or self.cluster.standby is True)
            )

    async def edit(
        self,
        force=False,
        factor=None,
        lbset=None,
        route_redir=None,
        **status_value_kwargs,
    ):

        # input validation
        for status_name in status_value_kwargs.keys():
            if status_name not in self:
                raise HttpdManagerError(f"invalid status name\nname: {status_name}")
            elif type(self[status_name]) is ImmutableStatus:
                raise HttpdManagerError(f"status is immutable\nname: {status_name}")

        status_updates = dict()

        # prepare new values to be sent to server
        for name in self.mutable_keys():
            if name in status_value_kwargs:
                status_updates[name] = status_value_kwargs[name]
            else:
                status_updates[name] = self[name].value

        # except routes with errors from throwing the "last-route" error
        if (
            force is True
            or self["error"] is True
            or self["disabled"] is True
            or self["draining_mode"] is True
        ):
            pass
        elif self.cluster.eligible_routes <= 1 and (
            status_updates.get("disabled") is True
            or status_updates.get("draining_mode") is True
        ):
            raise HttpdManagerError(
                "cannot disable final active route"
                f"endpoint: {self.cluster.balancer_manager.client.endpoint}\n"
                f"cluster: {self.cluster.name}\n"
                f"route: {self.name}"
            )

        payload = {
            "w_lf": factor if factor else self.factor,
            "w_ls": lbset if lbset else self.lbset,
            "w_wr": self.name,
            "w_rr": route_redir if route_redir else self.route_redir,
            "w": self.worker,
            "b": self.cluster.name,
            "nonce": str(self.session_nonce_uuid),
        }

        for status_name, new_value in status_updates.items():
            http_form_code = self[status_name].http_form_code
            payload_field = f"w_status_{http_form_code}"
            payload[payload_field] = int(new_value)

        logger.debug(
            "edit payload",
            {"cluster": self.cluster.name, "route": self.name, "payload": payload},
        )

        await self.cluster.balancer_manager.update(data=payload)

        # validate new values against load balancer
        for status_name, expected_value in status_updates.items():
            current_value = self[status_name].value
            if expected_value is not current_value:
                raise HttpdManagerError(
                    "status value is incorrect"
                    f"name: {status_name}\n"
                    f"value: {current_value}\n"
                    f"expected: {expected_value}"
                )
