#!/usr/bin/env python

import json
from collections import OrderedDict

from .client import Client


def validate(profile_json):

    full_profile = json.loads(profile_json)

    client = Client(
        full_profile['host'],
        verify_ssl_cert=full_profile.get('verify_ssl_cert', True),
        username=full_profile.get('username', None),
        password=full_profile.get('password', None)
    )

    routes = []

    for cluster in full_profile['clusters']:

        route_profiles = cluster.get('routes', {})

        for route in client.get_routes(cluster=cluster['name']):

            profile = full_profile['default_route_profile'].copy()
            profile.update(route_profiles.get(route['route'], {}))

            # create a special '_validate' key which will contain a list of the validation data
            route['_validate'] = []

            # for each validated route, push a tuple of the key and its validation status (True/False)
            for key, value in route.items():
                if key in profile:
                    route['_validate'].append((key, (route[key] == profile[key])))

            routes.append(route)

    return routes


def build_profile(host, default_route_profile, **kwargs):

    client = Client(
        host,
        verify_ssl_cert=kwargs.get('verify_ssl_cert', True),
        username=kwargs.get('username', None),
        password=kwargs.get('password', None)
    )

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

    print(json.dumps(profile, indent=4))
