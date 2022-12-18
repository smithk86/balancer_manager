from __future__ import annotations

import logging
from typing import Any, Generator, TYPE_CHECKING
from uuid import UUID

from pydantic import BaseModel, PrivateAttr

from ...models import Bytes
from ...utils import RegexPatterns
from ...models import ParsableModel


if TYPE_CHECKING:
    from .cluster import Cluster


logger = logging.getLogger(__name__)
__all__ = ["ImmutableStatus", "Route", "Status"]


class BaseStatus(BaseModel, validate_assignment=True):
    pass


class ImmutableStatus(BaseStatus):
    value: bool


class Status(BaseStatus):
    value: bool
    http_form_code: str


class MutableStatusValues(BaseModel, validate_assignment=True, extra="forbid"):
    ignore_errors: bool
    draining_mode: bool
    disabled: bool
    hot_standby: bool
    hot_spare: bool
    stopped: bool


class RouteStatus(BaseModel, validate_assignment=True):
    ok: ImmutableStatus
    error: ImmutableStatus
    ignore_errors: Status
    draining_mode: Status
    disabled: Status
    hot_standby: Status
    hot_spare: Status
    stopped: Status

    def mutable(self) -> dict[str, Status]:
        return {
            name: status
            for name, status in self
            if not isinstance(status, ImmutableStatus)
        }

    def get_mutable_values(self) -> MutableStatusValues:
        return MutableStatusValues(
            ignore_errors=self.ignore_errors.value,
            draining_mode=self.draining_mode.value,
            disabled=self.disabled.value,
            hot_standby=self.hot_standby.value,
            hot_spare=self.hot_spare.value,
            stopped=self.stopped.value,
        )


class Route(ParsableModel, validate_assignment=True):
    name: str
    cluster: str
    worker: str
    priority: int
    route_redir: str
    factor: float
    lbset: int
    elected: int
    busy: int
    load: int
    to_: int
    from_: int
    session_nonce_uuid: UUID
    status: RouteStatus
    accepting_requests: bool = False
    _cluster: Cluster = PrivateAttr()

    def set_cluster(self, cluster: Cluster):
        self._cluster = cluster
        self.accepting_requests = self._get_accepting_requests()

    def _get_accepting_requests(self) -> bool:
        if self.lbset != self._cluster.active_lbset:
            return False
        else:
            return (
                self.status.error.value is False
                and self.status.disabled.value is False
                and self.status.draining_mode.value is False
                and (
                    self.status.hot_standby.value is False
                    or self._cluster.standby is True
                )
            )

    @classmethod
    def _get_parsed_pairs(
        cls, data: dict[str, str], **kwargs
    ) -> Generator[tuple[str, Any], None, None]:
        yield ("name", data["name"])

        m = RegexPatterns.CLUSTER_NAME.match(data["worker_url"])
        yield ("cluster", m.group(1))

        m = RegexPatterns.SESSION_NONCE_UUID.search(data["worker_url"])
        yield ("session_nonce_uuid", m.group(1))

        m = RegexPatterns.BANDWIDTH_USAGE.search(data["to"])
        yield ("to_", int(Bytes(value=m.group(1), unit=m.group(2))))

        m = RegexPatterns.BANDWIDTH_USAGE.search(data["from"])
        yield ("from_", int(Bytes(value=m.group(1), unit=m.group(2))))

        yield ("worker", data["worker"])
        yield ("priority", data["priority"])
        yield ("route_redir", data["route_redir"])
        yield ("factor", data["factor"])
        yield ("lbset", data["lbset"])
        yield ("elected", data["elected"])
        yield ("busy", data["busy"])
        yield ("load", data["load"])

        yield (
            "status",
            RouteStatus(
                ok=ImmutableStatus(value="Ok" in data["active_status_codes"]),
                error=ImmutableStatus(value="Err" in data["active_status_codes"]),
                ignore_errors=Status(
                    http_form_code="I", value="Ign" in data["active_status_codes"]
                ),
                draining_mode=Status(
                    http_form_code="N", value="Drn" in data["active_status_codes"]
                ),
                disabled=Status(
                    http_form_code="D", value="Dis" in data["active_status_codes"]
                ),
                hot_standby=Status(
                    http_form_code="H", value="Stby" in data["active_status_codes"]
                ),
                hot_spare=Status(
                    http_form_code="R", value="Spar" in data["active_status_codes"]
                ),
                stopped=Status(
                    http_form_code="S", value="Stop" in data["active_status_codes"]
                ),
            ),
        )
