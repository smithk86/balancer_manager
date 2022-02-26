from __future__ import annotations

import re
from dataclasses import dataclass, InitVar
from datetime import datetime
from enum import Enum
from typing import Optional, Union

from packaging import version
from pytz import utc

from .errors import HttpdManagerError


TypeVersion = Union[version.LegacyVersion, version.Version]
__all__ = ["Bytes", "HttpxClientWrapper", "now", "RegexPatterns", "TypeVersion"]


def now() -> datetime:
    return datetime.now(utc)


class HttpdVersions(Enum):
    V24: TypeVersion = version.parse("2.4")

    @classmethod
    def validate(cls, version) -> None:
        if version < HttpdVersions.V24.value:
            raise HttpdManagerError(
                "apache httpd versions less than 2.4 are not supported"
            )


class RegexPatterns(Enum):
    # common
    HTTPD_VERSION: re.Pattern = re.compile(r"^Server\ Version:\ Apache/([\.0-9]*)")
    HTTPD_BUILT_DATE: re.Pattern = re.compile(r"Server Built:\ (.*)")
    OPENSSL_VERSION: re.Pattern = re.compile(r"OpenSSL\/([0-9\.a-z]*)")

    # server status
    RESTART_TIME: re.Pattern = re.compile(r"Restart Time: (.*)")
    PERFORMANCE_REQUEST_PER_SECOND: re.Pattern = re.compile(r"([\d\.]+) requests/sec")
    PERFORMANCE_BYTES_PER_SECOND: re.Pattern = re.compile(r"([\d\.]+)\ (\w?B)/second")
    PERFORMANCE_BYTES_PER_REQUEST: re.Pattern = re.compile(r"([\d\.]+)\ (\w?B)/request")
    PERFORMANCE_MS_PER_REQUEST: re.Pattern = re.compile(r"([\d\.]+) ms/request")

    # balancer manager
    SESSION_NONCE_UUID: re.Pattern = re.compile(r".*&nonce=([-a-f0-9]{36}).*")
    CLUSTER_NAME: re.Pattern = re.compile(r".*\?b=(.*?)&.*")
    BALANCER_URI: re.Pattern = re.compile("balancer://(.*)")
    ROUTE_USED: re.Pattern = re.compile(r"^(\d*) \[(\d*) Used\]$")
    BANDWIDTH_USAGE: re.Pattern = re.compile(r"([\d\.]+)([KMGT]?)")

    def match(self, raw_string, strict=True):
        m = self.value.match(raw_string)
        if m is None and strict is True:
            raise ValueError(f'{self}.match() failed for "{raw_string}"')
        return m

    def search(self, raw_string, strict=True):
        m = self.value.search(raw_string)
        if m is None and strict is True:
            raise ValueError(f'{self}.search() failed for "{raw_string}"')
        return m


@dataclass
class Bytes:
    raw: float
    unit: Optional[str]

    def __post_init__(self):
        if not (type(self.raw) is int or type(self.raw) is float):
            raise TypeError("raw value must be int or float")

        self.unit = (
            self.unit[0].upper()
            if (type(self.unit) is str and len(self.unit) > 0)
            else None
        )

    def __int__(self) -> int:
        if self.raw == 0 or not self.unit:
            return 0
        elif self.unit == "B":
            return int(self.raw)
        elif self.unit == "K":
            return int(self.raw * 1000)
        elif self.unit == "M":
            return int(self.raw * 1000000)
        elif self.unit == "G":
            return int(self.raw * 1000000000)
        elif self.unit == "T":
            return int(self.raw * 1000000000000)
        else:
            raise ValueError(f"unit value not supported: {self.unit}")
