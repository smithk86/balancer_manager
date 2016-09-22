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

        for cluster_name, cluster in clusters.items():

            cluster_profile = self.profile.get(cluster_name, {})

            for route in cluster['routes']:

                route['compliance_status'] = True
                route_profile = cluster_profile.get(route['route'])

                for status in allowed_statuses:
                    key = 'validate_' + status
                    route[key] = {
                        'value': route[status],
                        'profile': None,
                        'compliance': None
                    }

                    if type(route_profile) is list:
                        route[key]['profile'] = status in route_profile

                        if route[key]['value'] is route[key]['profile']:
                            route[key]['compliance'] = True
                        else:
                            route[key]['compliance'] = False
                            route['compliance_status'] = False
                            self.holistic_compliance_status = False

        return clusters

    def get_holistic_compliance_status(self):

        self.get_clusters()
        return self.holistic_compliance_status

    def enforce(self):

        global _allowed_statuses
        global _allowed_statuses_apache_22

        allowed_statuses = _allowed_statuses_apache_22 if self.apache_version_is('2.2') else _allowed_statuses

        for route in self.get_routes():

            if route.get('compliance_status') is False:

                logger.info('enforcing profile for {cluster}->{route}'.format(**route))

                # build status dictionary to enforce
                route_statuses = {}
                for status in allowed_statuses:
                    route_statuses[status] = route['validate_' + status]['profile']

                self.change_route_status(
                    route['cluster'],
                    route['route'],
                    **route_statuses
                )

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

        for name, cluster in super(ValidationClient, self)._get_clusters_from_apache().items():

            cluster_profile = OrderedDict()

            for route in cluster['routes']:

                enabled_statuses = []

                for key, status in route.items():
                    if key.startswith('status_') and key in allowed_statuses:
                        if type(status) is not bool:
                            raise TypeError('status value must be boolean')
                        if status is True:
                            enabled_statuses.append(key)

                cluster_profile[route['route']] = enabled_statuses

            profile[name] = cluster_profile

        return profile
