import os
import json
import logging

logger = logging.getLogger(__name__)

var_dict = {}
var_json = '{this_dir}/vars.json'.format(this_dir=os.path.abspath(os.path.join(os.path.dirname(__file__))))

if os.path.isfile(var_json):
    with open(var_json) as fh:
        var_dict.update(json.load(fh))
else:
    self.logger.warning('var.conf does not exit')


def get_var(key, default=None):

    if default is None:
        return var_dict[key]
    else:
        return var_dict.get(key, default)
