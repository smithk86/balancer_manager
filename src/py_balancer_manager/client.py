import re
import logging
from uuid import UUID
from datetime import timedelta

import requests
from bs4 import BeautifulSoup

from .errors import BalancerManagerError, ResultsError, NotFound
from .helpers import now, find_object


class BalancerManagerParseError(BalancerManagerError):
    pass


class ApacheVersionError(BalancerManagerError):
    pass


class RouteChangeValidationError(BalancerManagerError):
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
        try:
            return find_object(self.routes, 'name', name)
        except ResultsError:
            raise NotFound('could not locate route name in list of routes: {}'.format(name))


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
        self.immutable_statuses = []

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

    def get_immutable_statuses(self):

        if self.cluster.client.apache_version_is('2.2.'):
            return [
                'status_hot_standby',
                'status_draining_mode',
                'status_ignore_errors'
            ]
        else:
            return []

    def change_status(self, status_ignore_errors=None, status_draining_mode=None, status_disabled=None, status_hot_standby=None):

        # confirm no immutable statuses are trying to be changed
        for key, val in locals().items():
            if key in self.get_immutable_statuses():
                if val is not None:
                    raise ApacheVersionError('{} is immutable for this version of apache'.format(key))

        # create dictionary of existing values which are allowed by the apache version
        new_route_statuses = self.get_statuses()
        for status_name in new_route_statuses.copy().keys(): # use copy to avoid a "dictionary was modified during iteration" error
            if status_name in self.get_immutable_statuses():
                new_route_statuses.pop(status_name)
            elif type(locals().get(status_name)) is bool:
                new_route_statuses[status_name] = locals().get(status_name)

        # except routes with errors from throwing the "last-route" error
        if self.status_error is True or self.status_disabled is True or self.status_draining_mode is True:
            pass
        elif self.cluster.eligible_routes <= 1:
            if new_route_statuses['status_disabled'] is True:
                raise BalancerManagerError('cannot enable the "disabled" status for the last available route (cluster: {cluster_name}, route: {route_name})'.format(cluster_name=self.cluster.name, route_name=self.name))
            elif new_route_statuses['status_draining_mode'] is True:
                raise BalancerManagerError('cannot enable the "draining mode" status for the last available route (cluster: {cluster_name}, route: {route_name})'.format(cluster_name=self.cluster.name, route_name=self.name))

        if self.cluster.client.apache_version_is('2.2.'):
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


class Client:

    def __init__(self, url, insecure=False, username=None, password=None, cache_ttl=60, timeout=30):

        self.logger = logging.getLogger(__name__)

        if type(insecure) is not bool:
            raise TypeError('insecure must be type bool')

        if insecure is True:
            self.logger.warning('ssl certificate verification is disabled')

        self.url = url
        self.timeout = timeout
        self.updated_datetime = None

        self.insecure = insecure
        self.apache_version = None
        self.request_exception = None

        self.clusters_ttl = cache_ttl
        self.clusters = list()

        self.session = requests.Session()
        self.session.headers.update({
            'User-agent': 'py_balancer_manager.Client'
        })

        if username and password:
            self.session.auth = (username, password)

        self.holistic_error_status = None

    def __iter__(self):

        yield ('updated_datetime', self.updated_datetime)
        yield ('url', self.url)
        yield ('insecure', self.insecure)
        yield ('apache_version', self.apache_version)
        yield ('request_exception', str(self.request_exception) if self.request_exception else None)
        yield ('holistic_error_status', self.holistic_error_status)
        yield ('clusters', [dict(c) for c in self.clusters] if self.clusters else None)

    def close(self):

        self.session.close()

    def request_get(self, **kwargs):

        kwargs['method'] = 'get'
        self.update(**kwargs)

    def request_post(self, **kwargs):

        kwargs['method'] = 'post'
        self.update(**kwargs)

    def update(self, **kwargs):

        self.logger.info('updating routes')

        if 'timeout' not in kwargs:
            kwargs['timeout'] = self.timeout
        if 'verify' not in kwargs:
            kwargs['verify'] = not self.insecure

        request_method = kwargs.pop('method', 'get')

        try:

            response = getattr(self.session, request_method)(self.url, **kwargs)

            if response.status_code is not requests.codes.ok:
                response.raise_for_status()
            else:
                self.request_exception = None

        except requests.exceptions.RequestException as e:

            self.request_exception = e
            raise BalancerManagerError(e)

        # update timestamp
        self.updated_datetime = now()
        # process text with beautiful soup
        bsoup = BeautifulSoup(response.text, 'lxml')
        # update routes
        self._parse(bsoup)
        # purge defunct clusters/routes
        self._purge_outdated()

    def apache_version_is(self, version):

        if self.apache_version:
            return self.apache_version.startswith(version)
        else:
            raise ApacheVersionError('no apache version has been set')

    def new_cluster(self):

        cluster = Cluster(self)
        self.clusters.append(cluster)
        return cluster

    def get_clusters(self, refresh=False):

        # if there are no clusters or refresh=True or cluster ttl is reached
        if self.updated_datetime is None or self.clusters is None or refresh is True or \
                (self.updated_datetime < (now() - timedelta(seconds=self.clusters_ttl))):
            self.update()

        return self.clusters

    def get_cluster(self, name, refresh=False):

        # find the cluster object for this route
        try:
            return find_object(self.get_clusters(refresh=refresh), 'name', name)
        except ResultsError:
            raise NotFound('could not locate cluster name in list of clusters: {}'.format(name))

    def get_routes(self, refresh=False):

        routes = []
        for cluster in self.get_clusters(refresh=refresh):
            routes += cluster.get_routes()
        return routes

    def _parse(self, bsoup):

        def _set_apache_version():

            try:
                full_version_string = bsoup.find('dt').text
            except AttributeError:
                raise BalancerManagerParseError('could not parse text from the first "dt" element')

            match = re.match(r'^Server\ Version:\ Apache/([\.0-9]*)', full_version_string)
            if match:
                self.apache_version = match.group(1)
                self.logger.info('apache version: {apache_version}'.format(apache_version=self.apache_version))
            else:
                raise BalancerManagerParseError('the content of the first "dt" element did not contain the version of Apache')

        def _parse_max_members(value):

            m = re.match(r'^(\d*) \[(\d*) Used\]$', value)
            if m:
                return(
                    int(m.group(1)),
                    int(m.group(2))
                )

            raise ValueError('MaxMembers value from Apache could not be parsed')

        def _get_cluster(name):

            try:
                return find_object(self.clusters, 'name', name)
            except ResultsError:
                return None

        def _get_route(cluster, name):

            try:
                return find_object(cluster.routes, 'name', name)
            except ResultsError:
                return None

        # remove form from page -- this contains extra tables which do not contain clusters or routes
        for form in bsoup.find_all('form'):
            form.extract()

        # check/set apache version
        if not self.apache_version:
            _set_apache_version()

        # compile patterns
        session_nonce_uuid_pattern = re.compile(r'.*&nonce=([-a-f0-9]{36}).*')
        cluster_name_pattern = re.compile(r'.*\?b=(.*?)&.*')

        # parse out tables
        _tables = bsoup.find_all('table')
        page_cluster_tables = _tables[::2]
        page_route_tables = _tables[1::2]

        # only iterate through odd tables which contain cluster data
        for table in page_cluster_tables:

            header_elements = table.findPreviousSiblings('h3', limit=1)
            if len(header_elements) == 1:
                header = header_elements[0]
            else:
                raise BalancerManagerParseError('single h3 element is required but not found')

            balancer_uri_pattern = re.compile('balancer://(.*)')
            header_text = header.a.text if header.a else header.text

            m = balancer_uri_pattern.search(header_text)
            if m:
                cluster_name = m.group(1)
            else:
                raise ValueError('cluster name could not be parsed from <h3> tag')

            # attempt to get cluster from list
            cluster = _get_cluster(cluster_name)

            # if cluster does not exist, create a new Cluster object for it
            if cluster is None:
                cluster = self.new_cluster()
                cluster.name = cluster_name

            for row in table.find_all('tr'):
                cells = row.find_all('td')

                if len(cells) == 0:
                    continue

                if self.apache_version_is('2.4.'):
                    cluster.max_members, cluster.max_members_used = _parse_max_members(cells[0].text)
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

            cluster.updated_datetime = now()

        # only iterate through even tables which contain route data
        for table in page_route_tables:
            for i, row in enumerate(table.find_all('tr')):
                cells = row.find_all('td')

                if len(cells) == 0:
                    continue

                route_name = cells[1].text
                worker_url = cells[0].find('a')['href']
                session_nonce_uuid = None

                if worker_url:
                    session_nonce_uuid_match = session_nonce_uuid_pattern.search(worker_url)
                    if session_nonce_uuid_match:
                        session_nonce_uuid = session_nonce_uuid_match.group(1)

                cluster_name_match = cluster_name_pattern.search(worker_url)

                if not cluster_name_match:
                    raise BalancerManagerError("could not determine route's cluster")

                cluster_name = cluster_name_match.group(1)

                # find the cluster object for this route
                cluster = _get_cluster(cluster_name)

                if cluster is None:
                    raise BalancerManagerError('could not locate cluster name in list of clusters: {name}'.format(name=cluster_name_match.group(1)))

                route = _get_route(cluster, route_name)

                # if cluster does not exist, create a new Cluster object for it
                if route is None:
                    route = cluster.new_route()
                    route.name = route_name

                if self.apache_version_is('2.4.'):
                    route.worker = cells[0].find('a').text
                    route.name = route_name
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
                    route.traffic_to_raw = Client._decode_data_useage(cells[9].text)
                    route.traffic_from = cells[10].text
                    route.traffic_from_raw = Client._decode_data_useage(cells[10].text)
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
                    route.traffic_to_raw = Client._decode_data_useage(cells[7].text)
                    route.traffic_from = cells[8].text
                    route.traffic_from_raw = Client._decode_data_useage(cells[8].text)
                    route.session_nonce_uuid = UUID(session_nonce_uuid)

                else:
                    raise ValueError('this module only supports apache 2.2 and 2.4')

                route.updated_datetime = now()

        # iterate clusters for post-parse processing
        for cluster in self.clusters:
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

        # set holistic_error_status
        self.holistic_error_status = False
        for cluster in self.clusters:
            if self.holistic_error_status is True:
                break
            for route in cluster.routes:
                if route.status_error is True:
                    self.holistic_error_status = True
                    break

    def _purge_outdated(self):

        for cluster in self.clusters:
            if self.updated_datetime > cluster.updated_datetime:
                self.logger.info('removing defunct cluster: {}'.format(cluster.name))
                self.clusters.remove(cluster)
                continue

            for route in cluster.routes:
                if self.updated_datetime > route.updated_datetime:
                    self.logger.info('removing defunct route: {}'.format(route.name))
                    cluster.routes.remove(route)

    @staticmethod
    def _decode_data_useage(value):

        value = value.strip()

        try:
            # match string from manager page to number + kilo/mega/giga/tera-byte
            match = re.match('([\d\.]*)([KMGT]?)', value)
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
            elif value == '0':
                return 0

        except Exception as e:
            logging.exception(e)

        return None
