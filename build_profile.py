#!/usr/bin/env python

import os
import argparse
import requests
import logging
import json
from getpass import getpass

from py_balancer_manager import build_profile


# disable warnings
requests.packages.urllib3.disable_warnings()


def main():

    def get_bool(value):

        if value is None:
            return False
        elif value.lower() in ['true', '1', 'y', 'yes']:
            return True
        elif value.lower() in ['false', '0', 'n', 'no']:
            return False
        else:
            raise ValueError('could not parse "{value}" to boolean'.format(**locals()))

    parser = argparse.ArgumentParser()
    parser.add_argument('url', nargs='?', default=None)
    parser.add_argument('-c', '--container', default=None)
    parser.add_argument('-n', '--profile', default='default')
    parser.add_argument('-D', '--default', action='store_true', default=False)
    parser.add_argument('-u', '--username', default=None)
    parser.add_argument('-p', '--password', action='store_true', default=False)
    parser.add_argument('-P', '--pretty', action='store_true', default=False)
    parser.add_argument('-k', '--insecure', help='ignore ssl certificate errors', action='store_true', default=False)
    parser.add_argument('-d', '--debug', action='store_true', default=False)
    args = parser.parse_args()

    log_level = logging.DEBUG if args.debug else logging.WARN
    logging.basicConfig(level=log_level)

    if args.container:
        with open(args.container) as fh:
            container = json.load(fh)
    else:
        container = None

    if args.password:
        password = getpass('password # ')
    elif os.environ.get('PASSWORD'):
        password = os.environ.get('PASSWORD')
    else:
        password = None

    profile_dict = build_profile(url=args.url, container=container, profile_name=args.profile, username=args.username, password=password, insecure=args.insecure)

    if args.pretty:
        print(json.dumps(profile_dict, indent=4))
    else:
        print(json.dumps(profile_dict))


if __name__ == '__main__':

    main()
