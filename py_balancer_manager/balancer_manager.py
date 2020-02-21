from .cluster import Cluster
from .errors import BalancerManagerError
from .helpers import find_object


class BalancerManager(object):
    def __init__(self, client):
        self.client = client
        self.updated_datetime = None
        self.httpd_version = None
        self.httpd_compile_datetime = None
        self.openssl_version = None
        self.clusters = list()

    def __repr__(self):
        return f'<py_balancer_manager.BalancerManager object: {self.client.url} [clusters={len(self.clusters)}]>'

    def asdict(self):
        return {
            'url': self.client.url,
            'insecure': self.client.insecure,
            'updated_datetime': self.updated_datetime,
            'httpd_version': self.httpd_version,
            'httpd_compile_datetime': self.httpd_compile_datetime,
            'openssl_version': self.openssl_version
        }

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
        if response_payload is None:
            response_payload = await self.client._http_get_payload()
        self.client._parse(response_payload, self)
