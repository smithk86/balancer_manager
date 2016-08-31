#!/usr/bin/env python

import threading
import logging
from collections import OrderedDict

from .client import Client
from .errors import ValidationClientError


logger = logging.getLogger(__name__)


_allowed_statuses = ['status_disabled', 'status_hot_standby', 'status_draining_mode', 'status_ignore_errors']
_allowed_statuses_apache_22 = ['status_disabled']


class ValidationClient(Client):

    def __init__(self, url, **kwargs):

        self.holistic_compliance_status = False
        self.profile = kwargs.pop('profile', None)

        super(ValidationClient, self).__init__(url, **kwargs)

        if self.profile is None:
            self.profile = self.get_profile()

    def _get_clusters_from_apache(self):

        if self.profile is None:
            return super(ValidationClient, self)._get_clusters_from_apache()

        global _allowed_statuses
        global _allowed_statuses_apache_22

        allowed_statuses = _allowed_statuses_apache_22 if self.apache_version_is('2.2') else _allowed_statuses

        self.holistic_compliance_status = True

        clusters = super(ValidationClient, self)._get_clusters_from_apache()

        for cluster in clusters.values():
            for route in cluster['routes']:

                route['compliance_status'] = True
                enabled_statuses_from_profile = self.profile.get(route['cluster'], {}).get(route['route'], {})

                for status in allowed_statuses:
                    route[status] = {
                        'value': route[status],
                        'profile': status in enabled_statuses_from_profile,
                    }

                    if route[status]['value'] is route[status]['profile']:
                        route[status]['compliance'] = True
                    else:
                        route[status]['compliance'] = False
                        route['compliance_status'] = False
                        self.holistic_compliance_status = False

        return clusters

    def change_route_status(self, cluster_name, route_name, status_ignore_errors=None, status_draining_mode=None, status_disabled=None, status_hot_standby=None):

        """ convert route statuses back to a simple bool so that it is compatible with the original Client object """

        super(ValidationClient, self).change_route_status(
            cluster_name,
            route_name,
            status_ignore_errors=status_ignore_errors,
            status_draining_mode=status_draining_mode,
            status_disabled=status_disabled,
            status_hot_standby=status_hot_standby
        )

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
                    route_statuses[status] = route[status]['profile']

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

                if len(enabled_statuses) > 0:
                    cluster_profile[route['route']] = enabled_statuses

            profile[name] = cluster_profile

        return profile
