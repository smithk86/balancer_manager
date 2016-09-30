import threading
import logging
from collections import OrderedDict

from .client import Client


logger = logging.getLogger(__name__)


_allowed_statuses = ['status_disabled', 'status_hot_standby', 'status_draining_mode', 'status_ignore_errors']
_allowed_statuses_apache_22 = ['status_disabled']


class ValidationClient(Client):

    def __init__(self, url, **kwargs):

        self.holistic_compliance_status = False
        self.profile = kwargs.pop('profile', None)

        super(ValidationClient, self).__init__(url, **kwargs)

    def _get_clusters_from_apache(self):

        global _allowed_statuses
        global _allowed_statuses_apache_22

        allowed_statuses = _allowed_statuses_apache_22 if self.apache_version_is('2.2') else _allowed_statuses

        self.holistic_compliance_status = True

        clusters = super(ValidationClient, self)._get_clusters_from_apache()

        if self.profile is None:
            return clusters

        for cluster in clusters:

            cluster_profile = self.profile.get(cluster.name, {})

            for route in cluster.get_routes():

                route.compliance_status = True
                route_profile = cluster_profile.get(route.name)
                status_validation = {}

                for status in allowed_statuses:

                    status_validation[status] = {
                        'value': getattr(route, status),
                        'profile': None,
                        'compliance': None
                    }

                    if type(route_profile) is list:
                        status_validation[status]['profile'] = status in route_profile

                        if status_validation[status]['value'] is status_validation[status]['profile']:
                            status_validation[status]['compliance'] = True
                        else:
                            status_validation[status]['compliance'] = False
                            route.compliance_status = False
                            self.holistic_compliance_status = False

                setattr(route, 'status_validation', status_validation)

        return clusters

    def get_holistic_compliance_status(self):

        self.get_clusters()
        return self.holistic_compliance_status

    def enforce(self):

        global _allowed_statuses
        global _allowed_statuses_apache_22

        allowed_statuses = _allowed_statuses_apache_22 if self.apache_version_is('2.2') else _allowed_statuses

        for route in self.get_routes():
            if route.compliance_status is False:

                logger.info('enforcing profile for {cluster}->{route}'.format(cluster=route.cluster.name, route=route.name))

                # build status dictionary to enforce
                route_statuses = {}
                for status in allowed_statuses:
                    route_statuses[status] = route.status_validation[status]['profile']

                route.change_status(**route_statuses)

    def set_profile(self, profile):

        # set new profile
        self.profile = profile
        # expire cache to force refresh
        self.expire_route_cache()

    def get_profile(self):

        global _allowed_statuses
        global _allowed_statuses_apache_22

        allowed_statuses = _allowed_statuses_apache_22 if self.apache_version_is('2.2') else _allowed_statuses

        # init empty list for the profile
        profile = OrderedDict()

        for cluster in super(ValidationClient, self)._get_clusters_from_apache():

            cluster_profile = OrderedDict()

            for route in cluster.get_routes():

                enabled_statuses = []

                for status, value in route.get_statuses().items():
                    if status in allowed_statuses:
                        if type(value) is not bool:
                            raise TypeError('status value must be boolean')
                        if value is True:
                            enabled_statuses.append(status)

                cluster_profile[route.name] = enabled_statuses

            profile[cluster.name] = cluster_profile

        return profile
