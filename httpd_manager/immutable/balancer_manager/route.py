from __future__ import annotations

import logging
from typing import Any, Dict, Generator, Tuple, TYPE_CHECKING
from uuid import UUID

import httpx
from pydantic import validator, PrivateAttr
from pydantic.fields import ModelField, Field

from ...models import Bytes
from ...utils import RegexPatterns, PropertyBaseModel as BaseModel


if TYPE_CHECKING:
    from .cluster import ImmutableCluster


logger = logging.getLogger(__name__)
__all__ = ["ImmutableStatus", "Route", "Status"]


class BaseStatus(BaseModel):
    pass


class ImmutableStatus(BaseStatus, allow_mutation=False):
    value: bool


class Status(BaseStatus):
    value: bool
    http_form_code: str


class RouteStatus(BaseModel):
    ok: ImmutableStatus
    error: ImmutableStatus
    ignore_errors: Status
    draining_mode: Status
    disabled: Status
    hot_standby: Status
    hot_spare: Status
    stopped: Status

    def mutable(self) -> Dict[str, Status]:
        return {
            name: status
            for name, status in self
            if not isinstance(status, ImmutableStatus)
        }


class ImmutableRoute(BaseModel, validate_assignment=True):
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
    _cluster: ImmutableCluster = PrivateAttr()

    @property
    def health(self) -> bool:
        """
        return False if self['error'] does not exist or
            if self['error'].value is True
        return True otherwise
        """

        return False if self.status.error.value is True else True

    @property
    def accepting_requests(self) -> bool:
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

    @staticmethod
    def _get_parsed_pairs(
        obj: Dict[str, str]
    ) -> Generator[Tuple[str, Any], None, None]:
        yield ("name", obj["name"])

        m = RegexPatterns.CLUSTER_NAME.match(obj["worker_url"])
        yield ("cluster", m.group(1))

        m = RegexPatterns.SESSION_NONCE_UUID.search(obj["worker_url"])
        yield ("session_nonce_uuid", m.group(1))

        m = RegexPatterns.BANDWIDTH_USAGE.search(obj["to"])
        yield ("to_", int(Bytes(value=m.group(1), unit=m.group(2))))

        m = RegexPatterns.BANDWIDTH_USAGE.search(obj["from"])
        yield ("from_", int(Bytes(value=m.group(1), unit=m.group(2))))

        yield ("worker", obj["worker"])
        yield ("priority", obj["priority"])
        yield ("route_redir", obj["route_redir"])
        yield ("factor", obj["factor"])
        yield ("lbset", obj["lbset"])
        yield ("elected", obj["elected"])
        yield ("busy", obj["busy"])
        yield ("load", obj["load"])

        yield (
            "status",
            RouteStatus(
                ok=ImmutableStatus(value="Ok" in obj["active_status_codes"]),
                error=ImmutableStatus(value="Err" in obj["active_status_codes"]),
                ignore_errors=Status(
                    http_form_code="I", value="Ign" in obj["active_status_codes"]
                ),
                draining_mode=Status(
                    http_form_code="N", value="Drn" in obj["active_status_codes"]
                ),
                disabled=Status(
                    http_form_code="D", value="Dis" in obj["active_status_codes"]
                ),
                hot_standby=Status(
                    http_form_code="H", value="Stby" in obj["active_status_codes"]
                ),
                hot_spare=Status(
                    http_form_code="R", value="Spar" in obj["active_status_codes"]
                ),
                stopped=Status(
                    http_form_code="S", value="Stop" in obj["active_status_codes"]
                ),
            ),
        )
