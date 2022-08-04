import logging
from copy import copy

from datetime import datetime
from typing import Any, Generator

import dateparser

from .cluster import ImmutableCluster
from .parse import ParsedBalancerManager
from .route import ImmutableRoute
from ...models import ParsableModel
from ...utils import utcnow, RegexPatterns


logger = logging.getLogger(__name__)


class ImmutableBalancerManager(ParsableModel, allow_mutation=False):
    date: datetime
    httpd_version: str
    httpd_built_date: datetime
    openssl_version: str
    clusters: dict[str, ImmutableCluster]
    _parse_options: dict[str, Any] = {
        "cluster_model": ImmutableCluster,
        "route_model": ImmutableRoute,
    }

    def cluster(self, name: str):
        return self.clusters[name]

    @classmethod
    def parse_payload(cls, payload: str, **kwargs) -> "ImmutableBalancerManager":
        parsed_model = ParsedBalancerManager.parse_payload(payload, **kwargs)
        model_props = dict(cls._get_parsed_pairs(parsed_model, **kwargs))
        return cls.parse_obj(model_props)

    @classmethod
    def _get_parsed_pairs(
        cls, data: ParsedBalancerManager, **kwargs
    ) -> Generator[tuple[str, Any], None, None]:
        _cluster_model = cls._parse_options.get("cluster_model", ImmutableCluster)
        _route_model = cls._parse_options.get("route_model", ImmutableRoute)

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

        routes: list[ImmutableRoute] = list()
        for route in data.routes:
            route_data = _route_model._get_parsed_pairs(route)
            routes.append(_route_model.parse_obj(route_data))

        clusters = dict()
        for cluster in data.clusters:
            cluster_data = _cluster_model._get_parsed_pairs(cluster, routes=routes)
            _cluster = _cluster_model.parse_obj(cluster_data)
            assert (
                _cluster.name not in clusters
            ), f"cluster name already exists: {_cluster.name}"
            clusters[_cluster.name] = _cluster

        yield ("clusters", clusters)

        for key, val in kwargs.items():
            yield (key, val)


ImmutableBalancerManager.update_forward_refs()
