#!/usr/bin/env python

import os
import argparse
import requests
import logging
import threading
from getpass import getpass

import py_balancer_manager
from py_balancer_manager import printer

# disable warnings
requests.packages.urllib3.disable_warnings()


class ClientThread(threading.Thread):

    def __init__(self, client):
        threading.Thread.__init__(self)

        if type(client) is not Client:
            raise TypeError('first argument must be of type py_balancer_manager.Client')

        self.client = client
        self.routes = None

    def run(self):

        self.routes = self.client.get_routes()


class ClientAggregator:

    def __init__(self):
        self.clients = {}

    def add_client(self, client, client_id=None):

        if type(client) is Client:

            if client_id:
                self.clients.client_id = client_id

            self.clients.append(client)

    def get_servers(self):

        servers = []
        threads = []

        for client in self.clients:
            threads.append(ClientThread(client))

        for thread in threads:
            thread.start()

        for thread in threads:
            thread.join()

        for thread in threads:
            servers.append(thread.routes)

        return servers


def main():

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

    urls = getattr(args, 'balance-manager-url').split(',')

    if len(urls) > 1:

        clients = ClientAggregator()

        for url in urls:
            clients.add_client(
                py_balancer_manager.Client(url, verify_ssl_cert=not args.insecure, username=args.username, password=password)
            )

        routes = clients.get_routes()

    else:
        client = py_balancer_manager.Client(getattr(args, 'balance-manager-url'), verify_ssl_cert=not args.insecure, username=args.username, password=password)
        routes = client.get_routes(cluster=args.cluster)

    if args.list_routes:
        printer.routes(routes, args.verbose)

    elif (args.ignore_errors is not None or
            args.draining_mode is not None or
            args.disabled is not None or
            args.hot_standby is not None):

        if args.cluster is None or args.route is None:
            raise ValueError('--cluster and --route are required')

        route = client.get_route(args.cluster, args.route)

        if route:

            _kwargs = {}
            try:
                if args.ignore_errors is not None:
                    _kwargs['status_ignore_errors'] = bool(int(args.ignore_errors))
                if args.draining_mode is not None:
                    _kwargs['status_draining_mode'] = bool(int(args.draining_mode))
                if args.disabled is not None:
                    _kwargs['status_disabled'] = bool(int(args.disabled))
                if args.hot_standby is not None:
                    _kwargs['status_ignore_errors'] = bool(int(args.hot_standby))
            except ValueError:
                raise ValueError('status value must be passed as either 0 (Off) or 1 (On)')

            client.change_route_status(route, **_kwargs)

        else:
            raise NameError('no route was matched to the given cluster ({cluster}) and route ({route})'.format(cluster=args.cluster, route=args.route))

    else:
        print('no actionable arguments were provided')


if __name__ == '__main__':
    main()
