#!/usr/bin/env python

import sys
import os
import json
import argparse
import logging

from py_balancer_manager import Workflow


parser = argparse.ArgumentParser()
parser.add_argument('json-file')
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

Workflow(workflow, username='admin', password=os.environ.get('PASSWORD')).run()
