#!/usr/bin/env python

import logging
from collections import OrderedDict

from .client import Client

logger = logging.getLogger(__name__)


def validate(profile_dict, enforce=False):

    client = Client(
        profile_dict['host'],
        verify_ssl_cert=profile_dict.get('verify_ssl_cert', True),
        username=profile_dict.get('username', None),
        password=profile_dict.get('password', None)
    )

    routes = []
    holistic_compliance_status = True
    default_route_profile = {
        'status_ok': True,
        'status_error': False
    }

    for key in client.get_validation_properties():
        default_route_profile[key] = profile_dict['default_route_profile'].pop(key)

    if len(profile_dict['default_route_profile']) > 0:
        raise Exception('there were unathorized validation properties provided: {}'.format(profile_dict['default_route_profile']))

    for cluster in profile_dict['clusters']:

        route_profiles = cluster.get('routes', {})

        for route in client.get_routes(cluster=cluster['name']):

            profile = default_route_profile.copy()
            profile.update(route_profiles.get(route['route'], {}))

            # create a special '_validate' key which will contain a dict of the validation data
            route['_validate'] = {}
            profile_compliance_status = True

            # for each validated route, push a tuple of the key and its validation status (True/False)
            for key, value in route.items():
                if key in profile:
                    if route[key] == profile[key]:
                        route['_validate'][key] = True
                    else:
                        route['_validate'][key] = False
                        profile_compliance_status = False
                        holistic_compliance_status = False

            if enforce and profile_compliance_status is False:

                logger.info('enforcing profile for {cluster}->{route}'.format(**route))

                status_dict = {}
                status_dict['status_disabled'] = profile.get('status_disabled')

                if client.apache_version_is('2.4.'):
                    status_dict['status_ignore_errors'] = profile.get('status_ignore_errors')
                    status_dict['status_draining_mode'] = profile.get('status_draining_mode')
                    status_dict['status_hot_standby'] = profile.get('status_hot_standby')

                client.change_route_status(
                    route,
                    **status_dict
                )

            routes.append(route)

    return (routes, holistic_compliance_status)


def build_profile(host, default_route_profile, **kwargs):

    client = Client(
        host,
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
    profile['host'] = host
    profile['username'] = kwargs.get('username', None)
    profile['password'] = kwargs.get('password', None)
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
