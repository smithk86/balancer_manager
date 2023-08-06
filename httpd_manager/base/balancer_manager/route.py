from __future__ import annotations

import logging
from enum import StrEnum
from typing import Any, Generator
from uuid import UUID

from pydantic import BaseModel, validator

from ...models import Bytes
from ...utils import RegexPatterns
from ...models import ParsableModel


logger = logging.getLogger(__name__)
__all__ = ["ImmutableStatus", "Route", "Status"]


def strnone_validator(value: Any) -> str | None:
    if isinstance(value, str) and len(value) > 0:
        return value
    return None


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
    hcheck_failure: ImmutableStatus | None
    ignore_errors: Status
    draining_mode: Status
    disabled: Status
    hot_standby: Status
    hot_spare: Status
    stopped: Status

    def mutable(self) -> dict[str, Status]:
        return {name: status for name, status in self if status and not isinstance(status, ImmutableStatus)}

    def get_mutable_values(self) -> MutableStatusValues:
        return MutableStatusValues(
            ignore_errors=self.ignore_errors.value,
            draining_mode=self.draining_mode.value,
            disabled=self.disabled.value,
            hot_standby=self.hot_standby.value,
            hot_spare=self.hot_spare.value,
            stopped=self.stopped.value,
        )


class HealthCheckCounter(BaseModel):
    value: int
    state: int

    @classmethod
    def parse(cls, value: str | dict[str, Any]) -> HealthCheckCounter:
        if isinstance(value, dict):
            return cls.parse_obj(value)

        m = RegexPatterns.HCHECK_COUNTER.match(value)
        return cls(value=m.group(1), state=m.group(2))


class HealthCheckMethod(StrEnum):
    tcp = "TCP"
    options = "OPTIONS"
    head = "HEAD"
    get = "GET"
    options11 = "OPTIONS11"
    head11 = "HEAD11"
    get11 = "GET11"


class HealthCheck(BaseModel, validate_assignment=True):
    method: HealthCheckMethod
    interval_ms: int
    passes: HealthCheckCounter
    fails: HealthCheckCounter
    uri: str | None
    expr: str | None

    @validator("interval_ms", pre=True)
    def interval_ms_validator(cls, value: Any) -> int:
        if isinstance(value, int):
            return value

        m = RegexPatterns.HCHECK_INTERVAL.match(value)
        return int(m.group(1))

    # reuse validators
    _passes_validator = validator("passes", allow_reuse=True, pre=True)(HealthCheckCounter.parse)
    _fails_validator = validator("fails", allow_reuse=True, pre=True)(HealthCheckCounter.parse)
    _uri_validator = validator("uri", allow_reuse=True)(strnone_validator)
    _expr_validator = validator("expr", allow_reuse=True)(strnone_validator)


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
    hcheck: HealthCheck | None

    @property
    def electable(self) -> bool:
        """
        Return true/false if Route is eligible to be used for active traffic.
        """

        return all(
            [
                self.status.disabled.value is False,
                self.status.draining_mode.value is False,
                self.status.error.value is False,
                self.status.ok.value is True,
            ]
        )

    @classmethod
    def _get_parsed_pairs(cls, data: dict[str, str], **kwargs) -> Generator[tuple[str, Any], None, None]:
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
        yield ("hcheck", data["hcheck"])

        hcheck_failure = ImmutableStatus(value="HcFl" in data["active_status_codes"]) if data["hcheck"] else None

        yield (
            "status",
            RouteStatus(
                ok=ImmutableStatus(value="Ok" in data["active_status_codes"]),
                error=ImmutableStatus(value="Err" in data["active_status_codes"]),
                hcheck_failure=hcheck_failure,
                ignore_errors=Status(http_form_code="I", value="Ign" in data["active_status_codes"]),
                draining_mode=Status(http_form_code="N", value="Drn" in data["active_status_codes"]),
                disabled=Status(http_form_code="D", value="Dis" in data["active_status_codes"]),
                hot_standby=Status(http_form_code="H", value="Stby" in data["active_status_codes"]),
                hot_spare=Status(http_form_code="R", value="Spar" in data["active_status_codes"]),
                stopped=Status(http_form_code="S", value="Stop" in data["active_status_codes"]),
            ),
        )
