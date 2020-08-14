import logging

from .errors import BalancerManagerError, MultipleExceptions
from .helpers import find_object
from .route import Route


logger = logging.getLogger(__name__)


class Cluster(object):
    def __init__(self, balancer_manager, name):
        self.balancer_manager = balancer_manager
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
        self._date = None
        self.routes = list()

    def __repr__(self):
        return f'<py_balancer_manager.Cluster object: {self.name}>'

    def new_route(self, name):
        route = Route(self, name)
        self.routes.append(route)
        return route

    def route(self, name):
        # find the route object in the route list
        try:
            return find_object(self.routes, 'name', name)
        except ValueError:
            raise BalancerManagerError(f'could not locate route name in list of routes: {name}')

    def lbsets(self):
        lbsets_ = dict()
        for route in self.routes:
            if route.lbset not in lbsets_:
                lbsets_[route.lbset] = list()
            lbsets_[route.lbset].append(route)
        return lbsets_

    def lbset(self, lbset_number):
        lbsets = self.lbsets()
        if lbset_number in lbsets:
            return lbsets[lbset_number]
        else:
            raise BalancerManagerError(f'lbset does not exist: {lbset_number}')

    async def edit_lbset(self, lbset_number, force=False, factor=None, lbset=None, route_redir=None, **status_value_kwargs):
        exceptions = []
        for route in self.lbset(lbset_number):
            try:
                await route.edit(force=force, factor=factor, route_redir=route_redir, **status_value_kwargs)
            except Exception as e:
                logger.exception(e)
                exceptions.append(e)
        if len(exceptions) > 0:
            raise MultipleExceptions(exceptions)
