import logging
from collections import namedtuple

from ._parse import parse
from .balancer_manager import BalancerManager
from .client import Client
from .cluster import Cluster
from .errors import BalancerManagerError, MultipleExceptions
from .route import Route
from .status import ValidatedStatus


logger = logging.getLogger(__name__)


class ValidatedRoute(Route):
    def __init__(self, cluster, name):
        super().__init__(cluster, name)
        self.compliance_status = None

    def __repr__(self):
        return f'<py_balancer_manager.validate.ValidatedRoute object: {self.name}>'

    @property
    def profile(self):
        cluster_profile = self.cluster.profile
        if cluster_profile:
            return cluster_profile.get(self.name)
        else:
            return None

    def _parse(self):
        for status_name in self.mutable_statuses():
            status = self.status(status_name)
            setattr(self._status, status_name, ValidatedStatus(
                value=status.value,
                immutable=status.immutable,
                http_form_code=status.http_form_code,
                profile=None,
                compliance=None
            ))

            # this route is not part of the profile
            if self.profile is None:
                self.compliance_status = None
            else:
                self.compliance_status = True

            for status_name in self.mutable_statuses():
                status = self.status(status_name)
                status.profile = None
                status.compliance = None

                if self.profile is None:
                    continue

                status.profile = status_name in self.profile
                if status.value is status.profile:
                    status.compliance = True
                else:
                    status.compliance = False
                    self.compliance_status = False


class ValidatedCluster(Cluster):
    def __repr__(self):
        return f'<py_balancer_manager.validate.ValidatedCluster object: {self.name}>'

    def new_route(self, name):
        route = ValidatedRoute(self, name)
        self.routes.append(route)
        return route

    @property
    def profile(self):
        if self.balancer_manager.profile:
            return self.balancer_manager.profile.get(self.name)
        else:
            return None

    @property
    def compliance_status(self):
        for route in self.routes:
            if route.compliance_status is False:
                return False
        return True

    @property
    def all_routes_are_profiled(self):
        for route in self.routes:
            if route.profile is None:
                return False
        return True


class ValidatedBalancerManager(BalancerManager):
    def __init__(self, client, profile=None, use_lxml=False):
        super().__init__(client, use_lxml=use_lxml)
        self.profile = profile

    def __repr__(self):
        return f'<py_balancer_manager.validate.ValidatedBalancerManager object: {self.client.url} [clusters={len(self.clusters)}]>'

    @property
    def compliance_status(self):
        for cluster in self.clusters:
            if cluster.compliance_status is False:
                return False
        return True

    @property
    def all_routes_are_profiled(self):
        for cluster in self.clusters:
            if cluster.all_routes_are_profiled is False:
                return False
        return True

    def new_client(self, **kwargs):
        return ValidationClient(**kwargs)

    def new_cluster(self, name):
        cluster = ValidatedCluster(self, name)
        self.clusters.append(cluster)
        return cluster

    async def enforce(self):
        exceptions = []
        for cluster in self.clusters:
            for route in cluster.routes:
                if route.compliance_status is False:
                    logger.info(f'enforcing profile for {route.cluster.name}->{route.name}')
                    # build status dictionary to enforce
                    statuses = {}
                    for status_name in route.mutable_statuses():
                        statuses[status_name] = route.status(status_name).profile
                    try:
                        await route.edit(**statuses)
                    except Exception as e:
                        logger.exception(e)
                        exceptions.append(e)
        if len(exceptions) > 0:
            raise MultipleExceptions(exceptions)

    async def set_profile(self, profile):
        # set new profile
        self.profile = profile
        # refresh routes to include profile information
        await self.update()

    async def get_profile(self):
        await self.update()
        # init empty list for the profile
        profile = dict()
        for cluster in self.clusters:
            cluster_profile = dict()
            for route in cluster.routes:
                enabled_statuses = []
                for status_name in route.mutable_statuses():
                    value = route.status(status_name).value
                    if type(value) is not bool:
                        raise TypeError('status value must be boolean')
                    if value is True:
                        enabled_statuses.append(status_name)
                cluster_profile[route.name] = enabled_statuses
            profile[cluster.name] = cluster_profile
        return profile

    async def update(self, response_payload=None):
        await super().update(response_payload)
        for cluster in self.clusters:
            for route in cluster.routes:
                route._parse()
        return self
