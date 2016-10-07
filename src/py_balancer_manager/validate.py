import threading
import logging

from .client import Client


logger = logging.getLogger(__name__)


_allowed_statuses = ['status_disabled', 'status_hot_standby', 'status_draining_mode', 'status_ignore_errors']
_allowed_statuses_apache_22 = ['status_disabled']


class ValidationClient(Client):

    def __init__(self, url, **kwargs):

        self.holistic_compliance_status = False
        self.profile = kwargs.pop('profile', None)

        super(ValidationClient, self).__init__(url, **kwargs)

    def _update_clusters_from_apache(self):

        global _allowed_statuses
        global _allowed_statuses_apache_22

        allowed_statuses = _allowed_statuses_apache_22 if self.apache_version_is('2.2') else _allowed_statuses

        self.holistic_compliance_status = True

        super(ValidationClient, self)._update_clusters_from_apache()

        if self.profile is None:
            return

        for cluster in self.clusters:

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
        # refresh routes to include profile information
        self.refresh()

    def get_profile(self):

        global _allowed_statuses
        global _allowed_statuses_apache_22

        allowed_statuses = _allowed_statuses_apache_22 if self.apache_version_is('2.2') else _allowed_statuses

        # init empty list for the profile
        profile = dict()

        for cluster in self.get_clusters():

            cluster_profile = dict()

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
