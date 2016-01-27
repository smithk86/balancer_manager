#!/usr/bin/env python

import json

from .client import Client
from .prettystring import PrettyString


def validate(profile_json, verify_ssl_cert=True):

    full_profile = json.loads(profile_json)

    client = Client(full_profile['host'], verify_ssl_cert=verify_ssl_cert, username=full_profile['username'], password=full_profile['password'])

    validated_routes = []

    for cluster in full_profile['clusters']:
        route_profiles = cluster.get('routes', {})

        for route in client.get_routes(cluster=cluster['name']):
            profile = full_profile['default_route_profile'].copy()
            profile.update(route_profiles.get(route['route'], {}))

            for key, value in route.items():
                if key in profile:
                    if route[key] == profile[key]:
                        route[key] = PrettyString(value, 'green')
                    else:
                        route[key] = PrettyString(value, 'red')

            validated_routes.append(route)

    return validated_routes
