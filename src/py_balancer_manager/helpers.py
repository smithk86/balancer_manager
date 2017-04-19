import re
from datetime import datetime

import pytz
from .errors import BalancerManagerError, ResultsError


datetime_timezone_utc = pytz.timezone('UTC')


def now():

    return datetime_timezone_utc.localize(datetime.utcnow())


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
