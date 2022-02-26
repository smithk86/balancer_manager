from __future__ import annotations

import collections.abc
from dataclasses import dataclass
from datetime import datetime

import dateparser
import httpx
from bs4 import BeautifulSoup
from packaging import version
from typing import Any, Dict, List, Optional, TYPE_CHECKING

from .helpers import now, Bytes, RegexPatterns, TypeVersion
from .errors import HttpdManagerError

if TYPE_CHECKING:
    from .client import Client


worker_statuses: Dict[str, str] = {
    "waiting_for_connection": "_",
    "starting_up": "S",
    "reading_request": "R",
    "sending_reply": "W",
    "keepalive": "K",
    "dns_lookup": "D",
    "closing_connection": "C",
    "logging": "L",
    "gracefully_finishing": "G",
    "idle": "I",
    "open": ".",
}


@dataclass(frozen=True)
class WorkerStates:
    closing_connection: int
    dns_lookup: int
    gracefully_finishing: int
    idle: int
    keepalive: int
    logging: int
    open: int
    reading_request: int
    sending_reply: int
    starting_up: int
    waiting_for_connection: int


@dataclass(frozen=True)
class Worker:
    srv: str
    pid: Optional[int]
    acc: str
    m: str
    cpu: float
    ss: int
    req: int
    dur: int
    conn: float
    child: float
    slot: float
    client: str
    protocol: str
    vhost: str
    request: str


@dataclass(frozen=True)
class _RawServerStatusData:
    date: datetime
    version: str
    built_date: str
    restart_date: str
    performance: str
    worker_states: str
    workers: List[str]


class ServerStatus:
    def __init__(self, client: Client):
        if client.server_status_path is None:
            raise HttpdManagerError(
                f"cannot init ServerStatus\nendpoint: {client.endpoint}"
            )

        self.client = client
        self.url = f"{self.client.endpoint}{self.client.server_status_path}"
        self.cached_response: Optional[httpx.Response] = None
        self.date: Optional[datetime] = None
        self.httpd_version: Optional[TypeVersion] = None
        self.httpd_built_date: Optional[datetime] = None
        self.openssl_version: Optional[TypeVersion] = None
        self.restart_date: Optional[datetime] = None
        self.requests_per_sec: Optional[float] = None
        self._bytes_per_second: Optional[Bytes] = None
        self._bytes_per_request: Optional[Bytes] = None
        self.ms_per_request: Optional[float] = None
        self.worker_states: Optional[WorkerStates] = None
        self.workers: Optional[List[Worker]] = None

    async def __aenter__(self) -> ServerStatus:
        await self.client.__aenter__()
        return self

    async def __aexit__(self, *args, **kwargs) -> None:
        await self.client.__aexit__(*args, **kwargs)

    @property
    def bytes_per_second(self) -> Optional[int]:
        return int(self._bytes_per_second) if self._bytes_per_second else None

    @property
    def bytes_per_request(self) -> Optional[int]:
        return int(self._bytes_per_request) if self._bytes_per_request else None

    async def update(self, include_workers: bool = False) -> ServerStatus:
        url = self.client.server_status_path
        self.cached_response = await self.client.get(url)
        raw_data = await self.client.run_in_executor(
            ServerStatus.parse_data,
            self.cached_response,
            self.client.use_lxml,
            include_workers,
        )

        self.date = raw_data.date

        m = RegexPatterns.HTTPD_VERSION.match(raw_data.version)
        self.httpd_version = version.parse(m.group(1))

        m = RegexPatterns.OPENSSL_VERSION.search(raw_data.version)
        self.openssl_version = version.parse(m.group(1))

        m = RegexPatterns.HTTPD_BUILT_DATE.match(raw_data.built_date)
        self.httpd_built_date = dateparser.parse(m.group(1))

        m = RegexPatterns.RESTART_TIME.match(raw_data.restart_date)
        self.restart_date = dateparser.parse(m.group(1))

        # parse instance-wide performance metrics
        m = RegexPatterns.PERFORMANCE_REQUEST_PER_SECOND.search(
            raw_data.performance, strict=False
        )
        self.requests_per_sec = None if m is None else float(m.group(1))

        m = RegexPatterns.PERFORMANCE_BYTES_PER_SECOND.search(
            raw_data.performance, strict=False
        )
        self._bytes_per_second = (
            None if m is None else Bytes(raw=float(m.group(1)), unit=m.group(2))
        )

        m = RegexPatterns.PERFORMANCE_BYTES_PER_REQUEST.search(
            raw_data.performance, strict=False
        )
        self._bytes_per_request = (
            None if m is None else Bytes(raw=float(m.group(1)), unit=m.group(2))
        )

        m = RegexPatterns.PERFORMANCE_MS_PER_REQUEST.search(
            raw_data.performance, strict=False
        )
        self.ms_per_request = None if m is None else float(m.group(1))

        stats_collector = dict()
        for name, val in worker_statuses.items():
            stats_collector[name] = raw_data.worker_states.count(val)
        self.worker_states = WorkerStates(**stats_collector)

        if include_workers is True:
            self.workers = list()
            for raw_worker in raw_data.workers:
                self.workers.append(
                    Worker(
                        srv=raw_worker[0],
                        pid=None if raw_worker[1] == "-" else int(raw_worker[1]),
                        acc=raw_worker[2],
                        m=raw_worker[3],
                        cpu=float(raw_worker[4]),
                        ss=int(raw_worker[5]),
                        req=int(raw_worker[6]),
                        dur=int(raw_worker[7]),
                        conn=float(raw_worker[8]),
                        child=float(raw_worker[9]),
                        slot=float(raw_worker[10]),
                        client=raw_worker[11],
                        protocol=raw_worker[12],
                        vhost=raw_worker[13],
                        request=raw_worker[14],
                    )
                )
        else:
            self.workers = None

        return self

    @staticmethod
    def parse_data(
        response: httpx.Response, use_lxml=True, include_workers: bool = False
    ) -> _RawServerStatusData:
        """
        parse_data() includes xml processing
        and therefor can be a cpu bound task
        """

        data: Dict[str, Any] = dict(
            [
                ("date", now()),
                ("version", None),
                ("built_date", None),
                ("restart_date", None),
                ("performance", None),
                ("worker_states", None),
                ("workers", list()),
            ]
        )

        bs4_features = "lxml" if use_lxml is True else "html.parser"
        bsoup = BeautifulSoup(response.text, features=bs4_features)

        _bs_h1 = bsoup.find_all("h1")
        _bs_dt = bsoup.find_all("dt")
        _bs_table = bsoup.find_all("table")
        _bs_pre = bsoup.find_all("pre")

        if len(_bs_h1) < 1 or "Apache Server Status" not in _bs_h1[0].text:
            raise HttpdManagerError("httpd payload validation failed")

        data["version"] = _bs_dt[0].text
        data["built_date"] = _bs_dt[2].text
        data["restart_date"] = _bs_dt[4].text
        data["performance"] = _bs_dt[11].text
        data["worker_states"] = _bs_pre[0].text.replace("\n", "")

        if include_workers is True:
            rows = iter(_bs_table[0].findAll(lambda tag: tag.name == "tr"))
            next(rows)  # skip header row
            for row in rows:
                cells = [x.text.strip() for x in row.findAll("td")]

                if len(cells) == 15:
                    data["workers"].append(cells)

        return _RawServerStatusData(**data)
