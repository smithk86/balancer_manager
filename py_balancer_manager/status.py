from dataclasses import dataclass


@dataclass
class Status:
    value: bool
    immutable: bool
    http_form_code: str


@dataclass
class ValidatedStatus(Status):
    profile: bool
    compliance: bool


@dataclass
class Statuses:
    ok: Status
    error: Status
    ignore_errors: Status
    draining_mode: Status
    disabled: Status
    hot_standby: Status
    hot_spare: Status
    stopped: Status
