import re
import time
from datetime import datetime

from pytz import utc
from tzlocal import get_localzone
from dateutil.parser import parse as date_parser
from .errors import BalancerManagerError, ResultsError


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

    if len(objects) == 1:
        return objects[0]
    else:
        raise ResultsError('filter_objects() must return only one object; {} objects found'.format(len(objects)))
