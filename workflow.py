#!/usr/bin/env python

import sys
import os
import re
import json
import argparse
from lib.ask import prompt

from py_balancer_manager import ValidationClient, print_validated_routes


def parse_status_change(value):

    status_pattern = re.compile(r'([\-\+])(\w*)')
    match = status_pattern.match(value)
    if match:
        enable = (match.group(1) == '+')
        status_name = 'status_{status_name}'.format(status_name=match.group(2))
        return status_name, enable

    raise ValueError('must be a valid status name with a leading "+" or "-"')

import pprint
printer = pprint.PrettyPrinter(indent=4)

parser = argparse.ArgumentParser()
parser.add_argument('json-file')
args = parser.parse_args()

with open(getattr(args, 'json-file'), 'r') as fh:
    workflow = json.load(fh)

for group in workflow:

    has_reverts = False

    print()
    print('action: {name}'.format(name=group['name']))
    print('balancers:')
    for i, load_balancer in enumerate(group['load_balancers']):
        print('    #{i}: {name} ({url})'.format(
            i=i+1,
            name=load_balancer['name'],
            url=load_balancer['url']
        ))
    print('actions:')
    for i, action in enumerate(group['actions']):
        print('    #{i}: (revert={revert})'.format(i=i+1, revert='yes' if action['revert'] else 'no'))
        for route in action['routes']:
            print('        {cluster} -> {route} [{changes}]'.format(
                cluster=action['cluster'],
                route=route['name'],
                changes=','.join(route['changes'])
                ))
    print()

    if not prompt(message='execute the above actions?'):
        print()
        sys.exit(1)
    print()

    # prepare data model
    for load_balancer in group['load_balancers']:
        for action in group['actions']:
            action['cluster_profiles'] = {}

    # start main loop
    for load_balancer in group['load_balancers']:
        load_balancer['client'] = ValidationClient(load_balancer['url'], username='admin', password=os.environ.get('PASSWORD'))

        for action in group['actions']:
            if action['revert'] is True:
                has_reverts = True
                action['cluster_profiles'][load_balancer['name']] = load_balancer['client'].get_profile().get(action['cluster'])

        for action in group['actions']:
            load_balancer['client'].set_profile({
                action['cluster']: action['cluster_profiles'].get(load_balancer['name'], {})
            })
            for route in action['routes']:
                changes = {}
                for change in route['changes']:
                    status_name, enable = parse_status_change(change)
                    changes[status_name] = enable
                load_balancer['client'].change_route_status(action['cluster'], route['name'], **changes)

            print('URL: {url}'.format(url=load_balancer['url']))
            print_validated_routes(
                load_balancer['client'].get_routes(cluster=action['cluster'])
            )

    print() 

    if has_reverts:
        
        if not prompt(message='are the soapui tests passing and routes ready to be enabled?'):
            print()
            sys.exit(1)
        else:
            for load_balancer in group['load_balancers']:
                for action in group['actions']:
                    if action['revert'] is True:
                        load_balancer['client'].set_profile({
                            action['cluster']: action['cluster_profiles'][load_balancer['name']]
                        })

                        load_balancer['client'].enforce()

                        if load_balancer['client'].get_holistic_compliance_status() is False:
                            raise ValueError('{url} is out of compliance'.format(url=load_balancer['client']))

                        print('the balancer profiles has been enforced for {name} -> {cluster}'.format(name=load_balancer['name'], cluster=action['cluster']))

            print()
