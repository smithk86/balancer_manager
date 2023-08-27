from __future__ import annotations

import logging
from collections.abc import Generator
from datetime import datetime
from typing import Any, Generic, TypeVar

import dateparser
from bs4 import BeautifulSoup
from pydantic import BaseModel, ConfigDict, HttpUrl

from ...utils import RegexPatterns, get_table_rows, lxml_is_loaded, utcnow
from .cluster import Cluster, ClusterType
from .route import Route

logger = logging.getLogger(__name__)


class BalancerManager(BaseModel, Generic[ClusterType]):
    model_config = ConfigDict(validate_assignment=True)

    date: datetime
    url: HttpUrl
    httpd_version: str
    httpd_built_date: datetime
    openssl_version: str
    clusters: dict[str, ClusterType]

    def __init__(self, **data: Any) -> None:
        super().__init__(**data)

        # update Cluster._manager
        for cluster in self.clusters.values():
            cluster._manager = self

    def cluster(self, name: str) -> ClusterType:
        return self.clusters[name]

    @staticmethod
    def parse_values_from_payload(
        payload: str | bytes, context: dict[str, Any] | None
    ) -> Generator[tuple[str, Any], None, None]:
        context = context or {}

        bs = BeautifulSoup(payload, features="lxml") if lxml_is_loaded else BeautifulSoup(payload)

        yield ("date", utcnow())

        # remove form from page -- this contains extra tables which do not contain clusters or routes
        for form in bs.find_all("form"):
            form.extract()

        # initial payload validation
        _bs_h1 = bs.find_all("h1")
        if len(_bs_h1) != 1 or "Load Balancer Manager" not in _bs_h1[0].text:
            raise ValueError("initial html validation failed; is this really an Httpd Balancer Manager page?")

        _bs_dt = bs.find_all("dt")
        if len(_bs_dt) < 2:
            raise ValueError(f"at least 2 <dt> tags are expected ({len(_bs_dt)} found)")

        _bs_table = bs.find_all("table")

        m = RegexPatterns.HTTPD_VERSION.match(_bs_dt[0].text)
        yield ("httpd_version", m.group(1))

        m = RegexPatterns.HTTPD_BUILT_DATE.match(_bs_dt[1].text)
        yield (
            "httpd_built_date",
            dateparser.parse(m.group(1), settings={"RETURN_AS_TIMEZONE_AWARE": True}),
        )

        m = RegexPatterns.OPENSSL_VERSION.search(_bs_dt[0].text)
        yield ("openssl_version", m.group(1))

        routes: list[dict[str, Any]] = []
        for table in _bs_table[1::2]:  # routes are the even tables
            for i, row in enumerate(get_table_rows(table)):
                route_name = row["Route"].text
                route = {"name": route_name, "priority": i}
                route.update(dict(Route.parse_values_from_tags(row)))
                routes.append(route)

        clusters: dict[str, dict[str, Any]] = {}
        for table in _bs_table[::2]:  # clusters are the odd table
            header_elements = table.findPreviousSiblings("h3", limit=1)

            if len(header_elements) != 1:
                raise ValueError(f"single <h3> tag is expected ({len(header_elements)} found)")

            header = header_elements[0]

            for row in get_table_rows(table):
                # Note about sticky_session:
                # there is a workaround for a bug in the html formatting in httpd 2.4.20 in
                # which the StickySession cell closing tag comes after DisableFailover
                # HTML = <td>JSESSIONID<td>Off</td></td>
                # sticky_session = str(row["StickySession"].find(string=True, recursive=False)).strip()

                cluster_uri = header.a.text if header.a else header.text
                m = RegexPatterns.BALANCER_URI.match(cluster_uri)
                cluster_name = m.group(1)
                cluster = {
                    "name": cluster_name,
                    "routes": {x["name"]: x for x in routes if x["cluster"] == cluster_name},
                }
                cluster.update(dict(Cluster.parse_values_from_tags(row)))
                clusters[cluster_name] = cluster

        yield ("clusters", clusters)

    @classmethod
    def model_validate_payload(
        cls: type[BalancerManagerType],
        url: str | HttpUrl,
        payload: str | bytes,
        context: dict[str, Any] | None = None,
        **extra: Any,
    ) -> BalancerManagerType:
        values = dict(cls.parse_values_from_payload(payload, context=context))
        values.update({"url": url})
        values.update(extra)
        return cls.model_validate(values, context=context)


BalancerManagerType = TypeVar("BalancerManagerType", bound=BalancerManager[Any])
