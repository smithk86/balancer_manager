import warnings
from datetime import datetime
from enum import Enum
from typing import Any, Generator

import dateparser
from bs4 import BeautifulSoup
from pydantic import BaseModel, HttpUrl

from ..models import Bytes
from ..utils import RegexPatterns, get_table_rows, lxml_is_loaded, utcnow


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


class ServerStatus(BaseModel, validate_assignment=True):
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
    workers: list[Worker] | None = None

    @classmethod
    def parse_values_from_payload(
        cls, payload: str | bytes, include_workers: bool = True
    ) -> Generator[tuple[str, Any], None, None]:
        if lxml_is_loaded:
            bs = BeautifulSoup(payload, features="lxml")
        else:
            bs = BeautifulSoup(payload)

        yield ("date", utcnow())

        # initial payload validation
        _bs_h1 = bs.find_all("h1")
        if len(_bs_h1) != 1 or "Apache Server Status" not in _bs_h1[0].text:
            raise ValueError("initial html validation failed; is this really an Httpd Server Status page?")

        _bs_dt = bs.find_all("dt")
        if len(_bs_dt) != 13:
            raise ValueError(f"13 <dt> tags are expected ({len(_bs_dt)} found)")

        _bs_table = bs.find_all("table")
        if len(_bs_table) == 0:
            raise ValueError(f"at least 1 <table> tag is expected ({len(_bs_table)} found)")

        _bs_pre = bs.find_all("pre")
        if len(_bs_pre) != 1:
            raise ValueError(f"1 <pre> tag is expected ({len(_bs_pre)} found)")

        # versions
        m = RegexPatterns.HTTPD_VERSION.match(_bs_dt[0].text)
        yield ("httpd_version", m.group(1))
        m = RegexPatterns.OPENSSL_VERSION.search(_bs_dt[0].text)
        yield ("openssl_version", m.group(1))

        # dates
        m = RegexPatterns.HTTPD_BUILT_DATE.match(_bs_dt[2].text)
        yield (
            "httpd_built_date",
            dateparser.parse(m.group(1), settings={"RETURN_AS_TIMEZONE_AWARE": True}),
        )
        m = RegexPatterns.RESTART_TIME.match(_bs_dt[4].text)
        yield (
            "restart_time",
            dateparser.parse(m.group(1), settings={"RETURN_AS_TIMEZONE_AWARE": True}),
        )

        # performance
        try:
            m = RegexPatterns.REQUEST_PER_SECOND.search(_bs_dt[11].text)
            yield ("requests_per_sec", m.group(1))
        except ValueError:
            yield ("requests_per_sec", 0)

        try:
            m = RegexPatterns.BYTES_PER_SECOND.search(_bs_dt[11].text)
            yield ("bytes_per_second", int(Bytes(unit=m.group(2), value=m.group(1))))
        except ValueError:
            yield ("bytes_per_second", 0)

        try:
            m = RegexPatterns.BYTES_PER_REQUEST.search(_bs_dt[11].text)
            yield ("bytes_per_request", int(Bytes(unit=m.group(2), value=m.group(1))))
        except ValueError:
            yield ("bytes_per_request", 0)

        try:
            m = RegexPatterns.MILLISECONDS_PER_REQUEST.search(_bs_dt[11].text)
            yield ("ms_per_request", m.group(1))
        except ValueError:
            yield ("ms_per_request", 0)

        # count the number of worker in each state
        worker_states_str = _bs_pre[0].text.replace("\n", "")
        worker_states = dict()
        for state_enum in WorkerState:
            worker_states[state_enum.name.lower()] = worker_states_str.count(state_enum.value)
        yield ("worker_states", worker_states)

        # worker statistics
        if include_workers is True:
            workers = list()
            for worker in get_table_rows(_bs_table[0]):
                # the first rows are not worker data
                if "Srv" not in worker:
                    continue

                workers.append(
                    Worker(
                        srv=worker["Srv"].text.strip(),
                        pid=None if worker["PID"].text.strip() == "-" else worker["PID"].text.strip(),
                        acc=worker["Acc"].text.strip(),
                        m=worker["M"].text.strip(),
                        cpu=worker["CPU"].text.strip(),
                        ss=worker["SS"].text.strip(),
                        req=worker["Req"].text.strip(),
                        dur=worker["Dur"].text.strip(),
                        conn=worker["Conn"].text.strip(),
                        child=worker["Child"].text.strip(),
                        slot=worker["Slot"].text.strip(),
                        client=worker["Client"].text.strip(),
                        protocol=worker["Protocol"].text.strip(),
                        vhost=worker["VHost"].text.strip(),
                        request=worker["Request"].text.strip(),
                    )
                )
            yield ("workers", workers)

    @classmethod
    def model_validate_payload(
        cls, url: str | HttpUrl, payload: str | bytes, include_workers: bool = True
    ) -> "ServerStatus":
        model_values = {"url": str(url)}
        model_values.update(dict(cls.parse_values_from_payload(payload, include_workers)))
        return cls.model_validate(model_values)
