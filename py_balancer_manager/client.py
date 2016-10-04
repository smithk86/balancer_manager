import re
import time
import logging
from collections import OrderedDict
from uuid import UUID

import requests
from bs4 import BeautifulSoup

from .errors import BalancerManagerError


logger = logging.getLogger(__name__)


def _decode_data_useage(usage_string):

    usage_string = usage_string.strip()

    try:
        # match string from manager page to number + kilo/mega/giga/tera-byte
        match = re.match('([\d\.]*)([KMGT]?)', usage_string)
        if match:
            num = float(match.group(1))
            scale_code = match.group(2)
            if scale_code == 'K':
                return int(num * 1000)
            elif scale_code == 'M':
                return int(num * 1000000)
            elif scale_code == 'G':
                return int(num * 1000000000)
            elif scale_code == 'T':
                return int(num * 1000000000000)
            else:
                return int(num)
        elif usage_string == '0':
            return 0

    except Exception as e:
        logger.exception(e)

    return 'NaN'


class ApacheVersionError(BalancerManagerError):
    pass

class RouteNotFound(BalancerManagerError):
    pass


class Cluster:

    def __init__(self, client):

        self.client = client
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

    def __iter__(self):

        yield ('name', self.name)
        yield ('max_members', self.max_members)
        yield ('max_members_used', self.max_members_used)
        yield ('sticky_session', self.sticky_session)
        yield ('route_redir', self.route_redir)
        yield ('timeout', self.timeout)
        yield ('failover_attempts', self.failover_attempts)
        yield ('method', self.method)
        yield ('path', self.path)
        yield ('active', self.active)
        yield ('standby_activated', self.standby_activated)
        yield ('eligible_routes', self.eligible_routes)
        yield ('routes', [dict(r) for r in self.routes])

    def add_route(self, route):

        if not isinstance(route, Route):
            raise TypeError('argument 2 must be a Route object')

        self.routes.append(route)

    def get_routes(self):

        return self.routes

    def get_route(self, name):

        # find the route object in the route list
        route = list(
            filter(lambda r: r.name == name, self.routes)
        )

        if len(route) != 1:
            raise BalancerManagerError('could not locate route name in list of routes: {name}'.format(**locals()))

        return route.pop()


class Route:

    def __init__(self, cluster):

        self.cluster = cluster
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

    def __iter__(self):

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

    def change_status(self, status_ignore_errors=None, status_draining_mode=None, status_disabled=None, status_hot_standby=None):

        if self.cluster.client.apache_version_is('2.4.'):
            new_route_statuses = {
                'status_ignore_errors': self.status_ignore_errors,
                'status_draining_mode': self.status_draining_mode,
                'status_disabled': self.status_disabled,
                'status_hot_standby': self.status_hot_standby
            }
        elif self.cluster.client.apache_version_is('2.2.'):
            new_route_statuses = {
                'status_disabled': self.status_disabled
            }
            if status_ignore_errors is not None:
                raise ApacheVersionError('status_ignore_errors is not supported in apache 2.2')
            if status_draining_mode is not None:
                raise ApacheVersionError('status_draining_mode is not supported in apache 2.2')
            if status_hot_standby is not None:
                raise ApacheVersionError('status_hot_standby is not supported in apache 2.2')
        else:
            raise BalancerManagerError('py_balancer_manager only supports apache 2.2 and 2.4')

        if type(status_ignore_errors) is bool:
            new_route_statuses['status_ignore_errors'] = status_ignore_errors
        if type(status_draining_mode) is bool:
            new_route_statuses['status_draining_mode'] = status_draining_mode
        if type(status_disabled) is bool:
            new_route_statuses['status_disabled'] = status_disabled
        if type(status_hot_standby) is bool:
            new_route_statuses['status_hot_standby'] = status_hot_standby

        # except routes with errors from throwing the "last-route" error
        if self.status_error is True or self.status_disabled is True or self.status_draining_mode is True:
            pass
        elif self.cluster.eligible_routes <= 1:
            if new_route_statuses['status_disabled'] is True:
                raise BalancerManagerError('cannot enable the "disabled" status for the last available route (cluster: {cluster_name}, route: {route_name})'.format(cluster_name=self.cluster.name, route_name=self.name))
            elif new_route_statuses['status_draining_mode'] is True:
                raise BalancerManagerError('cannot enable the "draining mode" status for the last available route (cluster: {cluster_name}, route: {route_name})'.format(cluster_name=self.cluster.name, route_name=self.name))

        if self.cluster.client.apache_version_is('2.4.'):
            post_data = {
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
            }
            self.cluster.client._request_session_post(data=post_data)

        elif self.cluster.client.apache_version_is('2.2.'):
            get_data = {
                'lf': '1',
                'ls': '0',
                'wr': self.name,
                'rr': '',
                'dw': 'Disable' if new_route_statuses['status_disabled'] else 'Enable',
                'w': self.worker,
                'b': self.cluster.name,
                'nonce': str(self.session_nonce_uuid)
            }
            self.cluster.client._request_session_get(params=get_data)

        # expire cache to force refresh
        self.cluster.client.expire_route_cache()


class Client:

    def __init__(self, url, insecure=False, username=None, password=None, cache_ttl=60, timeout=30):

        if type(insecure) is not bool:
            raise TypeError('insecure must be type bool')

        if insecure is True:
            logger.warning('ssl certificate verification is disabled')

        self.url = url
        self.timeout = timeout

        self.insecure = insecure
        self.apache_version = None
        self.request_exception = None

        self.cache_ttl = cache_ttl
        self.cache_clusters = None
        self.cache_clusters_time = 0

        self.session = requests.Session()
        self.session.headers.update({
            'User-agent': 'py_balancer_manager.Client'
        })

        if username and password:
            self.session.auth = (username, password)

    def __iter__(self):

        yield ('url', self.url)
        yield ('insecure', self.insecure)
        yield ('apache_version', self.apache_version)
        yield ('request_exception', str(self.request_exception))
        yield ('clusters', [dict(c) for c in self.cache_clusters] if self.cache_clusters else None)

    def close(self):

        self.session.close()

    def _request_session_get(self, **kwargs):

        kwargs['method'] = 'get'
        return self._request_session(**kwargs)

    def _request_session_post(self, **kwargs):

        kwargs['method'] = 'post'
        return self._request_session(**kwargs)

    def _request_session(self, **kwargs):

        if 'timeout' not in kwargs:
            kwargs['timeout'] = self.timeout
        if 'verify' not in kwargs:
            kwargs['verify'] = not self.insecure

        request_method = kwargs.pop('method', 'get')

        response = None

        try:

            response = getattr(self.session, request_method)(self.url, **kwargs)

            if response.status_code is not requests.codes.ok:
                response.raise_for_status()
            else:
                self.request_exception = None

        except requests.exceptions.RequestException as e:

            self.request_exception = e
            raise BalancerManagerError(e)

        return response

    def set_apache_version(self):

        if self.apache_version:
            # do not re-poll if self.apache_version is already set
            return True

        page = self._get_soup_html()

        full_version_string = page.find('dt').text
        match = re.match(r'^Server\ Version:\ Apache/([\.0-9]*)', full_version_string)
        if match:
            self.apache_version = match.group(1)

        logger.info('apache version: {apache_version}'.format(apache_version=self.apache_version))

        if self.apache_version is None:
            raise TypeError('apache version parse failed')

    def apache_version_is(self, version):

        self.set_apache_version()

        if self.apache_version:
            return self.apache_version.startswith(version)
        else:
            raise ApacheVersionError('no apache version has been set')

    def test(self):

        self._request_session_get()

    def _get_soup_html(self):

        req = self._request_session_get()

        if req.status_code is not requests.codes.ok:
            req.raise_for_status()

        return BeautifulSoup(req.text, 'html.parser')

    def get_clusters(self, use_cache=True):

        self.set_apache_version()

        now = time.time()

        # if cache is expired
        if self.cache_clusters_time < (now - self.cache_ttl):
            self.cache_clusters = None

        # if use_cache has been set to False
        if use_cache is False:
            self.cache_clusters = None

        if not self.cache_clusters:
            logger.debug('refreshing route cache')
            self.cache_clusters = self._get_clusters_from_apache()
            self.cache_clusters_time = now

        return self.cache_clusters

    def get_cluster(self, name, use_cache=True):

        clusters = self.get_clusters(use_cache=use_cache)

        # find the cluster object for this route
        cluster = list(
            filter(lambda c: c.name == name, clusters)
        )

        if len(cluster) != 1:
            raise BalancerManagerError('could not locate route name in list of routes: {name}'.format(**locals()))

        return cluster.pop()

    def get_routes(self, use_cache=True):

        routes = []
        for cluster in self.get_clusters(use_cache=use_cache):
            routes += cluster.get_routes()
        return routes

    def expire_route_cache(self):
        # expire cache to force refresh
        self.cache_clusters_time = 0

    def _get_clusters_from_apache(self):

        def parse_max_members(value):

            m = re.match(r'^(\d*) \[(\d*) Used\]$', value)
            if m:
                return(
                    int(m.group(1)),
                    int(m.group(2))
                )

            raise ValueError('MaxMembers value from Apache could not be parsed')

        page = self._get_soup_html()
        session_nonce_uuid_pattern = re.compile(r'.*&nonce=([-a-f0-9]{36}).*')
        cluster_name_pattern = re.compile(r'.*\?b=(.*?)&.*')

        _tables = page.find_all('table')
        page_cluster_tables = _tables[::2]
        page_route_tables = _tables[1::2]

        clusters = list()

        # only iterate through odd tables which contain cluster data
        for table in page_cluster_tables:

            cluster = Cluster(self)

            header = table.findPreviousSiblings('h3', limit=1)[0]
            balancer_uri_pattern = re.compile('balancer://(.*)')
            header_text = header.a.text if header.a else header.text

            m = balancer_uri_pattern.search(header_text)
            if m:
                cluster.name = m.group(1)
            else:
                raise ValueError('cluster name could not be parsed from <h3> tag')

            if cluster.name in [c.name for c in clusters]:
                continue

            for row in table.find_all('tr'):
                cells = row.find_all('td')

                if len(cells) == 0:
                    continue

                if self.apache_version_is('2.4.'):
                    cluster.max_members, cluster.max_members_used = parse_max_members(cells[0].text)
                    # below is a workaround for a bug in the html formatting in apache 2.4.20 in which the StickySession cell closing tag comes after DisableFailover
                    # HTML = <td>JSESSIONID<td>Off</td></td>
                    sticky_session_value = cells[1].find(text=True, recursive=False).strip()
                    cluster.sticky_session = False if sticky_session_value == '(None)' else sticky_session_value
                    cluster.disable_failover = 'On' in cells[2].text
                    cluster.timeout = int(cells[3].text)
                    cluster.failover_attempts = int(cells[4].text)
                    cluster.method = cells[5].text
                    cluster.path = cells[6].text
                    cluster.active = 'Yes' in cells[7].text

                elif self.apache_version_is('2.2.'):
                    cluster.sticky_session = False if cells[0].text == '(None)' else cells[0].text
                    cluster.timeout = int(cells[1].text)
                    cluster.failover_attempts = int(cells[2].text)
                    cluster.method = cells[3].text

            clusters.append(cluster)

        # only iterate through even tables which contain route data
        for table in page_route_tables:
            for i, row in enumerate(table.find_all('tr')):
                cells = row.find_all('td')

                if len(cells) == 0:
                    continue

                worker_url = cells[0].find('a')['href']
                session_nonce_uuid = None

                if worker_url:
                    session_nonce_uuid_match = session_nonce_uuid_pattern.search(worker_url)
                    if session_nonce_uuid_match:
                        session_nonce_uuid = session_nonce_uuid_match.group(1)

                cluster_name_match = cluster_name_pattern.search(worker_url)

                if not cluster_name_match:
                    raise BalancerManagerError("could not determine route's cluster")

                # find the cluster object for this route
                cluster = list(
                    filter(lambda c: c.name == cluster_name_match.group(1), clusters)
                )

                if len(cluster) != 1:
                    raise BalancerManagerError('could not locate cluster name in list of clusters: {name}'.format(name=cluster_name_match.group(1)))

                cluster = cluster.pop()

                route = Route(cluster)

                if self.apache_version_is('2.4.'):
                    route.worker = cells[0].find('a').text
                    route.name = cells[1].text
                    route.priority = i
                    route.route_redir = cells[2].text
                    route.factor = int(cells[3].text)
                    route.set = int(cells[4].text)
                    route.status_ok = 'Ok' in cells[5].text
                    route.status_error = 'Err' in cells[5].text
                    route.status_ignore_errors = 'Ign' in cells[5].text
                    route.status_draining_mode = 'Drn' in cells[5].text
                    route.status_disabled = 'Dis' in cells[5].text
                    route.status_hot_standby = 'Stby' in cells[5].text
                    route.elected = int(cells[6].text)
                    route.busy = int(cells[7].text)
                    route.load = int(cells[8].text)
                    route.traffic_to = cells[9].text
                    route.traffic_to_raw = _decode_data_useage(cells[9].text)
                    route.traffic_from = cells[10].text
                    route.traffic_from_raw = _decode_data_useage(cells[10].text)
                    route.session_nonce_uuid = UUID(session_nonce_uuid)

                elif self.apache_version_is('2.2.'):
                    route.worker = cells[0].find('a').text
                    route.name = cells[1].text
                    route.priority = i
                    route.route_redir = cells[2].text
                    route.factor = int(cells[3].text)
                    route.set = int(cells[4].text)
                    route.status_ok = 'Ok' in cells[5].text
                    route.status_error = 'Err' in cells[5].text
                    route.status_ignore_errors = None
                    route.status_draining_mode = None
                    route.status_disabled = 'Dis' in cells[5].text
                    route.status_hot_standby = 'Stby' in cells[5].text
                    route.elected = int(cells[6].text)
                    route.busy = None
                    route.load = None
                    route.traffic_to = cells[7].text
                    route.traffic_to_raw = _decode_data_useage(cells[7].text)
                    route.traffic_from = cells[8].text
                    route.traffic_from_raw = _decode_data_useage(cells[8].text)
                    route.session_nonce_uuid = UUID(session_nonce_uuid)

                else:
                    raise ValueError('this module only supports apache 2.2 and 2.4')

                cluster.add_route(route)

        # iterate clusters for post-parse processing
        for cluster in clusters:
            # determine if standby routes are active for cluster
            cluster.standby_activated = True
            for route in cluster.routes:
                if route.status_ok and route.status_hot_standby is False:
                    cluster.standby_activated = False
                    break
            # set "standby_activated" property depending on "standby_activated" status
            for route in cluster.routes:
                if cluster.standby_activated is False:
                    route.taking_traffic = (route.status_error is False and route.status_disabled is False and route.status_draining_mode is not True and route.status_hot_standby is False)
                else:
                    route.taking_traffic = (route.status_error is False and route.status_disabled is False and route.status_draining_mode is not True and route.status_hot_standby is True)
            # calculate the number of routes which are eligible to take traffic
            cluster.eligible_routes = 0
            for route in cluster.routes:
                if route.status_error is False and route.status_disabled is False and route.status_draining_mode is not True:
                    cluster.eligible_routes += 1

        return clusters
