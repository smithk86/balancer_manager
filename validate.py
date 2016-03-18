#!/usr/bin/env python

import sys
import os
import argparse
import getpass
import requests
import logging
import json

from py_balancer_manager import ValidationClient, printer
from py_balancer_manager.prettystring import PrettyString


# disable warnings
requests.packages.urllib3.disable_warnings()


def main():

    def print_routes(routes):

        for route in routes:
            for key, status in route.get('_validation_status', {}).items():
                if key.startswith('_'):
                    continue

                route[key] = PrettyString(
                    '\u2713' if route[key] else '\u2717{}'.format('' if status else ' **'),
                    'green' if status else 'red'
                )

        printer.routes(
            routes,
            args.verbose
        )

    parser = argparse.ArgumentParser()
    parser.add_argument('profile-json')
    parser.add_argument('-u', '--username', default=None)
    parser.add_argument('-p', '--password', action='store_true', default=False)
    parser.add_argument('-e', '--enforce', help='enforce profile', action='store_true', default=False)
    parser.add_argument('-v', '--verbose', help='print all route information', action='store_true', default=False)
    parser.add_argument('-d', '--debug', action='store_true', default=False)
    args = parser.parse_args()

    log_level = logging.DEBUG if args.debug else logging.WARN
    logging.basicConfig(level=log_level)

    try:
        with open(getattr(args, 'profile-json')) as fh:
            full_profile_json = fh.read()

        profile_dict = json.loads(full_profile_json)

    except FileNotFoundError:
        print('file does not exist: {profile}'.format(profile=getattr(args, 'profile-json')))
        sys.exit(1)

    if args.password:
        password = getpass.getpass('password # ')
    else:
        password = None

    client = ValidationClient(
        profile_dict.get('url'),
        profile=profile_dict,
        username=args.username,
        password=password,
        verify_ssl_cert=profile_dict.get('verify_ssl_cert')
    )

    print_routes(
        client.get_routes()
    )

    if args.enforce and client.holistic_compliance_status is False:
        print()
        print(PrettyString('***** compliance has been enforced *****', 'red'))

        client.enforce()

        print_routes(
            client.get_routes()
        )

        if client.holistic_compliance_status is False:
            raise Exception('profile has been enforced but still not compliant')


if __name__ == '__main__':

    main()
