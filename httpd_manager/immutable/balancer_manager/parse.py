import warnings
from datetime import datetime
from typing import Any, Generator, Tuple

from bs4 import BeautifulSoup

from ...models import ParsableModel
from ...utils import utcnow


try:
    import lxml as _

    lxml_loaded = True
except ModuleNotFoundError:
    lxml_loaded = False
    warnings.warn(
        "lxml is not installed; " "parsing performance could be impacted", UserWarning
    )


class ParsedBalancerManager(ParsableModel):
    date: datetime
    httpd_version: str
    httpd_built_date: str
    openssl_version: str
    clusters: list[dict[str, str]]
    routes: list[dict[str, str]]

    @classmethod
    def parse_payload(cls, payload: str, **kwargs) -> "ParsedBalancerManager":
        # parse payload with beautiful soup
        bs4_features = "lxml" if lxml_loaded is True else "html.parser"
        data = BeautifulSoup(payload, features=bs4_features)
        model_data = dict(cls._get_parsed_pairs(data, **kwargs))
        return cls.parse_obj(model_data)

    @classmethod
    def _get_parsed_pairs(
        cls, data: BeautifulSoup, **kwargs
    ) -> Generator[Tuple[str, Any], None, None]:
        # record date of initial parse
        yield ("date", utcnow())

        # remove form from page -- this contains extra tables which do not contain clusters or routes
        for form in data.find_all("form"):
            form.extract()

        # initial payload validation
        _bs_h1 = data.find_all("h1")
        assert (
            len(_bs_h1) == 1 and "Load Balancer Manager" in _bs_h1[0].text
        ), "initial html validation failed; is this really an Httpd Balancer Manager page?"

        _bs_dt = data.find_all("dt")
        assert (
            len(_bs_dt) >= 2
        ), f"at least 2 <dt> tags are expected ({len(_bs_dt)} found)"

        _bs_table = data.find_all("table")
        _bs_table_clusters = _bs_table[::2]  # only capture the even indexes
        _bs_table_routes = _bs_table[1::2]  # only capture the even indexes

        yield ("httpd_version", _bs_dt[0].text)
        yield ("httpd_built_date", _bs_dt[1].text)
        yield ("openssl_version", _bs_dt[0].text)

        _clusters = list()
        for table in _bs_table_clusters:
            header_elements = table.findPreviousSiblings("h3", limit=1)
            assert (
                len(header_elements) == 1
            ), f"single <h3> tag is expected ({len(header_elements)} found)"
            header = header_elements[0]

            for row in table.find_all("tr"):
                cells = row.find_all("td")

                if len(cells) == 0:
                    continue

                # Note about sticky_session:
                # there is a workaround for a bug in the html formatting in httpd 2.4.20 in
                # which the StickySession cell closing tag comes after DisableFailover
                # HTML = <td>JSESSIONID<td>Off</td></td>
                _clusters.append(
                    {
                        "name": header.a.text if header.a else header.text,
                        "max_members": cells[0].text,
                        "sticky_session": cells[1]
                        .find(text=True, recursive=False)
                        .strip(),
                        "disable_failover": cells[2].text,
                        "timeout": cells[3].text,
                        "failover_attempts": cells[4].text,
                        "method": cells[5].text,
                        "path": cells[6].text,
                        "active": cells[7].text,
                    }
                )

        yield ("clusters", _clusters)

        _routes = list()
        for table in _bs_table_routes:
            for i, row in enumerate(table.find_all("tr")):
                cells = row.find_all("td")

                if len(cells) == 0:
                    continue

                _routes.append(
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

        yield ("routes", _routes)
