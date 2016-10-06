#!/usr/bin/env python

import os
import argparse
import requests
import logging
from getpass import getpass

import py_balancer_manager
from py_balancer_manager import print_routes


# disable warnings
requests.packages.urllib3.disable_warnings()


def main():

    def get_bool(value):

        if value is None:
            return False
        elif value.lower() in ['true', '1', 'y', 'yes', 'enabled']:
            return True
        elif value.lower() in ['false', '0', 'n', 'no', 'disabled']:
            return False
        else:
            raise ValueError('could not parse "{value}" to boolean'.format(**locals()))

    parser = argparse.ArgumentParser()
    parser.add_argument('balance-manager-url')
    parser.add_argument('-l', '--list', dest='list_routes', action='store_true', default=False)
    parser.add_argument('-c', '--cluster')
    parser.add_argument('-r', '--route')
    parser.add_argument('--ignore-errors', dest='ignore_errors', default=None)
    parser.add_argument('--draining-mode', dest='draining_mode', default=None)
    parser.add_argument('--disabled', default=None)
    parser.add_argument('--hot-standby', dest='hot_standby', default=None)
    parser.add_argument('-u', '--username', default=None)
    parser.add_argument('-p', '--password', action='store_true', default=False)
    parser.add_argument('-k', '--insecure', help='ignore ssl certificate errors', action='store_true', default=False)
    parser.add_argument('-v', '--verbose', help='print all route information', action='store_true', default=False)
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

    client = py_balancer_manager.Client(getattr(args, 'balance-manager-url'), insecure=args.insecure, username=args.username, password=password)
    if args.cluster:
        routes = client.get_cluster(args.cluster).get_routes()
    else:
        routes = client.get_routes()

    if args.list_routes:
        print_routes(routes, args.verbose)

    elif (args.ignore_errors is not None or
            args.draining_mode is not None or
            args.disabled is not None or
            args.hot_standby is not None):

        if args.cluster is None or args.route is None:
            raise ValueError('--cluster and --route are required')

        route = client.get_cluster(args.cluster).get_route(args.route)

        _kwargs = {}
        try:
            if args.ignore_errors is not None:
                _kwargs['status_ignore_errors'] = get_bool(args.ignore_errors)
            if args.draining_mode is not None:
                _kwargs['status_draining_mode'] = get_bool(args.draining_mode)
            if args.disabled is not None:
                _kwargs['status_disabled'] = get_bool(args.disabled)
            if args.hot_standby is not None:
                _kwargs['status_ignore_errors'] = get_bool(args.hot_standby)
        except ValueError:
            raise ValueError('status value must be passed as either 0 (Off) or 1 (On)')

        route.change_status(args.cluster, args.route, **_kwargs)

    else:
        print('no actionable arguments were provided')


if __name__ == '__main__':
    main()
