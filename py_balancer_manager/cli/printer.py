import dataclasses

from termcolor import colored


def get_formated_routes(routes, verbose=False):
    def _get_value(val):
        if val is None:
            return ''
        elif type(val) is bool:
            if val:
                return 'X'
            else:
                return ''
        elif type(val) is int:
            return str(val)
        else:
            return val

    rows = []

    if verbose:
        rows.append([
            colored('Cluster', 'white', attrs=['bold']),
            colored('Worker URL', 'white', attrs=['bold']),
            colored('Route', 'white', attrs=['bold']),
            colored('Elected', 'white', attrs=['bold']),
            colored('To', 'white', attrs=['bold']),
            colored('From', 'white', attrs=['bold']),
            colored('Status: Ok', 'white', attrs=['bold']),
            colored('Active', 'white', attrs=['bold']),
            colored('Status: Err', 'white', attrs=['bold']),
            colored('Status: Ign', 'white', attrs=['bold']),
            colored('Status: Drn', 'white', attrs=['bold']),
            colored('Status: Dis', 'white', attrs=['bold']),
            colored('Status: Stby', 'white', attrs=['bold']),
            colored('Route Redir', 'white', attrs=['bold']),
            colored('Factor', 'white', attrs=['bold']),
            colored('Set', 'white', attrs=['bold']),
            colored('Busy', 'white', attrs=['bold']),
            colored('Load', 'white', attrs=['bold'])
        ])
    else:
        rows.append([
            colored('Cluster', 'white', attrs=['bold']),
            colored('Worker URL', 'white', attrs=['bold']),
            colored('Route', 'white', attrs=['bold']),
            colored('Status: Ok', 'white', attrs=['bold']),
            colored('Active', 'white', attrs=['bold']),
            colored('Status: Err', 'white', attrs=['bold']),
            colored('Status: Ign', 'white', attrs=['bold']),
            colored('Status: Drn', 'white', attrs=['bold']),
            colored('Status: Dis', 'white', attrs=['bold']),
            colored('Status: Stby', 'white', attrs=['bold'])
        ])

    if verbose:
        for route in routes:
            rows.append([
                colored(_get_value(route.cluster.name), 'cyan'),
                colored(_get_value(route.worker), 'yellow'),
                _get_value(route.name),
                _get_value(route.elected),
                _get_value(route.traffic_to),
                _get_value(route.traffic_from),
                _get_value(route.status_ok),
                _get_value(route.taking_traffic),
                _get_value(route.status_error),
                _get_value(route.status_ignore_errors),
                _get_value(route.status_draining_mode),
                _get_value(route.status_disabled),
                _get_value(route.status_hot_standby),
                _get_value(route.route_redir),
                _get_value(route.factor),
                _get_value(route.set),
                _get_value(route.busy),
                _get_value(route.load)
            ])
    else:
        for route in routes:
            rows.append([
                colored(_get_value(route.cluster.name), 'cyan'),
                colored(_get_value(route.worker), 'yellow'),
                _get_value(route.name),
                _get_value(route.status('ok').value),
                _get_value(route.taking_traffic),
                _get_value(route.status('error').value),
                _get_value(route.status('ignore_errors').value),
                _get_value(route.status('draining_mode').value),
                _get_value(route.status('disabled').value),
                _get_value(route.status('hot_standby').value)
            ])
    return rows


def get_formated_validated_routes(routes, hide_compliant_routes=False, verbose=False):
    for route in list(routes):
        if hide_compliant_routes is True and route.compliance_status is True:
            routes.remove(route)
            continue
        for status, _ in dataclasses.asdict(route._status).items():
            if status != 'ok' and status != 'error':
                validation = route.status(status)
                if type(validation) is dict:
                    if validation['compliance'] is None:
                        char = ' X' if validation['value'] else ''
                        color = 'blue'
                    else:
                        if not validation['value'] and validation['compliance'] is None:
                            char = ''
                        elif validation['value'] and validation['compliance']:
                            char = ' \u2717'
                        elif validation['value'] and not validation['compliance']:
                            char = ' \u2717 **'
                        elif not validation['value'] and not validation['compliance']:
                            char = '[  ] **'
                        else:
                            char = ''

                        color = 'green' if validation['compliance'] else 'red'

                    setattr(
                        route,
                        status,
                        colored(char, color)
                    )
    return get_formated_routes(routes, verbose)


def print_routes(routes, verbose=False):
    _print_table(
        get_formated_routes(
            routes,
            verbose
        )
    )


def print_validated_routes(routes, hide_compliant_routes=False, verbose=False):
    _print_table(
        get_formated_validated_routes(
            routes,
            hide_compliant_routes=hide_compliant_routes,
            verbose=verbose
        )
    )


def _print_table(rows):
    widths = [max(map(len, col)) for col in zip(*rows)]
    for row in rows:
        print(' | '.join((val.ljust(width) for val, width in zip(row, widths))))
