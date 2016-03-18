#!/usr/bin/env python

import threading
import logging
from collections import OrderedDict

from .client import Client

logger = logging.getLogger(__name__)


class ValidationClient(Client):

    def __init__(self, *args, **kwargs):

        self.profile = kwargs.pop('profile')
        self.holistic_compliance_status = False

        if self.profile is None:

            raise TypeError('self.profile is TypeNone')

        super(ValidationClient, self).__init__(*args, **kwargs)

    def _get_routes_from_apache(self):

        routes = super(ValidationClient, self)._get_routes_from_apache()

        self.holistic_compliance_status = True

        for route in routes:

            route_profiles = self._get_cluster_routes_from_profile(route['cluster'])

            # build profile for this route
            route['_validation_profile'] = self.profile['default_route_profile'].copy()
            route['_validation_profile'].update(route_profiles.get(route['route'], {}))

            # create a special '_validation_status' key which will contain a dict of the validation data
            route['_validation_status'] = {}
            route['_validation_status']['_holistic'] = True

            # --- update ----
            for key in route.keys():
                if key in route['_validation_profile']:
                    if route[key] == route['_validation_profile'][key]:
                        route['_validation_status'][key] = True
                    else:
                        route['_validation_status'][key] = False
                        route['_validation_status']['_holistic'] = False
                        self.holistic_compliance_status = False

        return routes

    def enforce(self):

        for route in self.get_routes():

            validation_status = route.get('_validation_status', {})
            validation_profile = route.get('_validation_profile', {})

            if validation_status.get('_holistic') is False:

                logger.info('enforcing profile for {cluster}->{route}'.format(**route))

                # build status dictionary to enforce
                route_statuses = {}
                route_statuses['status_disabled'] = validation_profile.get('status_disabled')

                if self.apache_version_is('2.4.'):
                    route_statuses['status_ignore_errors'] = validation_profile.get('status_ignore_errors')
                    route_statuses['status_draining_mode'] = validation_profile.get('status_draining_mode')
                    route_statuses['status_hot_standby'] = validation_profile.get('status_hot_standby')

                self.change_route_status(
                    route,
                    **route_statuses
                )

    def _get_cluster_routes_from_profile(self, cluster_name):

        for cluster in self.profile['clusters']:
            if cluster.get('name') == cluster_name:
                return cluster.get('routes', {})

        return {}


def build_profile(url, default_route_profile, **kwargs):

    client = Client(
        url,
        verify_ssl_cert=kwargs.get('verify_ssl_cert', True),
        username=kwargs.get('username', None),
        password=kwargs.get('password', None)
    )

    # apache 2.2 only supports 'disabled' and 'hot standby'
    if client.apache_version_is('2.2.'):
        default_route_profile = {
            'status_disabled': default_route_profile.get('status_disabled'),
            'status_hot_standby': default_route_profile.get('status_hot_standby')
        }

    profile = OrderedDict()
    profile['url'] = url
    profile['verify_ssl_cert'] = kwargs.get('verify_ssl_cert', True)
    profile['default_route_profile'] = default_route_profile
    profile['clusters'] = list()

    routes = client.get_routes()

    clusters = list()
    for route in routes:
        try:
            clusters.index(route['cluster'])
        except ValueError:
            clusters.append(route['cluster'])

    for cluster in clusters:

        cluster_profile = OrderedDict()
        cluster_profile['name'] = cluster
        cluster_profile['routes'] = dict()

        for route in client.get_routes(cluster=cluster):

            entries = {}

            for status_key in default_route_profile.keys():
                if default_route_profile[status_key] != route[status_key]:
                    entries[status_key] = route[status_key]

            if len(entries) > 0:
                cluster_profile['routes'][route['route']] = entries

        if len(cluster_profile['routes']) == 0:
            del(cluster_profile['routes'])

        profile['clusters'].append(cluster_profile)

    return profile
