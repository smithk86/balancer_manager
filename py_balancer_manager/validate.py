#!/usr/bin/env python

import json

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
