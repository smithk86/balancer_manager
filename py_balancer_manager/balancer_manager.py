import asyncio

from ._parse import parse
from .client import Client
from .cluster import Cluster
from .errors import BalancerManagerError
from .helpers import find_object


class BalancerManager(object):
    def __init__(self, client):
        if isinstance(client, Client):
            self.client = client
        elif isinstance(client, dict):
            self.client = Client(**client)
        else:
            raise TypeError('client arg must be either py_balancer_manager.Client object or dict')

        self.httpd_version = None
        self.httpd_compile_date = None
        self.openssl_version = None
        self.clusters = list()
        self.date = None

    def __repr__(self):
        return f'<py_balancer_manager.BalancerManager object: {self.client.url} [clusters={len(self.clusters)}]>'

    @property
    def holistic_error_status(self):
        for cluster in self.clusters:
            # if self.holistic_error_status is True:
            #     return False
            for route in cluster.routes:
                if route._status.error.value is True:
                    return True
            return False

    def new_cluster(self, name):
        cluster = Cluster(self, name)
        self.clusters.append(cluster)
        return cluster

    def cluster(self, name):
        try:
            return find_object(self.clusters, 'name', name)
        except ValueError:
            raise BalancerManagerError(f'could not locate cluster name in list of clusters: {name}')

    async def update(self, response_payload=None):
        loop = asyncio.get_running_loop()
        if response_payload is None:
            async with self.client:
                response_payload = await self.client.get()
        await loop.run_in_executor(None, parse, response_payload, self)
        return self
