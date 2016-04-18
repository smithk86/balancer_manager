#!/usr/bin/env python

import threading
import logging
from collections import OrderedDict

from .client import Client
from .errors import ValidationClientError


logger = logging.getLogger(__name__)


allowed_statuses = ['status_disabled', 'status_hot_standby', 'status_draining_mode', 'status_ignore_errors']
allowed_statuses_apache_22 = ['status_disabled']


class ValidationClient(Client):

    def __init__(self, *args, **kwargs):

        self.holistic_compliance_status = False
        self.container = kwargs.pop('container')
        profile_name = kwargs.pop('profile', 'default')
        self.set_profile(profile_name)

        super(ValidationClient, self).__init__(*args, **kwargs)

    def set_profile(self, profile_name):

        try:
            self.profile = self.container['profiles'][profile_name]
        except KeyError:
            self.profile = None
            raise ValidationClientError('profile does not exist -> {profile_name}'.format(**locals()))

    def _get_routes_from_apache(self):

        global allowed_statuses
        global allowed_statuses_apache_22

        if self.apache_version_is('2.2'):
            allowed_statuses = allowed_statuses_apache_22

        self.holistic_compliance_status = True

        routes = super(ValidationClient, self)._get_routes_from_apache()

        for route in routes:

            route['compliance_status'] = True
            route_profiles = self._get_cluster_routes_from_profile(route['cluster'])
            enabled_statuses_from_route_profile = route_profiles.get(route['route'], {})

            for status in allowed_statuses:
                route[status] = {
                    'value': route[status],
                    'profile': status in enabled_statuses_from_route_profile,
                }

                if route[status]['value'] is route[status]['profile']:
                    route[status]['compliance'] = True
                else:
                    route[status]['compliance'] = False
                    route['compliance_status'] = False
                    self.holistic_compliance_status = False

        return routes

    def change_route_status(self, route, status_ignore_errors=None, status_draining_mode=None, status_disabled=None, status_hot_standby=None):

        """ convert route statuses back to a simple bool so that it is compatible with the original Client object """

        for key, val in route.items():
            if key.startswith('status_') and type(val) is dict:
                route[key] = route[key]['value']

        import pprint
        pprint.PrettyPrinter(indent=4).pprint(route)

        super(ValidationClient, self).change_route_status(
            route,
            status_ignore_errors=status_ignore_errors,
            status_draining_mode=status_draining_mode,
            status_disabled=status_disabled,
            status_hot_standby=status_hot_standby
        )

    def enforce(self):

        global allowed_statuses
        global allowed_statuses_apache_22

        if self.apache_version_is('2.2'):
            allowed_statuses = allowed_statuses_apache_22

        for route in self.get_routes():

            if route.get('compliance_status') is False:

                logger.info('enforcing profile for {cluster}->{route}'.format(**route))

                # build status dictionary to enforce
                route_statuses = {}
                for status in allowed_statuses:
                    route_statuses[status] = route[status]['profile']

                self.change_route_status(
                    route,
                    **route_statuses
                )

    def _get_cluster_routes_from_profile(self, cluster_name):

        for cluster in self.profile['clusters']:
            if cluster.get('name') == cluster_name:
                return cluster.get('routes', {})

        return {}


def build_profile(url=None, container=None, profile_name='default', default=False, insecure=False, username=None, password=None):

    global allowed_statuses
    global allowed_statuses_apache_22

    if url is None and container is None:
        raise ValueError('url and container cannot both be null')

    # init client with container settings
    if container:

        client = Client(
            container.get('url'),
            insecure=container.get('insecure'),
            username=username,
            password=password
        )

        # if default is True, remove the default key from all other profiles
        if default:
            for profile in container['profiles']:
                profile.pep('default')

    # create a new container if none was passed
    else:

        client = Client(
            url,
            insecure=insecure,
            username=username,
            password=password
        )

        container = OrderedDict()
        container['url'] = url
        container['insecure'] = insecure
        container['profiles'] = {}

    if client.apache_version_is('2.2'):
        allowed_statuses = allowed_statuses_apache_22

    # raise error if profile name exists
    if profile_name in container['profiles']:
        raise KeyError('profile name exists: {profile_name}'.format(**locals()))

    # build empty profile
    profile = {
        'clusters': list(),
        'default': len(container['profiles']) == 0 or default
    }

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

            enabled_statuses = []

            for key, value in route.items():
                if key not in allowed_statuses:
                    continue

                if value is True:
                    enabled_statuses.append(key)

            if len(enabled_statuses) > 0:
                cluster_profile['routes'][route['route']] = enabled_statuses

        # if len(cluster_profile['routes']) == 0:
        #     del(cluster_profile['routes'])

        profile['clusters'].append(cluster_profile)

    container['profiles'][profile_name] = profile

    return container
