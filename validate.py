#!/usr/bin/env python

import os
import argparse
import requests
import logging

import py_balancer_manager
from py_balancer_manager import printer
from py_balancer_manager.prettystring import PrettyString


# disable warnings
requests.packages.urllib3.disable_warnings()


def main():

    parser = argparse.ArgumentParser()
    parser.add_argument('profile-json')
    parser.add_argument('-v', '--verbose', help='print all route information', action='store_true', default=False)
    parser.add_argument('-d', '--debug', action='store_true', default=False)
    args = parser.parse_args()

    log_level = logging.DEBUG if args.debug else logging.WARN
    logging.basicConfig(level=log_level)

    try:
        with open(getattr(args, 'profile-json')) as fh:
            full_profile_json = fh.read()
    except FileNotFoundError:
        print('file does not exist: {profile}'.format(profile=getattr(args, 'profile-json')))

    routes = py_balancer_manager.validate(full_profile_json)

    for route in routes:
        for key, status in route.get('_validate'):
            color = 'green' if status else 'red'
            route[key] = PrettyString(route[key], color)

    printer.routes(
        routes,
        args.verbose
    )


if __name__ == '__main__':

    main()
