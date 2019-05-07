import logging

from .client import Client
from .cluster import Cluster
from .errors import BalancerManagerError
from .route import Route


logger = logging.getLogger(__name__)


class ValidatedCluster(Cluster):
    def new_route(self):
        route = ValidatedRoute(self)
        self.routes.append(route)
        return route

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
                if status_validation['profile'] is None:
                    return False
        return True

    def _parse(self):
        if self.status_validation is None:
            self.status_validation = dict()
            for status_name in self.get_statuses().keys():
                if status_name not in self.get_immutable_statuses():
                    self.status_validation[status_name] = {
                        'value': None,
                        'profile': None,
                        'compliance': None
                    }


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

                for status_name, status_profile in route.status_validation.items():
                    route.status_validation[status_name] = {
                        'value': getattr(route, status_name),
                        'profile': None,
                        'compliance': None
                    }
                    if type(route_profile) is list:
                        route.status_validation[status_name]['profile'] = status_name in route_profile
                        if route.status_validation[status_name]['value'] is route.status_validation[status_name]['profile']:
                            route.status_validation[status_name]['compliance'] = True
                        else:
                            route.status_validation[status_name]['compliance'] = False
                            route.compliance_status = False
                            self.holistic_compliance_status = False

            if not cluster.all_routes_are_profiled():
                self.all_routes_are_profiled = False

    def get_holistic_compliance_status(self):
        if self.holistic_compliance_status is None:
            self.update()
        return self.holistic_compliance_status

    async def enforce(self):
        exceptions = []
        for route in await self.get_routes():
            if route.compliance_status is False:
                logger.info(f'enforcing profile for {route.cluster.name}->{route.name}')
                # build status dictionary to enforce
                route_statuses = {}
                for status_name in route.get_statuses().keys():
                    if status_name not in route.get_immutable_statuses():
                        route_statuses[status_name] = route.status_validation[status_name]['profile']

                try:
                    await route.change_status(**route_statuses)
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
