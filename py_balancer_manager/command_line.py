import sys
import os
import json
import argparse
import requests
import logging
from getpass import getpass

from tzlocal import get_localzone

from . import Client, ValidationClient, Workflow, Workflow, print_routes, print_validated_routes
from .prettystring import PrettyString


def manage():

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

    client = Client(getattr(args, 'balance-manager-url'), insecure=args.insecure, username=args.username, password=password)

    if (args.ignore_errors is not None or
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

    if args.cluster:
        routes = client.get_cluster(args.cluster).get_routes()
    else:
        routes = client.get_routes()

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


def validate():

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

        print_validated_routes(
            client.get_routes()
        )

        if args.action == 'enforce' and client.holistic_compliance_status is False:

            print()
            print(PrettyString('***** compliance has been enforced *****', 'red'))

            client.enforce()

            print_validated_routes(
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


def workflow():

    parser = argparse.ArgumentParser()
    parser.add_argument('json-file')
    parser.add_argument('-u', '--username', help='http username', default='admin')
    parser.add_argument('-p', '--password', help='http password', default=None)
    parser.add_argument('-d', '--debug', action='store_true', default=False)
    args = parser.parse_args()

    if args.debug:
        logging.basicConfig(level=logging.DEBUG)

    try:
        with open(getattr(args, 'json-file'), 'r') as fh:
            workflow = json.load(fh)
    except FileNotFoundError:
        print('json file does not exist: {file}'.format(file=getattr(args, 'json-file')))
        sys.exit(1)

    if args.password is None:
        password = getpass('password # ')
    elif os.environ.get('PASSWORD'):
        password = os.environ.get('PASSWORD')
    else:
        password = args.password

    Workflow(
        workflow,
        username=args.username,
        password=password
    ).run()
