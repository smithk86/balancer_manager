import dataclasses

from .errors import BalancerManagerError
from .helpers import VERSION_24


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
        self.taking_traffic = None
        self.statuses = None

    def __repr__(self):
        return f'<py_balancer_manager.route.Route object: {self.cluster.name} -> {self.name}>'

    def asdict(self):
        return {
            'updated_datetime': self.updated_datetime,
            'name': self.name,
            'worker': self.worker,
            'priority': self.priority,
            'route_redir': self.route_redir,
            'factor': self.factor,
            'set': self.set,
            'elected': self.elected,
            'traffic_to': self.traffic_to,
            'traffic_to_raw': self.traffic_to_raw,
            'traffic_from': self.traffic_from,
            'traffic_from_raw': self.traffic_from_raw,
            'session_nonce_uuid': self.session_nonce_uuid,
            'taking_traffic': self.taking_traffic,
        }

    def mutable_statuses(self):
        allowed_statuses = list()
        for k, v in dataclasses.asdict(self.status).items():
            if v and v['immutable'] is False:
                allowed_statuses.append(k)
        return allowed_statuses

    async def change_status(self, force=False, **status_value_kwargs):
        mutable_statuses = self.mutable_statuses()
        new_route_statuses = dict()

        # confirm no immutable statuses are trying to be changed
        for key, val in status_value_kwargs.items():
            if key not in mutable_statuses:
                raise BalancerManagerError(f'{key} is not a valid status')

        # prepare new values to be sent to server
        for key in mutable_statuses:
            if key in status_value_kwargs:
                new_route_statuses[key] = status_value_kwargs.pop(key)
            else:
                new_route_statuses[key] = getattr(self.status, key).value

        # except routes with errors from throwing the "last-route" error
        if force is True or self.status.error is True or self.status.disabled is True or self.status.draining_mode is True:
            pass
        elif self.cluster.eligible_routes <= 1:
            if new_route_statuses['disabled'] is True:
                raise BalancerManagerError('cannot enable the "disabled" status for the last available route (cluster: {cluster_name}, route: {route_name})'.format(cluster_name=self.cluster.name, route_name=self.name))
            elif new_route_statuses.get('draining_mode') is True:
                raise BalancerManagerError('cannot enable the "draining mode" status for the last available route (cluster: {cluster_name}, route: {route_name})'.format(cluster_name=self.cluster.name, route_name=self.name))

        if self.cluster.client.httpd_version < VERSION_24:
            async with self.cluster.client.http_request('get', params={
                'lf': '1',
                'ls': '0',
                'wr': self.name,
                'rr': '',
                'dw': 'Disable' if new_route_statuses['disabled'] else 'Enable',
                'w': self.worker,
                'b': self.cluster.name,
                'nonce': str(self.session_nonce_uuid)
            }) as r:
                self.cluster.client.do_update(await r.text())
        else:
            post_data = {
                'w_lf': '1',
                'w_ls': '0',
                'w_wr': self.name,
                'w_rr': '',
                'w': self.worker,
                'b': self.cluster.name,
                'nonce': str(self.session_nonce_uuid)
            }
            for status_name in self.mutable_statuses():
                http_form_code = getattr(self.status, status_name).http_form_code
                post_data[f'w_status_{http_form_code}'] = int(new_route_statuses[status_name])
            async with self.cluster.client.http_request('post', data=post_data) as r:
                self.cluster.client.do_update(await r.text())

        # validate new values against load balancer
        for status_name, expected_value in new_route_statuses.items():
            current_value = getattr(self.status, status_name).value
            if expected_value is not current_value:
                raise BalancerManagerError(f'status value for "{status_name}" is {current_value} (should be {expected_value})')
