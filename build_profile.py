#!/usr/bin/env python

import os
import argparse
from getpass import getpass
import requests
import logging

from py_balancer_manager import build_profile


# disable warnings
requests.packages.urllib3.disable_warnings()


def main():

    parser = argparse.ArgumentParser()
    parser.add_argument('balance-manager-url')
    parser.add_argument('-u', '--username', default=None)
    parser.add_argument('-p', '--password', action='store_true', default=False)
    parser.add_argument('-k', '--insecure', help='ignore ssl certificate errors', action='store_true', default=False)
    parser.add_argument('-d', '--debug', action='store_true', default=False)
    args = parser.parse_args()

    log_level = logging.DEBUG if args.debug else logging.WARN
    logging.basicConfig(level=log_level)

    if args.password:
        password = getpass('password # ')
    else:
        password = os.environ.get('PASSWORD')

    default_route_profile = {
        'status_ignore_errors': False,
        'status_draining_mode': False,
        'status_disabled': False,
        'status_hot_standby': False
    }

    build_profile(getattr(args, 'balance-manager-url'), default_route_profile, username=args.username, password=password, verify_ssl_cert=not args.insecure)

if __name__ == '__main__':

    main()
