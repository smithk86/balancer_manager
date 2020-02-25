import argparse
import asyncio
import logging
import os
from getpass import getpass
from tzlocal import get_localzone

from termcolor import colored

from py_balancer_manager import BalancerManager
from .printer import print_routes


async def main():
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

    balancer_manager = BalancerManager(client={
        'url': getattr(args, 'balance-manager-url'),
        'insecure': args.insecure,
        'username': args.username,
        'password': password
    })
    await balancer_manager.update()

    if (args.ignore_errors is not None or
            args.draining_mode is not None or
            args.disabled is not None or
            args.hot_standby is not None):

        if args.cluster is None or args.route is None:
            raise ValueError('--cluster and --route are required')

        route = balancer_manager.cluster(args.cluster).route(args.route)

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

        await route.edit(args.cluster, args.route, **_kwargs)

    if args.cluster:
        routes = balancer_manager.cluster(args.cluster).routes
    else:
        routes = list()
        for cluster in balancer_manager.clusters:
            routes += cluster.routes

    print()
    print(f"{colored('url', 'blue')}: {balancer_manager.client.url}")
    print(f"{colored('httpd version', 'blue')}: {balancer_manager.httpd_version}")
    print(f"{colored('httpd build time', 'blue')}: {balancer_manager.httpd_compile_datetime.astimezone(get_localzone())}")

    if balancer_manager.openssl_version:
        print(f"{colored('openssl version', 'blue')}: {balancer_manager.openssl_version}")

    print()
    print_routes(routes, args.verbose)
    print()


if __name__ == '__main__':
    asyncio.run(main())
