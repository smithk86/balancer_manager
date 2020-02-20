import logging
from collections import namedtuple

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

    def asdict(self):
        d = super().asdict()
        d.update({
            'compliance_status': self.compliance_status
        })
        return d

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
    def __init__(self, client):
        super().__init__(client)
        self.profile = None

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

    def asdict(self):
        d = super().asdict()
        d.update({
            'compliance_status': self.compliance_status,
            'all_routes_are_profiled': self.all_routes_are_profiled,
            'profile': self.profile
        })
        return d

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

    def get_profile(self):
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


class ValidationClient(Client):
    def __repr__(self):
        return f'<py_balancer_manager.validate.ValidationClient object: {self.client.url}>'

    async def balancer_manager(self, profile):
        balancer_manager = ValidatedBalancerManager(self)
        balancer_manager.profile = profile
        response_payload = await self._http_get_payload()
        self._parse(response_payload, balancer_manager)
        return balancer_manager

    def _parse(self, response_payload, balancer_manager):
        super()._parse(response_payload, balancer_manager)
        for cluster in balancer_manager.clusters:
            for route in cluster.routes:
                route._parse()

                # this route is not part of the profile
                if route.profile is None:
                    route.compliance_status = None
                else:
                    route.compliance_status = True

                for status_name in route.mutable_statuses():
                    status = route.status(status_name)
                    status.profile = None
                    status.compliance = None

                    if route.profile is None:
                        continue

                    status.profile = status_name in route.profile
                    if status.value is status.profile:
                        status.compliance = True
                    else:
                        status.compliance = False
                        route.compliance_status = False
