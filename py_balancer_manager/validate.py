import asyncio
import logging
from collections import namedtuple

from .client import Client
from .cluster import Cluster
from .errors import BalancerManagerError
from .helpers import handle_task_exceptions
from .route import Route
from .status import ValidatedStatus


logger = logging.getLogger(__name__)


class ValidatedCluster(Cluster):
    def new_route(self):
        route = ValidatedRoute(self)
        self.routes.append(route)
        return route

    @property
    def profile(self):
        if self.client.profile:
            return self.client.profile.get(self.name)
        else:
            return None

    @property
    def compliance_status(self):
        for route in self.get_routes():
            if route.compliance_status is False:
                return False
        return True

    @property
    def all_routes_are_profiled(self):
        for route in self.get_routes():
            if route.profile is None:
                return False
        return True


class ValidatedRoute(Route):
    def __init__(self, cluster):
        super(ValidatedRoute, self).__init__(cluster)
        self.compliance_status = None

    def asdict(self):
        d = super(ValidatedRoute, self).asdict()
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


class ValidationClient(Client):
    def __init__(self, url, **kwargs):
        self.profile = kwargs.pop('profile', None)
        super(ValidationClient, self).__init__(url, **kwargs)

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
        d = super(ValidationClient, self).asdict()
        d.update({
            'all_routes_are_profiled': self.all_routes_are_profiled,
            'compliance_status': self.compliance_status,
            'profile': self.profile
        })
        return d

    def new_cluster(self):
        cluster = ValidatedCluster(self)
        self.clusters.append(cluster)
        return cluster

    def _parse(self, bsoup):
        super(ValidationClient, self)._parse(bsoup)
        if self.profile is None:
            return

        for cluster in self.clusters:
            for route in cluster.get_routes():
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

    async def enforce(self):
        tasks = []
        for route in await self.get_routes():
            if route.compliance_status is False:
                logger.info(f'enforcing profile for {route.cluster.name}->{route.name}')
                # build status dictionary to enforce
                statuses = {}
                for status_name in route.mutable_statuses():
                    statuses[status_name] = route.status(status_name).profile
                tasks.append(
                    self.loop.create_task(
                        route.change_status(**statuses)
                    )
                )
        if len(tasks) > 0:
            await asyncio.wait(tasks)
            handle_task_exceptions(tasks)

    async def set_profile(self, profile):
        # set new profile
        self.profile = profile
        # refresh routes to include profile information
        await self.update()

    async def get_profile(self):
        # init empty list for the profile
        profile = dict()
        for cluster in await self.get_clusters():
            cluster_profile = dict()
            for route in cluster.get_routes():
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
