import re
from datetime import datetime, timezone
from enum import Enum

from bs4 import Tag


def get_table_rows(table: Tag, first_row_index: int = 1) -> list[dict[str, Tag]]:
    rows = table.find_all("tr")
    header = rows[0]
    header_values = [cell.text.strip() for cell in header.find_all("th")]

    results: list[dict[str, Tag]] = []
    for row in rows[first_row_index:]:
        zipped = zip(header_values, row.find_all("td"))
        results.append(dict(zipped))
    return results


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
    HCHECK_INTERVAL: re.Pattern = re.compile(r"^([\d\.]+)ms$")
    HCHECK_COUNTER: re.Pattern = re.compile(r"^([\d\.]+)\ \(([\d\.]+)\)$")

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
