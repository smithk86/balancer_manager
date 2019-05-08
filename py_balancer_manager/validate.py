import dataclasses
import logging
from collections import namedtuple

from .client import Client
from .cluster import Cluster
from .errors import BalancerManagerError
from .route import Route
from .status import ValidatedStatus


logger = logging.getLogger(__name__)


class ValidatedCluster(Cluster):
    def new_route(self):
        route = ValidatedRoute(self)
        self.routes.append(route)
        return route

    @property
    def all_routes_are_profiled(self):
        for route in self.get_routes():
            if not route.has_profile():
                return False
        return True


class ValidatedRoute(Route):
    def __init__(self, cluster):
        super(ValidatedRoute, self).__init__(cluster)
        self.compliance_status = None
        self.status_validation = None

    def to_dict(self):
        d = super(ValidatedRoute, self).to_dict()
        d.update({
            'compliance_status': self.compliance_status,
            'status_validation': self.status_validation
        })
        return d

    def has_profile(self):
        if self.status_validation is not None:
            for status_validation in self.status_validation.values():
                if status_validation.profile is None:
                    return False
        return True

    def _parse(self):
        if self.status_validation is None:
            self.status_validation = dict()
            for status_name in self.mutable_statuses():
                status = getattr(self.status, status_name)
                setattr(self.status, status_name, ValidatedStatus(
                    value=status.value,
                    immutable=status.immutable,
                    http_form_code=status.http_form_code,
                    profile=None,
                    compliance=None
                ))


class ValidationClient(Client):
    def __init__(self, url, **kwargs):
        self.all_routes_are_profiled = None
        self.holistic_compliance_status = None
        self.profile = kwargs.pop('profile', None)
        super(ValidationClient, self).__init__(url, **kwargs)

    def to_dict(self):
        d = super(ValidationClient, self).to_dict()
        d.update({
            'all_routes_are_profiled': self.all_routes_are_profiled,
            'holistic_compliance_status': self.holistic_compliance_status,
            'profile': self.profile
        })
        return d

    def new_cluster(self):
        cluster = ValidatedCluster(self)
        self.clusters.append(cluster)
        return cluster

    def _parse(self, bsoup):
        self.all_routes_are_profiled = True
        self.holistic_compliance_status = True
        super(ValidationClient, self)._parse(bsoup)
        if self.profile is None:
            return

        for cluster in self.clusters:
            cluster_profile = self.profile.get(cluster.name, {})
            for route in cluster.get_routes():
                route._parse()
                route.compliance_status = True
                route_profile = cluster_profile.get(route.name)
                for status_name in route.mutable_statuses():
                    status = getattr(route.status, status_name)
                    status.profile = None
                    status.compliance = True

                    if type(route_profile) is list:
                        status.profile = status_name in route_profile
                        if status.value is not status.profile:
                            status.compliance = False
                            route.compliance_status = False
                            self.holistic_compliance_status = False

            if not cluster.all_routes_are_profiled:
                self.all_routes_are_profiled = False

    async def get_holistic_compliance_status(self):
        if self.holistic_compliance_status is None:
            await self.update()
        return self.holistic_compliance_status

    async def enforce(self):
        exceptions = []
        for route in await self.get_routes():
            if route.compliance_status is False:
                logger.info(f'enforcing profile for {route.cluster.name}->{route.name}')
                # build status dictionary to enforce
                statuses = {}
                for status_name in route.mutable_statuses():
                    statuses[status_name] = getattr(route.status, status_name).profile
                try:
                    await route.change_status(**statuses)
                except Exception as e:
                    exceptions.append(e)
        if len(exceptions) > 0:
            raise BalancerManagerError({'exceptions': exceptions})

    def set_profile(self, profile):
        # set new profile
        self.profile = profile
        # refresh routes to include profile information
        self.update()

    async def get_profile(self):
        # init empty list for the profile
        profile = dict()
        for cluster in await self.get_clusters():
            cluster_profile = dict()
            for route in cluster.get_routes():
                enabled_statuses = []
                for status_name, value in route.get_statuses().items():
                    if status_name not in route.get_immutable_statuses():
                        if type(value) is not bool:
                            raise TypeError('status value must be boolean')
                        if value is True:
                            enabled_statuses.append(status_name)
                cluster_profile[route.name] = enabled_statuses
            profile[cluster.name] = cluster_profile
        return profile
