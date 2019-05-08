import re
import time
from collections import namedtuple
from datetime import datetime

from packaging import version
from pytz import utc
from tzlocal import get_localzone
from dateutil.parser import parse as date_parser
from .errors import BalancerManagerError


VERSION_22 = version.parse('2.2')
VERSION_24 = version.parse('2.4')


Statuses = namedtuple('Statuses', ['ok', 'error', 'ignore_errors', 'draining_mode', 'disabled', 'hot_standby', 'hot_spare', 'stopped'])
Status = namedtuple('Status', ['value', 'immutable', 'http_form_code'])


def now():
    return datetime.now(utc)


def parse_from_local_timezone(date_string):
    return get_localzone().localize(date_parser(date_string)).astimezone(utc)


def filter_objects(list_of_objects, prop_name, value, regex=False):
    if regex:
        if type(value) is not str:
            raise ValueError('value must be a string when using regex')

        pattern = re.compile(value)
        return list(
            filter(lambda obj: pattern.match(getattr(obj, prop_name)), list_of_objects)
        )
    else:
        return list(
            filter(lambda obj: getattr(obj, prop_name) == value, list_of_objects)
        )


def find_object(list_of_objects, prop_name, value, regex=False):
    objects = filter_objects(list_of_objects, prop_name, value, regex=regex)
    return objects[0] if len(objects) == 1 else None
