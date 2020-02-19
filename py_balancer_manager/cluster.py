from .errors import BalancerManagerError
from .helpers import find_object
from .route import Route


class Cluster(object):
    def __init__(self, balancer_data, name):
        self.balancer_data = balancer_data
        self.name = name
        self.max_members = None
        self.max_members_used = None
        self.sticky_session = None
        self.disable_failover = None
        self.timeout = None
        self.failover_attempts = None
        self.method = None
        self.path = None
        self.active = None
        self.standby_activated = None
        self.eligible_routes = None
        self.routes = list()

    def __repr__(self):
        return f'<py_balancer_manager.Cluster object: {self.name}>'

    def asdict(self):
        return {
            'name': self.name,
            'max_members': self.max_members,
            'max_members_used': self.max_members_used,
            'sticky_session': self.sticky_session,
            'timeout': self.timeout,
            'failover_attempts': self.failover_attempts,
            'method': self.method,
            'path': self.path,
            'active': self.active,
            'standby_activated': self.standby_activated,
            'eligible_routes': self.eligible_routes,
            'routes': [r.asdict() for r in self.routes]
        }

    def new_route(self, name):
        route = Route(self.balancer_data, self.name, name)
        self.routes.append(route)
        return route

    def route(self, name):
        # find the route object in the route list
        try:
            return find_object(self.routes, 'name', name)
        except ValueError:
            raise BalancerManagerError(f'could not locate route name in list of routes: {name}')

    async def edit_lbset(self, lbset_number, force=False, factor=None, lbset=None, route_redir=None, **status_value_kwargs):
        for route in self.routes:
            if route.lbset == lbset_number:
                await route.edit(force=force, factor=factor, route_redir=route_redir, **status_value_kwargs)
