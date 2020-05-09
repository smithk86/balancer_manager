import dataclasses
import logging

from .helpers import RefererParams
from .errors import BalancerManagerError


logger = logging.getLogger(__name__)


class Route(object):
    def __init__(self, cluster, name):
        self.cluster = cluster
        self.name = name
        self.worker = None
        self.priority = None
        self.route_redir = None
        self.factor = None
        self.lbset = None
        self.elected = None
        self.busy = None
        self.load = None
        self.traffic_to = None
        self.traffic_from = None
        self.session_nonce_uuid = None
        self.taking_traffic = None
        self._status = None
        self._date = None

    def __repr__(self):
        return f'<py_balancer_manager.Route object: {self.cluster.name} -> {self.name}>'

    def asdict(self):
        return {
            'name': self.name,
            'worker': self.worker,
            'priority': self.priority,
            'route_redir': self.route_redir,
            'factor': self.factor,
            'lbset': self.lbset,
            'elected': self.elected,
            'busy': self.busy,
            'traffic_to': self.traffic_to._asdict(),
            'traffic_from': self.traffic_from._asdict(),
            'session_nonce_uuid': self.session_nonce_uuid,
            'taking_traffic': self.taking_traffic,
            'status': self._status
        }

    def mutable_statuses(self):
        allowed_statuses = list()
        for k, v in dataclasses.asdict(self._status).items():
            if v and v['immutable'] is False:
                allowed_statuses.append(k)
        return allowed_statuses

    def status(self, name):
        return getattr(self._status, name)

    async def edit(self, force=False, factor=None, lbset=None, route_redir=None, **status_value_kwargs):
        _mutable_statuses = self.mutable_statuses()
        new_route_statuses = dict()

        # confirm no immutable statuses are trying to be changed
        for key, val in status_value_kwargs.items():
            if key not in _mutable_statuses:
                raise BalancerManagerError(f'{key} is not a mutable status')

        # prepare new values to be sent to server
        for key in _mutable_statuses:
            if key in status_value_kwargs:
                new_route_statuses[key] = status_value_kwargs.pop(key)
            else:
                new_route_statuses[key] = self.status(key).value

        # except routes with errors from throwing the "last-route" error
        if force is True or self._status.error is True or self._status.disabled is True or self._status.draining_mode is True:
            pass
        elif self.cluster.eligible_routes <= 1:
            if new_route_statuses['disabled'] is True:
                raise BalancerManagerError('cannot enable the "disabled" status for the last available route (cluster: {cluster_name}, route: {route_name})'.format(cluster_name=self.cluster.name, route_name=self.name))
            elif new_route_statuses.get('draining_mode') is True:
                raise BalancerManagerError('cannot enable the "draining mode" status for the last available route (cluster: {cluster_name}, route: {route_name})'.format(cluster_name=self.cluster.name, route_name=self.name))

        post_data = {
            'w_lf': factor if factor else self.factor,
            'w_ls': lbset if lbset else self.lbset,
            'w_wr': self.name,
            'w_rr': route_redir if route_redir else self.route_redir,
            'w': self.worker,
            'b': self.cluster.name,
            'nonce': str(self.session_nonce_uuid)
        }

        for status_name in self.mutable_statuses():
            http_form_code = self.status(status_name).http_form_code
            post_data[f'w_status_{http_form_code}'] = int(new_route_statuses[status_name])

        logger.debug(f'post payload {self.cluster.name}->{self.name}: {post_data}')

        referer_params = RefererParams(
            cluster=self.cluster.name,
            w=self.worker,
            nonce=str(self.session_nonce_uuid)
        )
        async with self.cluster.balancer_manager.client._http_client(referer_params=referer_params) as client:
            r = await client.post(self.cluster.balancer_manager.client.url, data=post_data)

        await self.cluster.balancer_manager.update(response_payload=r.text)

        # validate new values against load balancer
        for status_name, expected_value in new_route_statuses.items():
            current_value = self.status(status_name).value
            if expected_value is not current_value:
                raise BalancerManagerError(f'status value for "{status_name}" is {current_value} (should be {expected_value})')
