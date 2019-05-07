from .errors import BalancerManagerError
from .helpers import find_object
from .route import Route


class Cluster(object):
    def __init__(self, client):
        self.client = client
        self.updated_datetime = None
        self.name = None
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
        return f'<py_balancer_manager.cluster.Cluster object: {self.name}>'

    def to_dict(self):
        yield ('updated_datetime', self.updated_datetime)
        yield ('name', self.name)
        yield ('max_members', self.max_members)
        yield ('max_members_used', self.max_members_used)
        yield ('sticky_session', self.sticky_session)
        yield ('timeout', self.timeout)
        yield ('failover_attempts', self.failover_attempts)
        yield ('method', self.method)
        yield ('path', self.path)
        yield ('active', self.active)
        yield ('standby_activated', self.standby_activated)
        yield ('eligible_routes', self.eligible_routes)
        yield ('routes', [dict(r) for r in self.routes])

    def new_route(self):
        route = Route(self)
        self.routes.append(route)
        return route

    def get_routes(self):
        return self.routes

    def get_route(self, name):
        # find the route object in the route list
        route = find_object(self.routes, 'name', name)
        if route:
            return route
        else:
            raise BalancerManagerError(f'could not locate route name in list of routes: {name}')
