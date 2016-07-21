#!/usr/bin/env python

import sys
import os
import argparse
import requests
import logging
import json
from getpass import getpass

from py_balancer_manager import ValidationClient, printer
from py_balancer_manager.prettystring import PrettyString


# disable warnings
requests.packages.urllib3.disable_warnings()


def main():

    def print_routes(routes):
        for route in routes:
            for key, value in route.items():
                if key.startswith('status_') and type(value) is dict:
                    if value['value'] and value['compliance']:
                        char = ' \u2717'
                    elif value['value'] and not value['compliance']:
                        char = ' \u2717 **'
                    elif not value['value'] and not value['compliance']:
                        char = '[  ] **'
                    else:
                        char = ''

                    color = 'green' if value['compliance'] else 'red'

                    value['value'] = PrettyString(char, color)

        printer.routes(
            routes,
            args.verbose
        )

    parser = argparse.ArgumentParser()
    parser.add_argument('action', help='validate, enforce, build')
    parser.add_argument('balance-manager-url')
    parser.add_argument('profile-json', nargs='?')
    parser.add_argument('-u', '--username', default=None)
    parser.add_argument('-p', '--password', action='store_true', default=False)
    parser.add_argument('-k', '--insecure', help='ignore ssl certificate errors', action='store_true', default=False)
    parser.add_argument('-v', '--verbose', help='print all route information', action='store_true', default=False)
    parser.add_argument('-d', '--debug', action='store_true', default=False)
    parser.add_argument('--pretty', action='store_true', default=False)
    args = parser.parse_args()

    log_level = logging.DEBUG if args.debug else logging.WARN
    logging.basicConfig(level=log_level)

    if args.action == 'validate' or args.action == 'enforce':

        try:
            with open(getattr(args, 'profile-json')) as fh:
                profile_json = fh.read()

            profile = json.loads(profile_json)

        except FileNotFoundError:
            print('file does not exist: {profile}'.format(profile=getattr(args, 'profile-json')))
            sys.exit(1)
    else:
        profile = None

    if args.password:
        password = getpass('password # ')
    elif os.environ.get('PASSWORD'):
        password = os.environ.get('PASSWORD')
    else:
        password = None

    client = ValidationClient(
        getattr(args, 'balance-manager-url'),
        username=args.username,
        password=password,
        insecure=args.insecure,
        profile=profile
    )

    if args.action == 'validate' or args.action == 'enforce':

        print_routes(
            client.get_routes()
        )

        if args.action == 'enforce' and client.holistic_compliance_status is False:

            print()
            print(PrettyString('***** compliance has been enforced *****', 'red'))

            client.enforce()

            print_routes(
                client.get_routes()
            )

            if client.holistic_compliance_status is False:
                raise Exception('profile has been enforced but still not compliant')

    elif args.action == 'build':

        profile = client.get_profile()

        if args.pretty:
            print(json.dumps(profile, indent=4))
        else:
            print(json.dumps(profile))


if __name__ == '__main__':

    main()
