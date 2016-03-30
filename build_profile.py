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
    parser.add_argument('balance-manager-url')
    parser.add_argument('-u', '--username', default=None)
    parser.add_argument('-p', '--password', action='store_true', default=False)
    parser.add_argument('--default-ignore-errors', dest='default_ignore_errors', default=None)
    parser.add_argument('--default-draining-mode', dest='default_draining_mode', default=None)
    parser.add_argument('--default-disabled', dest='default_disabled', default=None)
    parser.add_argument('--default-hot-standby', dest='default_hot_standby', default=None)
    parser.add_argument('-k', '--insecure', help='ignore ssl certificate errors', action='store_true', default=False)
    parser.add_argument('-d', '--debug', action='store_true', default=False)
    args = parser.parse_args()

    log_level = logging.DEBUG if args.debug else logging.WARN
    logging.basicConfig(level=log_level)

    if args.password:
        password = getpass('password # ')
    elif os.environ.get('PASSWORD'):
        password = os.environ.get('PASSWORD')
    else:
        password = None

    default_route_profile = {
        'status_ignore_errors': get_bool(args.default_ignore_errors),
        'status_draining_mode': get_bool(args.default_draining_mode),
        'status_disabled': get_bool(args.default_disabled),
        'status_hot_standby': get_bool(args.default_hot_standby),
    }

    profile_dict = build_profile(getattr(args, 'balance-manager-url'), default_route_profile, username=args.username, password=password, verify_ssl_cert=not args.insecure)

    print(json.dumps(profile_dict, indent=4))

if __name__ == '__main__':

    main()
