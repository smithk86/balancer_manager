from .prettystring import PrettyString


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
                PrettyString(_get_value(route.cluster.name), 'cyan'),
                PrettyString(_get_value(route.worker), 'yellow'),
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
                PrettyString(_get_value(route.cluster.name), 'cyan'),
                PrettyString(_get_value(route.worker), 'yellow'),
                _get_value(route.name),
                _get_value(route.status_ok),
                _get_value(route.taking_traffic),
                _get_value(route.status_error),
                _get_value(route.status_ignore_errors),
                _get_value(route.status_draining_mode),
                _get_value(route.status_disabled),
                _get_value(route.status_hot_standby)
            ])
    return rows


def get_formated_validated_routes(routes, hide_compliant_routes=False, verbose=False):
    for route in list(routes):
        if hide_compliant_routes is True and route.compliance_status is True:
            routes.remove(route)
            continue
        for status, _ in route.get_statuses().items():
            if status != 'status_ok' and status != 'status_error':
                validation = route.status_validation.get(status)
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
                        PrettyString(char, color)
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
