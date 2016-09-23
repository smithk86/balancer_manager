import re
from abc import ABCMeta, abstractmethod

from .validate import ValidationClient


class Workflow(metaclass=ABCMeta):

    def __init__(self, workflow, username=None, password=None):

        self.workflow = workflow
        self.has_reverts = False
        self.username = username
        self.password = password

        # prepare data model
        for group in self.workflow:
            for load_balancer in group['load_balancers']:
                for load_balancer in group['load_balancers']:
                    for action in group['actions']:
                        # add cluster_profiles dictionary
                        action['cluster_profiles'] = {}

    @abstractmethod
    def print(self, *args, **kwargs):

        pass

    @abstractmethod
    def prompt(self, *args, **kwargs):

        pass

    @abstractmethod
    def exit(self, *args, **kwargs):

        pass

    @staticmethod
    def parse_status_change(value):

        status_pattern = re.compile(r'([\-\+])(\w*)')
        match = status_pattern.match(value)
        if match:
            enable = (match.group(1) == '+')
            status_name = 'status_{status_name}'.format(status_name=match.group(2))
            return status_name, enable

        raise ValueError('must be a valid status name with a leading "+" or "-"')

    def run(self):

        """ run the workflow logic """

        self.print()

        for group in self.workflow:

            self.print_validation(group)
            self.print()

            if not self.prompt(message='execute the above actions?'):
                self.print()
                self.exit()

            self.print()
            self.execute_changes(group)
            self.print()

            if self.has_reverts:
                self.revert_changes(group)
                self.print()

    def print_validation(self, group):

        """ print the balancers and action so user can verify """

        self.print('action: {name}'.format(name=group['name']))
        self.print('balancers:')
        for i, load_balancer in enumerate(group['load_balancers']):
            self.print('    #{i}: {name} ({url})'.format(
                i=i + 1,
                name=load_balancer['name'],
                url=load_balancer['url']
            ))
        self.print('actions:')
        for i, action in enumerate(group['actions']):
            self.print('    #{i}: (revert={revert})'.format(i=i + 1, revert='yes' if action['revert'] else 'no'))
            for route in action['routes']:
                self.print('        {cluster} -> {route} [{changes}]'.format(
                    cluster=action['cluster'],
                    route=route['name'],
                    changes=','.join(route['changes'])
                ))

    def execute_changes(self, group):

        """ do the work """

        for load_balancer in group['load_balancers']:
            load_balancer['client'] = ValidationClient(load_balancer['url'], username=self.username, password=self.password)

            for action in group['actions']:
                if action['revert'] is True:
                    self.has_reverts = True
                    action['cluster_profiles'][load_balancer['name']] = load_balancer['client'].get_profile().get(action['cluster'])

            for action in group['actions']:
                load_balancer['client'].set_profile({
                    action['cluster']: action['cluster_profiles'].get(load_balancer['name'], {})
                })
                for route in action['routes']:
                    changes = {}
                    for change in route['changes']:
                        status_name, enable = Workflow.parse_status_change(change)
                        changes[status_name] = enable
                    load_balancer['client'].change_route_status(action['cluster'], route['name'], **changes)

                self.print('URL: {url}'.format(url=load_balancer['url']))
                self.print_routes(
                    load_balancer['client'].get_routes(cluster=action['cluster'])
                )

    def revert_changes(self, group):

        """ revert changes by enforcing the cluster profile taken before the changes were made """

        if not self.prompt(message='are the soapui tests passing and routes ready to be enabled?'):
            self.print()
            self.exit(1)
        else:
            self.print()
            for load_balancer in group['load_balancers']:
                for action in group['actions']:
                    if action['revert'] is True:
                        load_balancer['client'].set_profile({
                            action['cluster']: action['cluster_profiles'][load_balancer['name']]
                        })

                        load_balancer['client'].enforce()

                        if load_balancer['client'].get_holistic_compliance_status() is False:
                            raise ValueError('{url} is out of compliance'.format(url=load_balancer['client']))

                        self.print('the balancer profiles has been enforced for {name} -> {cluster}'.format(name=load_balancer['name'], cluster=action['cluster']))
