#!/usr/bin/env python

import sys
import os
import json
import argparse
from lib.ask import prompt

from py_balancer_manager import Workflow, print_validated_routes


class WorkflowCLI(Workflow):

    def print(self, *args, **kwargs):

        print(*args, **kwargs)

    def print_routes(self, routes):

        print_validated_routes(routes)

    def prompt(self, message):

        return prompt(message)

    def exit(self, retval=0):

        sys.exit(retval)


parser = argparse.ArgumentParser()
parser.add_argument('json-file')
args = parser.parse_args()

try:
    with open(getattr(args, 'json-file'), 'r') as fh:
        workflow = json.load(fh)
except FileNotFoundError:
    print('json file does not exist: {file}'.format(file=getattr(args, 'json-file')))
    sys.exit(1)

WorkflowCLI(workflow, username='admin', password=os.environ.get('PASSWORD')).run()
