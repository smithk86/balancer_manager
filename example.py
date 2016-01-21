#!/usr/bin/env python

import argparse
import requests
import logging

from py_balancer_manager import ApacheBalancerManager
from py_balancer_manager import ApacheBalancerManagerPollThread

# disable warnings
requests.packages.urllib3.disable_warnings()


def main():

    def get_value(val):
        if val is None:
            return ''
        elif type(val) is bool:
            if val:
                return 'on'
            else:
                return 'off'
        else:
            return val

    def print_routes(routes):

        rows = [[
            'URL',
            'Apache Version',
            'Cluster',
            'Worker URL',
            'Route',
            'Route Redir',
            'Factor',
            'Set',
            'Status: Init',
            'Status: Ign',
            'Status: Drn',
            'Status: Dis',
            'Status: Stby',
            'Elected',
            'Busy',
            'Load',
            'To',
            'From',
            'Session Nonce UUID'
        ]]

        for route in routes:
            rows.append([
                get_value(route['apache_manager_url']),
                get_value(route['apache_version']),
                get_value(route['cluster']),
                get_value(route['url']),
                get_value(route['route']),
                get_value(route['route_redir']),
                get_value(route['factor']),
                get_value(route['set']),
                get_value(route['status_init']),
                get_value(route['status_ignore_errors']),
                get_value(route['status_draining_mode']),
                get_value(route['status_disabled']),
                get_value(route['status_hot_standby']),
                get_value(route['elected']),
                get_value(route['busy']),
                get_value(route['load']),
                get_value(route['to']),
                get_value(route['from']),
                get_value(route['session_nonce_uuid'])
            ])

        widths = [max(map(len, col)) for col in zip(*rows)]
        for row in rows:
            print(' | '.join((val.ljust(width) for val, width in zip(row, widths))))

    parser = argparse.ArgumentParser()
    parser.add_argument('balance-manager-url')
    parser.add_argument('-l', '--list', dest='list_routes', action='store_true', default=False)
    parser.add_argument('-c', '--cluster')
    parser.add_argument('-r', '--route')
    parser.add_argument('--enable', action='store_true', default=False)
    parser.add_argument('--disable', action='store_true', default=False)
    parser.add_argument('-u', '--username', default=None)
    parser.add_argument('-p', '--password', default=None)
    parser.add_argument('-k', '--insecure', help='ignore ssl certificate errors', action='store_true', default=False)
    parser.add_argument('-d', '--debug', action='store_true', default=False)
    args = parser.parse_args()

    log_level = logging.DEBUG if args.debug else logging.WARN
    logging.basicConfig(level=log_level)

    urls = getattr(args, 'balance-manager-url').split(',')

    if len(urls) > 1:
        routes = []
        threads = []
        for url in urls:
            threads.append(ApacheBalancerManagerPollThread(url, verify_ssl_cert=not args.insecure, username=args.username, password=args.password))

        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()

        for thread in threads:
            if type(thread.routes) is list:
                routes += thread.routes

    else:
        abm = ApacheBalancerManager(getattr(args, 'balance-manager-url'), verify_ssl_cert=not args.insecure, username=args.username, password=args.password)
        routes = abm.get_routes()

    if args.enable and args.disable:
        raise ValueError('--enable and --disable are incompatible')

    if args.list_routes:
        print_routes(routes)

    elif args.enable or args.disable:

        if args.cluster is None or args.route is None:
            raise ValueError('--cluster and --route are required')

        for route in routes:
            if route['cluster'] == args.cluster and route['route'] == args.route:
                status_disabled = True if args.disable else False
                abm.change_route_status(route, status_disabled=status_disabled)


if __name__ == '__main__':
    main()
