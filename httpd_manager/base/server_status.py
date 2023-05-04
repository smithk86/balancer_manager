import warnings
from datetime import datetime
from enum import Enum
from typing import Any, Generator

import dateparser
from bs4 import BeautifulSoup
from pydantic import BaseModel, HttpUrl

from ..models import Bytes, ParsableModel
from ..utils import RegexPatterns, utcnow


try:
    import lxml

    lxml_loaded = True
except ModuleNotFoundError:
    lxml_loaded = False
    warnings.warn(
        "lxml is not installed; " "parsing performance could be impacted", UserWarning
    )


class WorkerState(str, Enum):
    WAITING_FOR_CONNECTION = "_"
    STARTING_UP = "S"
    READING_REQUEST = "R"
    SENDING_REPLY = "W"
    KEEPALIVE = "K"
    DNS_LOOKUP = "D"
    CLOSING_CONNECTION = "C"
    LOGGING = "L"
    GRACEFULLY_FINISHING = "G"
    IDLE = "I"
    OPEN = "."


class WorkerStateCount(BaseModel, validate_assignment=True):
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


class Worker(BaseModel, validate_assignment=True):
    srv: str
    pid: int | None
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


class ParsedServerStatus(ParsableModel, validate_assignment=True):
    date: datetime
    httpd_version: str
    httpd_built_date: str
    openssl_version: str
    restart_time: str
    requests_per_sec: str
    bytes_per_second: str
    bytes_per_request: str
    ms_per_request: str
    worker_states: str
    workers: list[list[str]] | None

    @classmethod
    def parse_payload(cls, payload: str, **kwargs) -> "ParsedServerStatus":
        bs4_features = "lxml" if lxml_loaded is True else "html.parser"
        data = BeautifulSoup(payload, features=bs4_features)
        model_data = dict(cls._get_parsed_pairs(data, **kwargs))
        return cls.parse_obj(model_data)

    @classmethod
    def _get_parsed_pairs(
        cls, data: BeautifulSoup, **kwargs
    ) -> Generator[tuple[str, Any], None, None]:
        _include_workers = kwargs.get("include_workers", True)

        # record date of initial parse
        yield ("date", utcnow())

        # initial payload validation
        _bs_h1 = data.find_all("h1")
        if len(_bs_h1) != 1 or "Apache Server Status" not in _bs_h1[0].text:
            raise ValueError(
                "initial html validation failed; is this really an Httpd Server Status page?"
            )

        _bs_dt = data.find_all("dt")
        if len(_bs_dt) != 13:
            raise ValueError(f"13 <dt> tags are expected ({len(_bs_dt)} found)")

        _bs_table = data.find_all("table")
        if len(_bs_table) == 0:
            raise ValueError(
                f"at least 1 <table> tag is expected ({len(_bs_table)} found)"
            )

        _bs_pre = data.find_all("pre")
        if len(_bs_pre) != 1:
            raise ValueError(f"1 <pre> tag is expected ({len(_bs_pre)} found)")

        # parse versions
        yield ("httpd_version", _bs_dt[0].text)
        yield ("openssl_version", _bs_dt[0].text)

        # dates
        yield ("httpd_built_date", _bs_dt[2].text)
        yield ("restart_time", _bs_dt[4].text)

        # performance stats
        yield ("requests_per_sec", _bs_dt[11].text)
        yield ("bytes_per_second", _bs_dt[11].text)
        yield ("bytes_per_request", _bs_dt[11].text)
        yield ("ms_per_request", _bs_dt[11].text)

        # worker statistics
        yield ("worker_states", _bs_pre[0].text.replace("\n", ""))
        if _include_workers is True:
            rows = _bs_table[0].find_all(lambda tag: tag.name == "tr")
            # "rows[1:]" is used to skip the header row of the <table>
            workers = [
                [x.text.strip() for x in row.find_all("td")]
                for row in rows[1:]
                if len(row) == 15
            ]
            yield ("workers", workers)
        else:
            yield ("workers", None)


class ServerStatus(ParsableModel, validate_assignment=True):
    url: HttpUrl
    date: datetime
    httpd_version: str
    httpd_built_date: datetime
    openssl_version: str
    restart_time: datetime
    requests_per_sec: float
    bytes_per_second: int
    bytes_per_request: int
    ms_per_request: float
    worker_states: WorkerStateCount
    workers: list[Worker] | None

    @classmethod
    def parse_payload(cls, payload: str, **kwargs) -> "ServerStatus":
        parsed_model = ParsedServerStatus.parse_payload(payload, **kwargs)
        model_props = dict(cls._get_parsed_pairs(parsed_model, **kwargs))
        return cls.parse_obj(model_props)

    @classmethod
    def _get_parsed_pairs(
        cls, data: ParsedServerStatus, **kwargs
    ) -> Generator[tuple[str, Any], None, None]:
        yield ("date", data.date)
        # versions
        m = RegexPatterns.HTTPD_VERSION.match(data.httpd_version)
        yield ("httpd_version", m.group(1))
        m = RegexPatterns.OPENSSL_VERSION.search(data.openssl_version)
        yield ("openssl_version", m.group(1))

        # dates
        m = RegexPatterns.HTTPD_BUILT_DATE.match(data.httpd_built_date)
        yield (
            "httpd_built_date",
            dateparser.parse(m.group(1), settings={"RETURN_AS_TIMEZONE_AWARE": True}),
        )
        m = RegexPatterns.RESTART_TIME.match(data.restart_time)
        yield (
            "restart_time",
            dateparser.parse(m.group(1), settings={"RETURN_AS_TIMEZONE_AWARE": True}),
        )

        # performance
        try:
            m = RegexPatterns.REQUEST_PER_SECOND.search(data.requests_per_sec)
            yield ("requests_per_sec", m.group(1))
        except ValueError:
            yield ("requests_per_sec", 0)

        try:
            m = RegexPatterns.BYTES_PER_SECOND.search(data.bytes_per_second)
            yield ("bytes_per_second", int(Bytes(unit=m.group(2), value=m.group(1))))
        except ValueError:
            yield ("bytes_per_second", 0)

        try:
            m = RegexPatterns.BYTES_PER_REQUEST.search(data.bytes_per_request)
            yield ("bytes_per_request", int(Bytes(unit=m.group(2), value=m.group(1))))
        except ValueError:
            yield ("bytes_per_request", 0)

        try:
            m = RegexPatterns.MILLISECONDS_PER_REQUEST.search(data.ms_per_request)
            yield ("ms_per_request", m.group(1))
        except ValueError:
            yield ("ms_per_request", 0)

        # count the number of worker in each state
        _worker_states = dict()
        for state_enum in WorkerState:
            _worker_states[state_enum.name.lower()] = data.worker_states.count(
                state_enum.value
            )
        yield ("worker_states", WorkerStateCount.parse_obj(_worker_states))

        if data.workers is None:
            yield ("workers", None)
        else:
            _workers = list()
            for row in data.workers:
                _workers.append(
                    Worker(
                        srv=row[0],
                        pid=None if row[1] == "-" else row[1],
                        acc=row[2],
                        m=row[3],
                        cpu=row[4],
                        ss=row[5],
                        req=row[6],
                        dur=row[7],
                        conn=row[8],
                        child=row[9],
                        slot=row[10],
                        client=row[11],
                        protocol=row[12],
                        vhost=row[13],
                        request=row[14],
                    )
                )
            yield ("workers", _workers)

        for key, val in kwargs.items():
            yield (key, val)
