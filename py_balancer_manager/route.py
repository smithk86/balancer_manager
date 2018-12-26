from .errors import BalancerManagerError, HttpdVersionError


class RouteChangeValidationError(BalancerManagerError):
    pass


class Route(object):
    def __init__(self, cluster):
        self.cluster = cluster
        self.updated_datetime = None
        self.name = None
        self.worker = None
        self.priority = None
        self.route_redir = None
        self.factor = None
        self.set = None
        self.elected = None
        self.busy = None
        self.load = None
        self.traffic_to = None
        self.traffic_to_raw = None
        self.traffic_from = None
        self.traffic_from_raw = None
        self.session_nonce_uuid = None
        self.status_ok = None
        self.status_error = None
        self.status_ignore_errors = None
        self.status_draining_mode = None
        self.status_disabled = None
        self.status_hot_standby = None
        self.taking_traffic = None
        self.immutable_statuses = []

    def __iter__(self):
        yield ('updated_datetime', self.updated_datetime)
        yield ('name', self.name)
        yield ('worker', self.worker)
        yield ('priority', self.priority)
        yield ('route_redir', self.route_redir)
        yield ('factor', self.factor)
        yield ('set', self.set)
        yield ('elected', self.elected)
        yield ('traffic_to', self.traffic_to)
        yield ('traffic_to_raw', self.traffic_to_raw)
        yield ('traffic_from', self.traffic_from)
        yield ('traffic_from_raw', self.traffic_from_raw)
        yield ('session_nonce_uuid', self.session_nonce_uuid)
        yield ('status_ok', self.status_ok)
        yield ('status_error', self.status_error)
        yield ('status_ignore_errors', self.status_ignore_errors)
        yield ('status_draining_mode', self.status_draining_mode)
        yield ('status_disabled', self.status_disabled)
        yield ('status_hot_standby', self.status_hot_standby)
        yield ('taking_traffic', self.taking_traffic)

    def get_statuses(self):
        return {
            'status_ignore_errors': self.status_ignore_errors,
            'status_draining_mode': self.status_draining_mode,
            'status_disabled': self.status_disabled,
            'status_hot_standby': self.status_hot_standby
        }

    def get_immutable_statuses(self):
        if self.cluster.client.httpd_version_is('2.2.'):
            return [
                'status_hot_standby',
                'status_draining_mode',
                'status_ignore_errors'
            ]
        else:
            return []

    def change_status(self, force=False, status_ignore_errors=None, status_draining_mode=None, status_disabled=None, status_hot_standby=None):
        # confirm no immutable statuses are trying to be changed
        for key, val in locals().items():
            if key in self.get_immutable_statuses():
                if val is not None:
                    raise HttpdVersionError('{} is immutable for this version of httpd'.format(key))

        # create dictionary of existing values which are allowed by the httpd version
        new_route_statuses = self.get_statuses()
        for status_name in new_route_statuses.copy().keys(): # use copy to avoid a "dictionary was modified during iteration" error
            if status_name in self.get_immutable_statuses():
                new_route_statuses.pop(status_name)
            elif type(locals().get(status_name)) is bool:
                new_route_statuses[status_name] = locals().get(status_name)

        # except routes with errors from throwing the "last-route" error
        if force is True or self.status_error is True or self.status_disabled is True or self.status_draining_mode is True:
            pass
        elif self.cluster.eligible_routes <= 1:
            if new_route_statuses['status_disabled'] is True:
                raise BalancerManagerError('cannot enable the "disabled" status for the last available route (cluster: {cluster_name}, route: {route_name})'.format(cluster_name=self.cluster.name, route_name=self.name))
            elif new_route_statuses['status_draining_mode'] is True:
                raise BalancerManagerError('cannot enable the "draining mode" status for the last available route (cluster: {cluster_name}, route: {route_name})'.format(cluster_name=self.cluster.name, route_name=self.name))

        if self.cluster.client.httpd_version_is('2.2.'):
            self.cluster.client.request_get(params={
                'lf': '1',
                'ls': '0',
                'wr': self.name,
                'rr': '',
                'dw': 'Disable' if new_route_statuses['status_disabled'] else 'Enable',
                'w': self.worker,
                'b': self.cluster.name,
                'nonce': str(self.session_nonce_uuid)
            })
        else:
            self.cluster.client.request_post(data={
                'w_lf': '1',
                'w_ls': '0',
                'w_wr': self.name,
                'w_rr': '',
                'w_status_I': int(new_route_statuses['status_ignore_errors']),
                'w_status_N': int(new_route_statuses['status_draining_mode']),
                'w_status_D': int(new_route_statuses['status_disabled']),
                'w_status_H': int(new_route_statuses['status_hot_standby']),
                'w': self.worker,
                'b': self.cluster.name,
                'nonce': str(self.session_nonce_uuid)
            })

        # validate new values against load balancer
        for status_name in new_route_statuses.keys():
            if new_route_statuses[status_name] is not getattr(self, status_name):
                raise RouteChangeValidationError('status value for "{}" is incorrect (should be {})'.format(status_name, getattr(self, status_name)))
