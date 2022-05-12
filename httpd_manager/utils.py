from __future__ import annotations

import re
from datetime import datetime, timezone
from enum import Enum
from typing import TYPE_CHECKING, Union

from pydantic import BaseModel

if TYPE_CHECKING:
    from pydantic.typing import AbstractSetIntStr, DictStrAny, MappingIntStrAny


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class RegexPatterns(Enum):
    # common
    HTTPD_VERSION: re.Pattern = re.compile(r"^Server\ Version:\ Apache/([\.0-9]*)")
    HTTPD_BUILT_DATE: re.Pattern = re.compile(r"Server Built:\ (.*)")
    OPENSSL_VERSION: re.Pattern = re.compile(r"OpenSSL\/([0-9\.a-z]*)")

    # server status
    RESTART_TIME: re.Pattern = re.compile(r"Restart Time: (.*)")
    REQUEST_PER_SECOND: re.Pattern = re.compile(r"([\d\.]+) requests/sec")
    BYTES_PER_SECOND: re.Pattern = re.compile(r"([\d\.]+)\ (\w?B)/second")
    BYTES_PER_REQUEST: re.Pattern = re.compile(r"([\d\.]+)\ (\w?B)/request")
    MILLISECONDS_PER_REQUEST: re.Pattern = re.compile(r"([\d\.]+) ms/request")

    # balancer manager
    SESSION_NONCE_UUID: re.Pattern = re.compile(r".*&nonce=([-a-f0-9]{36}).*")
    CLUSTER_NAME: re.Pattern = re.compile(r".*\?b=(.*?)&.*")
    BALANCER_URI: re.Pattern = re.compile(r"balancer://(.*)")
    ROUTE_USED: re.Pattern = re.compile(r"^(\d*) \[(\d*) Used\]$")
    BANDWIDTH_USAGE: re.Pattern = re.compile(r"([\d\.]+)([KMGT]?)")

    def match(self, value: str):
        m = self.value.match(value)
        if m is None:
            raise ValueError(f'{self}.match() failed for "{value}"')
        return m

    def search(self, value: str):
        m = self.value.search(value)
        if m is None:
            raise ValueError(f'{self}.search() failed for "{value}"')
        return m


# from https://stackoverflow.com/questions/63264888/pydantic-using-property-getter-decorator-for-a-field-with-an-alias
class PropertyBaseModel(BaseModel):
    """
    Workaround for serializing properties with pydantic until
    https://github.com/samuelcolvin/pydantic/issues/935
    is solved
    """

    @classmethod
    def get_properties(cls):
        return [
            prop
            for prop in dir(cls)
            if isinstance(getattr(cls, prop), property)
            and prop not in ("__values__", "fields")
        ]

    def dict(
        self,
        *,
        include: Union["AbstractSetIntStr", "MappingIntStrAny"] = None,
        exclude: Union["AbstractSetIntStr", "MappingIntStrAny"] = None,
        by_alias: bool = False,
        skip_defaults: bool = None,
        exclude_unset: bool = False,
        exclude_defaults: bool = False,
        exclude_none: bool = False,
    ) -> "DictStrAny":
        attribs = super().dict(
            include=include,
            exclude=exclude,
            by_alias=by_alias,
            skip_defaults=skip_defaults,
            exclude_unset=exclude_unset,
            exclude_defaults=exclude_defaults,
            exclude_none=exclude_none,
        )
        props = self.get_properties()
        # Include and exclude properties
        if include:
            props = [prop for prop in props if prop in include]
        if exclude:
            props = [prop for prop in props if prop not in exclude]

        # Update the attribute dict with the properties
        if props:
            attribs.update({prop: getattr(self, prop) for prop in props})

        return attribs
