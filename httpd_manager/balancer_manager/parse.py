from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List

from bs4 import BeautifulSoup

from ..errors import HttpdManagerError
from ..helpers import now


@dataclass
class ParsedBalancerManager:
    date: datetime = field(init=False)
    version: str
    built_date: str
    clusters: List[Dict[str, str]]
    routes: List[Dict[str, str]]

    def __post_init__(self):
        self.date = now()


def parse(request, use_lxml=True) -> ParsedBalancerManager:
    # parse payload with beautiful soup
    bs4_features = "lxml" if use_lxml is True else "html.parser"
    bsoup = BeautifulSoup(request.text, features=bs4_features)

    _data: Dict[str, Any] = dict(
        [
            ("version", None),
            ("built_date", None),
            ("clusters", list()),
            ("routes", list()),
        ]
    )

    # remove form from page -- this contains extra tables which do not contain clusters or routes
    for form in bsoup.find_all("form"):
        form.extract()

    # initial bs4 parsing
    _bs_h1 = bsoup.find_all("h1")
    _bs_dt = bsoup.find_all("dt")
    _bs_tables = bsoup.find_all("table")
    _bs_table_clusters = _bs_tables[::2]
    _bs_table_routes = _bs_tables[1::2]

    if len(_bs_h1) < 1 or "Load Balancer Manager" not in _bs_h1[0].text:
        raise HttpdManagerError("payload validation failed")

    if len(_bs_dt) >= 1:
        _data["version"] = _bs_dt[0].text

    if len(_bs_dt) >= 2:
        _data["built_date"] = _bs_dt[1].text

    # only iterate through odd tables which contain cluster data
    for table in _bs_table_clusters:
        header_elements = table.findPreviousSiblings("h3", limit=1)
        if len(header_elements) == 1:
            header = header_elements[0]
        else:
            raise HttpdManagerError("single h3 element is required but not found")

        for row in table.find_all("tr"):
            cells = row.find_all("td")

            if len(cells) == 0:
                continue

            # Note about sticky_session:
            # there is a workaround for a bug in the html formatting in httpd 2.4.20 in
            # which the StickySession cell closing tag comes after DisableFailover
            # HTML = <td>JSESSIONID<td>Off</td></td>
            _data["clusters"].append(
                {
                    "name": header.a.text if header.a else header.text,
                    "max_members": cells[0].text,
                    "sticky_session": cells[1].find(text=True, recursive=False).strip(),
                    "disable_failover": cells[2].text,
                    "timeout": cells[3].text,
                    "failover_attempts": cells[4].text,
                    "method": cells[5].text,
                    "path": cells[6].text,
                    "active": cells[7].text,
                }
            )

    # only iterate through even tables which contain route data
    for table in _bs_table_routes:
        for i, row in enumerate(table.find_all("tr")):
            cells = row.find_all("td")

            if len(cells) == 0:
                continue

            _data["routes"].append(
                {
                    "name": cells[1].text,
                    "worker_url": cells[0].find("a")["href"],
                    "worker": cells[0].find("a").text,
                    "priority": i,
                    "route_redir": cells[2].text,
                    "factor": cells[3].text,
                    "lbset": cells[4].text,
                    "elected": cells[6].text,
                    "busy": cells[7].text,
                    "load": cells[8].text,
                    "to": cells[9].text,
                    "from": cells[10].text,
                    "active_status_codes": cells[5].text,
                }
            )

    return ParsedBalancerManager(**_data)
