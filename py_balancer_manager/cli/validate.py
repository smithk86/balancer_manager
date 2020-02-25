import argparse
import asyncio
import json
import logging
import os
from getpass import getpass

from termcolor import cprint

from py_balancer_manager import ValidatedBalancerManager
from .printer import print_validated_routes


async def main():
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

    balancer_manager = ValidatedBalancerManager(client={
        'url': getattr(args, 'balance-manager-url'),
        'insecure': args.insecure,
        'username': args.username,
        'password': password
    })

    if args.action == 'validate' or args.action == 'enforce':
        await balancer_manager.update()
        routes = list()
        for cluster in balancer_manager.clusters:
            routes += cluster.routes
        print_validated_routes(routes)
        if args.action == 'enforce' and balancer_manager.holistic_compliance_status is False:
            print()
            cprint('***** compliance has been enforced *****', 'red')
            await balancer_manager.enforce()

            routes = list()
            for cluster in balancer_manager.clusters:
                routes += cluster.routes
            print_validated_routes(routes)

            if balancer_manager.holistic_compliance_status is False:
                raise Exception('profile has been enforced but still not compliant')

    elif args.action == 'build':
        profile = await balancer_manager.get_profile()
        if args.pretty:
            print(json.dumps(profile, indent=4))
        else:
            print(json.dumps(profile))

    else:
        raise RuntimeError(f'action does not exist: {args.action}')


if __name__ == '__main__':
    asyncio.run(main())
