from __future__ import annotations

import logging
from collections.abc import Generator
from enum import StrEnum
from typing import TYPE_CHECKING, Annotated, Any
from uuid import UUID

from bs4 import Tag
from pydantic import BaseModel, BeforeValidator, computed_field, field_validator, model_validator

from ...models import Bytes
from ...utils import RegexPatterns

if TYPE_CHECKING:
    from .cluster import Cluster


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

    @model_validator(mode="before")
    @classmethod
    def _model_validator(cls, values: Any) -> dict[str, str]:
        if isinstance(values, dict):
            return values
        if isinstance(values, str):
            m = RegexPatterns.HCHECK_COUNTER.match(values)
            return {"value": m.group(1), "state": m.group(2)}
        raise ValueError("could not parse HealthCheckCounter")


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
    uri: Annotated[str | None, BeforeValidator(strnone_validator)]
    expr: Annotated[str | None, BeforeValidator(strnone_validator)]

    @field_validator("interval_ms", mode="before")
    @classmethod
    def interval_ms_validator(cls, value: Any) -> int:
        if isinstance(value, int):
            return value

        m = RegexPatterns.HCHECK_INTERVAL.match(value)
        return int(m.group(1))


class Route(BaseModel, validate_assignment=True):
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
    hcheck: HealthCheck | None = None
    _cluster: Cluster

    @computed_field  # type: ignore[misc]
    @property
    def electable(self) -> bool:
        """Return true/false if Route is eligible to be used for active traffic."""
        return all(
            [
                self.status.disabled.value is False,
                self.status.draining_mode.value is False,
                self.status.error.value is False,
                self.status.ok.value is True,
                (self.status.hcheck_failure is None or self.status.hcheck_failure.value is False),
            ]
        )

    @classmethod
    def parse_values_from_tags(cls, values: dict[str, Tag]) -> Generator[tuple[str, Any], None, None]:
        status_str = values["Status"].text
        worker_url = values["Worker URL"].find("a")

        if not isinstance(worker_url, Tag):
            raise TypeError(f"worker_uri should be an instance of Tag; got {type(worker_url)}")

        m = RegexPatterns.CLUSTER_NAME.match(str(worker_url["href"]))
        yield ("cluster", m.group(1))

        m = RegexPatterns.SESSION_NONCE_UUID.search(str(worker_url["href"]))
        yield ("session_nonce_uuid", m.group(1))

        m = RegexPatterns.BANDWIDTH_USAGE.search(values["To"].text)
        yield ("to_", int(Bytes(value=m.group(1), unit=m.group(2))))

        m = RegexPatterns.BANDWIDTH_USAGE.search(values["From"].text)
        yield ("from_", int(Bytes(value=m.group(1), unit=m.group(2))))

        yield ("worker", values["Worker URL"].text)
        yield ("route_redir", values["RouteRedir"].text)
        yield ("factor", values["Factor"].text)
        yield ("lbset", values["Set"].text)
        yield ("elected", values["Elected"].text)
        yield ("busy", values["Busy"].text)
        yield ("load", values["Load"].text)

        # add hcheck data if available
        hcheck_failure: dict[str, Any] | None = None
        if "HC Method" in values and values["HC Method"].text != "NONE":
            hcheck_failure = {"value": "HcFl" in status_str}
            yield (
                "hcheck",
                {
                    "method": values["HC Method"].text,
                    "interval_ms": values["HC Interval"].text,
                    "passes": values["Passes"].text,
                    "fails": values["Fails"].text,
                    "uri": values["HC uri"].text,
                    "expr": values["HC Expr"].text,
                },
            )

        yield (
            "status",
            {
                "ok": {"value": "Ok" in status_str},
                "error": {"value": "Err" in status_str},
                "hcheck_failure": hcheck_failure,
                "ignore_errors": {"value": "Ign" in status_str, "http_form_code": "I"},
                "draining_mode": {"value": "Drn" in status_str, "http_form_code": "N"},
                "disabled": {"value": "Dis" in status_str, "http_form_code": "D"},
                "hot_standby": {"value": "Stby" in status_str, "http_form_code": "H"},
                "hot_spare": {"value": "Spar" in status_str, "http_form_code": "R"},
                "stopped": {"value": "Stop" in status_str, "http_form_code": "S"},
            },
        )

    @classmethod
    def model_validate_tags(cls, name: str, priority: int, values: dict[str, Tag]) -> Route:
        model_values = {
            "name": name,
            "priority": priority,
        }
        model_values.update(dict(cls.parse_values_from_tags(values)))
        return cls.model_validate(model_values)
