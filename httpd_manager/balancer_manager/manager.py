from __future__ import annotations

import asyncio
import collections.abc
import logging
from copy import copy
from datetime import datetime
from typing import Callable, Iterator, Optional, TYPE_CHECKING
from uuid import UUID

import dateparser
from packaging import version

from ..errors import HttpdManagerError
from ..helpers import Bytes, HttpdVersions, RegexPatterns, TypeVersion
from .cluster import Cluster
from .parse import parse
from .route import ImmutableStatus, Route, Status

if TYPE_CHECKING:
    from ..client import Client


logger = logging.getLogger(__name__)
__all__ = ["BalancerManager"]


class BalancerManager(collections.abc.Mapping):
    cluster_class: Callable = Cluster
    route_class: Callable = Route

    def __init__(self, client):
        if client.balancer_manager_path is None:
            raise HttpdManagerError(
                f"cannot init ServerStatus\nendpoint: {client.endpoint}"
            )

        self.client: Client = client
        self.httpd_version: Optional[TypeVersion] = None
        self.httpd_built_date: Optional[datetime] = None
        self.openssl_version: Optional[TypeVersion] = None
        self.clusters: Dict[Cluster] = dict()
        self.cached_response: Optional[httpx.Response] = None
        self.date: Optional[datetime] = None
        self._communication_lock = asyncio.Lock()

    async def __aenter__(self) -> BalancerManager:
        await self.client.__aenter__()
        return self

    async def __aexit__(self, *args, **kwargs) -> None:
        await self.client.__aexit__(*args, **kwargs)

    def __getitem__(self, key: str) -> Cluster:
        if self.clusters is None:
            raise HttpdManagerError(
                f"client contains no data\nendpoint: {self.client.endpoint}"
            )

        if key in self.clusters:
            return self.clusters[key]
        else:
            raise HttpdManagerError(
                f"cluster does not exist\nendpoint: {self.client.endpoint}\ncluster: {key}"
            )

    def __iter__(self) -> Iterator[str]:
        return iter(self.clusters.keys())

    def __len__(self) -> int:
        return len(self.clusters)

    @property
    def health(self) -> Optional[bool]:
        """
        return False if len(self) == 0 or
            if any cluster.health is False
        """

        if len(self) == 0:
            return None

        for cluster in self.values():
            if cluster.health is False:
                return False
        return True

    async def update(self, data=None) -> BalancerManager:
        async with self._communication_lock:
            if data:
                self.cached_response = await self.client.post(
                    self.client.balancer_manager_path, data
                )
            else:
                self.cached_response = await self.client.get(
                    self.client.balancer_manager_path
                )
            await self.parse()

        return self

    async def parse(self) -> None:
        parsed_data = await self.client.run_in_executor(
            parse, self.cached_response, self.client.use_lxml
        )
        self.date = parsed_data.date

        m = RegexPatterns.HTTPD_VERSION.match(parsed_data.version)
        self.httpd_version = version.parse(m.group(1))

        HttpdVersions.validate(self.httpd_version)

        m = RegexPatterns.OPENSSL_VERSION.search(parsed_data.version)
        self.openssl_version = version.parse(m.group(1))

        m = RegexPatterns.HTTPD_BUILT_DATE.match(parsed_data.built_date)
        self.httpd_built_date = dateparser.parse(m.group(1))

        for parsed_cluster in parsed_data.clusters:
            m = RegexPatterns.BALANCER_URI.match(parsed_cluster["name"])
            cluster_name = m.group(1)

            if cluster_name in self.clusters:
                cluster_obj = self.clusters[cluster_name]
            else:
                cluster_obj = self.clusters[cluster_name] = self.cluster_class(
                    self, cluster_name
                )

            cluster_obj._date = parsed_data.date

            m = RegexPatterns.ROUTE_USED.match(parsed_cluster["max_members"])
            max_members = int(m.group(1))
            max_members_used = int(m.group(2))

            cluster_obj.max_members = max_members
            cluster_obj.max_members_used = max_members_used
            cluster_obj.sticky_session = (
                None
                if parsed_cluster["sticky_session"] == "(None)"
                else parsed_cluster["sticky_session"]
            )
            cluster_obj.disable_failover = "On" in parsed_cluster["disable_failover"]
            cluster_obj.timeout = int(parsed_cluster["timeout"])
            cluster_obj.failover_attempts = int(parsed_cluster["failover_attempts"])
            cluster_obj.method = parsed_cluster["method"]
            cluster_obj.path = parsed_cluster["path"]
            cluster_obj.active = "Yes" in parsed_cluster["active"]

        for parsed_route in parsed_data.routes:
            m = RegexPatterns.CLUSTER_NAME.search(parsed_route["worker_url"])
            cluster_name = m.group(1)
            route_name = parsed_route["name"]

            cluster_obj = self.clusters[cluster_name]
            if route_name in cluster_obj.routes:
                route_obj = cluster_obj.routes[route_name]
            else:
                route_obj = cluster_obj.routes[route_name] = self.route_class(
                    cluster_obj, route_name
                )

            route_obj._date = parsed_data.date

            m = RegexPatterns.SESSION_NONCE_UUID.search(parsed_route["worker_url"])
            route_obj.session_nonce_uuid = UUID(m.group(1))

            m = RegexPatterns.BANDWIDTH_USAGE.search(parsed_route["to"])
            route_obj._to = Bytes(float(m.group(1)), m.group(2))

            m = RegexPatterns.BANDWIDTH_USAGE.search(parsed_route["from"])
            route_obj._from_ = Bytes(float(m.group(1)), m.group(2))

            route_obj.worker = parsed_route["worker"]
            route_obj.priority = parsed_route["priority"]
            route_obj.route_redir = parsed_route["route_redir"]
            route_obj.factor = float(parsed_route["factor"])
            route_obj.lbset = int(parsed_route["lbset"])
            route_obj.elected = int(parsed_route["elected"])
            route_obj.busy = int(parsed_route["busy"])
            route_obj.load = int(parsed_route["load"])
            route_obj.status = dict(
                [
                    (
                        "ok",
                        ImmutableStatus(
                            name="ok", value="Ok" in parsed_route["active_status_codes"]
                        ),
                    ),
                    (
                        "error",
                        ImmutableStatus(
                            name="error",
                            value="Err" in parsed_route["active_status_codes"],
                        ),
                    ),
                    (
                        "ignore_errors",
                        Status(
                            name="ignore_errors",
                            value="Ign" in parsed_route["active_status_codes"],
                            http_form_code="I",
                        ),
                    ),
                    (
                        "draining_mode",
                        Status(
                            name="draining_mode",
                            value="Drn" in parsed_route["active_status_codes"],
                            http_form_code="N",
                        ),
                    ),
                    (
                        "disabled",
                        Status(
                            name="disabled",
                            value="Dis" in parsed_route["active_status_codes"],
                            http_form_code="D",
                        ),
                    ),
                    (
                        "hot_standby",
                        Status(
                            name="hot_standby",
                            value="Stby" in parsed_route["active_status_codes"],
                            http_form_code="H",
                        ),
                    ),
                    (
                        "hot_spare",
                        Status(
                            name="hot_spare",
                            value="Spar" in parsed_route["active_status_codes"],
                            http_form_code="R",
                        )
                        if self.httpd_version >= version.parse("2.4.34")
                        else None,
                    ),
                    (
                        "stopped",
                        Status(
                            name="stopped",
                            value="Stop" in parsed_route["active_status_codes"],
                            http_form_code="S",
                        )
                        if self.httpd_version >= version.parse("2.4.23")
                        else None,
                    ),
                ]
            )

        # remove orphaned cluster/routes
        for cluster_name, cluster_obj in copy(self.clusters).items():
            if cluster_obj._date < self.date:
                logger.warning(f"removing orphaned cluster: {cluster_obj.name}")
                del self.clusters[cluster_name]
            else:
                for route_name, route_obj in copy(cluster_obj.routes).items():
                    if route_obj._date < self.date:
                        logger.warning(
                            f"removing orphaned route: {cluster_obj.name}->{route_obj.name}"
                        )
                        del cluster_obj.routes[route_name]
