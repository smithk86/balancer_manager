import logging
from datetime import datetime
from typing import Any, Generator, Type, TypedDict

import dateparser
from pydantic import HttpUrl

from .cluster import Cluster
from .parse import ParsedBalancerManager
from .route import Route
from ...models import ParsableModel
from ...utils import utcnow, RegexPatterns


logger = logging.getLogger(__name__)


class ParseOptions(TypedDict):
    cluster_class: Type[Cluster]
    route_class: Type[Route]


class BalancerManager(ParsableModel, validate_assignment=True):
    date: datetime
    url: HttpUrl
    httpd_version: str
    httpd_built_date: datetime
    openssl_version: str
    clusters: dict[str, Cluster]
    _parse_options: ParseOptions = {
        "cluster_class": Cluster,
        "route_class": Route,
    }

    def cluster(self, name: str):
        return self.clusters[name]

    @classmethod
    def parse_payload(cls, payload: str, **kwargs) -> "BalancerManager":
        parsed_model = ParsedBalancerManager.parse_payload(payload, **kwargs)
        model_props = dict(cls._get_parsed_pairs(parsed_model, **kwargs))
        return cls.parse_obj(model_props)

    @classmethod
    def _get_parsed_pairs(cls, data: ParsedBalancerManager, **kwargs) -> Generator[tuple[str, Any], None, None]:
        _cluster_class = cls._parse_options["cluster_class"]
        _route_class = cls._parse_options["route_class"]

        yield ("date", utcnow())

        m = RegexPatterns.HTTPD_VERSION.match(data.httpd_version)
        yield ("httpd_version", m.group(1))

        m = RegexPatterns.HTTPD_BUILT_DATE.match(data.httpd_built_date)
        yield (
            "httpd_built_date",
            dateparser.parse(m.group(1), settings={"RETURN_AS_TIMEZONE_AWARE": True}),
        )

        m = RegexPatterns.OPENSSL_VERSION.search(data.openssl_version)
        yield ("openssl_version", m.group(1))

        routes: list[Route] = list()
        for route in data.routes:
            route_data = _route_class._get_parsed_pairs(route)
            routes.append(_route_class.parse_obj(route_data))

        clusters = dict()
        for cluster in data.clusters:
            cluster_data = _cluster_class._get_parsed_pairs(cluster, routes=routes)
            _cluster = _cluster_class.parse_obj(cluster_data)
            if _cluster.name in clusters:
                raise ValueError(f"cluster name already exists: {_cluster.name}")
            clusters[_cluster.name] = _cluster

        yield ("clusters", clusters)

        for key, val in kwargs.items():
            yield (key, val)


BalancerManager.update_forward_refs()
