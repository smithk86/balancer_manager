import argparse
import logging
import os
from getpass import getpass
from tzlocal import get_localzone

from .. import Client
from .printer import print_routes
from .prettystring import PrettyString


async def manage():
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

    async with Client(getattr(args, 'balance-manager-url'), insecure=args.insecure, username=args.username, password=password) as client:
        if (args.ignore_errors is not None or
                args.draining_mode is not None or
                args.disabled is not None or
                args.hot_standby is not None):

            if args.cluster is None or args.route is None:
                raise ValueError('--cluster and --route are required')

            route = (await client.get_cluster(args.cluster)).get_route(args.route)

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

            await route.change_status(args.cluster, args.route, **_kwargs)

        if args.cluster:
            routes = (await client.get_cluster(args.cluster)).get_routes()
        else:
            routes = await client.get_routes()

        print()
        print('{label}: {val}'.format(
            label=PrettyString('url', 'blue'),
            val=client.url
        ))
        print('{label}: {val}'.format(
            label=PrettyString('httpd version', 'blue'),
            val=client.httpd_version
        ))
        print('{label}: {val}'.format(
            label=PrettyString('httpd build time', 'blue'),
            val=client.httpd_compile_datetime.astimezone(get_localzone())
        ))

        if client.openssl_version:
            print('{label}: {val}'.format(
                label=PrettyString('openssl version', 'blue'),
                val=client.openssl_version
            ))

        print()
        print_routes(routes, args.verbose)
        print()
