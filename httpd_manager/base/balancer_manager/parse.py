import warnings
from datetime import datetime
from typing import Any, Generator, cast

from bs4 import BeautifulSoup, Tag

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


def get_table_rows(table: Tag) -> list[dict[str, Tag]]:
    rows = table.find_all("tr")
    header = rows[0]
    header_values = [cell.text for cell in header.find_all("th")]

    results: list[dict[str, Tag]] = []
    for row in rows[1:]:
        zipped = zip(header_values, row.find_all("td"))
        results.append(dict(zipped))
    return results


class ParsedBalancerManager(ParsableModel):
    date: datetime
    httpd_version: str
    httpd_built_date: str
    openssl_version: str
    clusters: list[dict[str, Any]]
    routes: list[dict[str, Any]]

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
    ) -> Generator[tuple[str, Any], None, None]:
        # record date of initial parse
        yield ("date", utcnow())

        # remove form from page -- this contains extra tables which do not contain clusters or routes
        for form in data.find_all("form"):
            form.extract()

        # initial payload validation
        _bs_h1 = data.find_all("h1")
        if len(_bs_h1) != 1 or "Load Balancer Manager" not in _bs_h1[0].text:
            raise ValueError(
                "initial html validation failed; is this really an Httpd Balancer Manager page?"
            )

        _bs_dt = data.find_all("dt")
        if len(_bs_dt) < 2:
            raise ValueError(f"at least 2 <dt> tags are expected ({len(_bs_dt)} found)")

        _bs_table = data.find_all("table")
        _bs_table_clusters = _bs_table[::2]  # only capture the even indexes
        _bs_table_routes = _bs_table[1::2]  # only capture the even indexes

        yield ("httpd_version", _bs_dt[0].text)
        yield ("httpd_built_date", _bs_dt[1].text)
        yield ("openssl_version", _bs_dt[0].text)

        _clusters = list()
        for table in _bs_table_clusters:
            header_elements = table.findPreviousSiblings("h3", limit=1)

            if len(header_elements) != 1:
                raise ValueError(
                    f"single <h3> tag is expected ({len(header_elements)} found)"
                )

            header = header_elements[0]

            for row in get_table_rows(table):
                # Note about sticky_session:
                # there is a workaround for a bug in the html formatting in httpd 2.4.20 in
                # which the StickySession cell closing tag comes after DisableFailover
                # HTML = <td>JSESSIONID<td>Off</td></td>
                sticky_session = str(
                    row["StickySession"].find(string=True, recursive=False)
                ).strip()

                _clusters.append(
                    {
                        "name": header.a.text if header.a else header.text,
                        "max_members": row["MaxMembers"].text,
                        "sticky_session": sticky_session,
                        "disable_failover": row["DisableFailover"].text,
                        "timeout": row["Timeout"].text,
                        "failover_attempts": row["FailoverAttempts"].text,
                        "method": row["Method"].text,
                        "path": row["Path"].text,
                        "active": row["Active"].text,
                    }
                )

        yield ("clusters", _clusters)

        _routes = list()
        for table in _bs_table_routes:
            for i, row in enumerate(get_table_rows(table)):
                worker_url = cast(Tag, row["Worker URL"].find("a"))
                row_data: dict[str, Any] = {
                    "name": row["Route"].text,
                    "worker_url": worker_url["href"] if worker_url else "",
                    "worker": worker_url.text if worker_url else "",
                    "priority": i,
                    "route_redir": row["RouteRedir"].text,
                    "factor": row["Factor"].text,
                    "lbset": row["Set"].text,
                    "elected": row["Elected"].text,
                    "busy": row["Busy"].text,
                    "load": row["Load"].text,
                    "to": row["To"].text,
                    "from": row["From"].text,
                    "active_status_codes": row["Status"].text,
                    "hcheck": None,
                }

                # add hcheck data if available
                if "HC Method" in row and row["HC Method"].text != "NONE":
                    row_data["hcheck"] = {
                        "method": row["HC Method"].text,
                        "interval_ms": row["HC Interval"].text,
                        "passes": row["Passes"].text,
                        "fails": row["Fails"].text,
                        "uri": row["HC uri"].text,
                        "expr": row["HC Expr"].text,
                    }

                _routes.append(row_data)

        yield ("routes", _routes)
