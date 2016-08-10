from .prettystring import PrettyString


def routes(routes, verbose=False):

    def _get_value(val):
        if val is None:
            return ''
        elif type(val) is bool:
            if val:
                return 'X'
            else:
                return ''
        elif type(val) is dict:
            return _get_value(val['value'])
        elif type(val) is int:
            return str(val)
        else:
            return val

    rows = []

    if verbose:

        rows.append([
            PrettyString('URL', 'bold'),
            PrettyString('Cluster', 'bold'),
            PrettyString('Worker URL', 'bold'),
            PrettyString('Route', 'bold'),
            PrettyString('Elected', 'bold'),
            PrettyString('To', 'bold'),
            PrettyString('From', 'bold'),
            PrettyString('Status: Ok', 'bold'),
            PrettyString('Active', 'bold'),
            PrettyString('Status: Err', 'bold'),
            PrettyString('Status: Ign', 'bold'),
            PrettyString('Status: Drn', 'bold'),
            PrettyString('Status: Dis', 'bold'),
            PrettyString('Status: Stby', 'bold'),
            PrettyString('Route Redir', 'bold'),
            PrettyString('Factor', 'bold'),
            PrettyString('Set', 'bold'),
            PrettyString('Busy', 'bold'),
            PrettyString('Load', 'bold')
        ])

    else:

        rows.append([
            PrettyString('URL', 'bold'),
            PrettyString('Cluster', 'bold'),
            PrettyString('Worker URL', 'bold'),
            PrettyString('Route', 'bold'),
            PrettyString('Status: Ok', 'bold'),
            PrettyString('Active', 'bold'),
            PrettyString('Status: Err', 'bold'),
            PrettyString('Status: Ign', 'bold'),
            PrettyString('Status: Drn', 'bold'),
            PrettyString('Status: Dis', 'bold'),
            PrettyString('Status: Stby', 'bold')
        ])

    if verbose:

        for route in routes:

            rows.append([
                PrettyString(_get_value(route['url']), 'cyan'),
                _get_value(route['cluster']),
                PrettyString(_get_value(route['worker']), 'yellow'),
                _get_value(route['route']),
                _get_value(route['elected']),
                _get_value(route['to']),
                _get_value(route['from']),
                _get_value(route['status_ok']),
                _get_value(route['taking_traffic']),
                _get_value(route['status_error']),
                _get_value(route['status_ignore_errors']),
                _get_value(route['status_draining_mode']),
                _get_value(route['status_disabled']),
                _get_value(route['status_hot_standby']),
                _get_value(route['route_redir']),
                _get_value(route['factor']),
                _get_value(route['set']),
                _get_value(route['busy']),
                _get_value(route['load'])
            ])

    else:

        for route in routes:
            rows.append([
                PrettyString(_get_value(route['url']), 'cyan'),
                _get_value(route['cluster']),
                PrettyString(_get_value(route['worker']), 'yellow'),
                _get_value(route['route']),
                _get_value(route['status_ok']),
                _get_value(route['taking_traffic']),
                _get_value(route['status_error']),
                _get_value(route['status_ignore_errors']),
                _get_value(route['status_draining_mode']),
                _get_value(route['status_disabled']),
                _get_value(route['status_hot_standby'])
            ])

    widths = [max(map(len, col)) for col in zip(*rows)]
    for row in rows:
        print(' | '.join((val.ljust(width) for val, width in zip(row, widths))))
