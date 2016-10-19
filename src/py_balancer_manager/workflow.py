import re
import logging
from abc import ABCMeta, abstractmethod

from .validate import ValidationClient
from .errors import BalancerManagerError


logger = logging.getLogger(__name__)


class EndWorkflow(Exception):
    pass


class Workflow(metaclass=ABCMeta):

    def __init__(self, workflow, username=None, password=None):

        self.workflow = workflow
        self.username = username
        self.password = password

        # prepare data model
        for step in self.workflow:
            for server in step['servers']:
                for server in step['servers'].values():
                    if username:
                        server['username'] = username
                    if password:
                        server['password'] = password
                    for action in step['actions']:
                        # add cluster_profiles dictionary
                        action['cluster_profiles'] = {}

    @abstractmethod
    def print(self, msg=None):

        pass

    @abstractmethod
    def print_routes(self, *args, **kwargs):

        pass

    @abstractmethod
    def prompt(self, *args, **kwargs):

        pass

    def tearDown(self):

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

        try:

            for step in self.workflow:

                try:

                    self.init_clients(step)
                    self.print_validation(step)
                    self.print()

                    if self.prompt(message='execute the above actions?') is False:
                        raise EndWorkflow()

                    self.print()
                    self.execute_changes(step)
                    self.print()

                except KeyboardInterrupt:
                    raise EndWorkflow()

                if self.has_reverts(step):

                    if self.prompt(message='are the soapui tests passing and routes ready to be enabled?'):
                        self.revert_changes(step)
                        self.print()
                    else:
                        raise EndWorkflow()

            self.print('done')

        except EndWorkflow:
            self.print()
            self.print('exiting workflow')
            self.print()

        self.tearDown()

    def init_clients(self, step):

        for name, server in step['servers'].items():
            if isinstance(server, ValidationClient):
                server.test()
            elif isinstance(server, dict):
                step['servers'][name] = ValidationClient(**server)
                step['servers'][name].test()
            else:
                raise BalancerManagerError('cannot convert server value into py_balancer_manager.ValidationClient')

    def print_validation(self, step):

        """ print the balancers and action so user can verify """

        self.print('workflow step: {name}'.format(name=step['name']))
        self.print('balancers:')
        for i, (name, server) in enumerate(step['servers'].items()):
            self.print('    #{i}: {name} ({url})'.format(
                i=i + 1,
                name=name,
                url=server.url
            ))
        self.print('actions:')
        for i, action in enumerate(step['actions']):
            self.print('    #{i}: (revert={revert})'.format(i=i + 1, revert='yes' if action['revert'] else 'no'))
            for route_name, route_changes in action['routes'].items():
                self.print('        {cluster} -> {route} [{changes}]'.format(
                    cluster=action['cluster'],
                    route=route_name,
                    changes=','.join(route_changes)
                ))

    def execute_changes(self, step):

        """ do the work """

        for name, server in step['servers'].items():

            for action in step['actions']:
                if action['revert'] is True:
                    action['cluster_profiles'][name] = server.get_profile().get(action['cluster'])

            for action in step['actions']:
                server.set_profile({
                    action['cluster']: action['cluster_profiles'].get(name, {})
                })
                for route_name, route_changes in action['routes'].items():
                    changes = {}
                    for change in route_changes:
                        status_name, enabled = Workflow.parse_status_change(change)
                        changes[status_name] = enabled

                    server.get_cluster(action['cluster']).get_route(route_name).change_status(**changes)

                self.print('URL: {url}'.format(url=server.url))
                self.print_routes(
                    server.get_cluster(action['cluster']).get_routes()
                )

    def has_reverts(self, step):

        """ check to see if a step should be reverted """

        for action in step['actions']:
            if action['revert'] is True:
                return True

        return False

    def revert_changes(self, step):

        """ revert changes by enforcing the cluster profile taken before the changes were made """

        self.print()
        for name, server in step['servers'].items():
            for action in step['actions']:
                if action['revert'] is True:
                    server.set_profile({
                        action['cluster']: action['cluster_profiles'][name]
                    })

                    self.print('enforcing the profile for {name} -> {cluster}'.format(name=name, cluster=action['cluster']))
                    self.print()

                    server.enforce()

                    self.print('URL: {url}'.format(url=server.url))
                    self.print_routes(
                        server.get_cluster(action['cluster']).get_routes()
                    )

                    if server.get_holistic_compliance_status() is False:
                        raise ValueError('{url} is out of compliance'.format(url=server))
