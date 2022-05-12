from __future__ import annotations

import logging

from datetime import datetime
from typing import Any, Dict, Generator, List, Tuple, Type

import dateparser
from pydantic import validator

from .cluster import ImmutableCluster
from .parse import ParsedBalancerManager
from .route import ImmutableStatus, ImmutableRoute, Status
from ...utils import BaseModel, RegexPatterns


logger = logging.getLogger(__name__)


class ImmutableBalancerManager(BaseModel, allow_mutation=False):
    date: datetime
    httpd_version: str
    httpd_built_date: datetime
    openssl_version: str
    clusters: Dict[str, ImmutableCluster]
    _cluster_class: Type = ImmutableCluster
    _route_class: Type = ImmutableRoute

    def cluster(self, name: str):
        return self.clusters[name]

    @property
    def health(self) -> bool | None:
        """
        return False if len(self) == 0 or
            if any cluster.health is False
        """

        if len(self.clusters) == 0:
            return None

        for cluster in self.clusters.values():
            if cluster.health is False:
                return False
        return True

    @classmethod
    def parse_payload(cls, payload: str, **extra) -> ImmutableBalancerManager:
        parsed_model = ParsedBalancerManager.parse_payload(payload)
        model_props = dict(cls._get_parsed_pairs(parsed_model))
        model_props.update(extra)
        return cls.parse_obj(model_props)

    @classmethod
    def _get_parsed_pairs(
        cls,
        model: ParsedBalancerManager,
    ) -> Generator[Tuple[str, Any], None, None]:
        yield ("date", model.date)

        m = RegexPatterns.HTTPD_VERSION.match(model.httpd_version)
        yield ("httpd_version", m.group(1))

        m = RegexPatterns.HTTPD_BUILT_DATE.match(model.httpd_built_date)
        yield (
            "httpd_built_date",
            dateparser.parse(m.group(1), settings={"RETURN_AS_TIMEZONE_AWARE": True}),
        )

        m = RegexPatterns.OPENSSL_VERSION.search(model.openssl_version)
        yield ("openssl_version", m.group(1))

        routes: List[ImmutableRoute] = list()
        for route in model.routes:
            parsed = cls._route_class._get_parsed_pairs(route)
            routes.append(cls._route_class.parse_obj(parsed))

        clusters = dict()
        for cluster in model.clusters:
            parsed = cls._cluster_class._get_parsed_pairs(cluster, routes)
            _cluster = cls._cluster_class.parse_obj(parsed)
            assert (
                _cluster.name not in clusters
            ), f"cluster name already exists: {_cluster.name}"
            clusters[_cluster.name] = _cluster

        yield ("clusters", clusters)


ImmutableBalancerManager.update_forward_refs()
