import re
import logging
from uuid import UUID
from datetime import datetime, timedelta

import requests
from bs4 import BeautifulSoup

from .cluster import Cluster
from .errors import BalancerManagerError, ResultsError, NotFound
from .helpers import now, parse_from_local_timezone, find_object


class BalancerManagerParseError(BalancerManagerError):
    pass


class Client(object):
    def __init__(self, url, insecure=False, username=None, password=None, cache_ttl=60, timeout=30):
        self.logger = logging.getLogger(__name__)

        if type(insecure) is not bool:
            raise TypeError('insecure must be type bool')

        if insecure is True:
            self.logger.warning('ssl certificate verification is disabled')

        self.url = url
        self.last_response = None
        self.timeout = timeout
        self.updated_datetime = None

        self.insecure = insecure
        self.httpd_version = None
        self.httpd_compile_datetime = None
        self.openssl_version = None
        self.error = None

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
        yield ('httpd_version', self.httpd_version)
        yield ('httpd_compile_datetime', self.httpd_compile_datetime)
        yield ('openssl_version', self.openssl_version)
        yield ('error', str(self.error) if self.error else None)
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

    def update(self, method='get', timeout=None, verify=None, **kwargs):

        self.logger.info('updating routes')

        timeout = timeout if timeout else self.timeout
        verify = verify if verify else not self.insecure

        try:

            self.last_response = getattr(self.session, method)(self.url, timeout=timeout, verify=verify, **kwargs)

            if self.last_response.status_code is not requests.codes.ok:
                self.last_response.raise_for_status()
            else:
                self.error = None

        except requests.exceptions.RequestException as e:

            self.error = e
            raise BalancerManagerError(e)

        # update timestamp
        self.updated_datetime = now()
        # process text with beautiful soup
        bsoup = BeautifulSoup(self.last_response.text, 'html.parser')
        # update routes
        self._parse(bsoup)
        # purge defunct clusters/routes
        self._purge_outdated()

    def httpd_version_is(self, version):

        if self.httpd_version:
            return self.httpd_version.startswith(version)
        else:
            raise HttpdVersionError('no httpd version has been set')

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

        def _parse_max_members(value):

            m = re.match(r'^(\d*) \[(\d*) Used\]$', value)
            if m:
                return(
                    int(m.group(1)),
                    int(m.group(2))
                )

            raise ValueError('MaxMembers value from httpd could not be parsed')

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

        # compile patterns
        session_nonce_uuid_pattern = re.compile(r'.*&nonce=([-a-f0-9]{36}).*')
        cluster_name_pattern = re.compile(r'.*\?b=(.*?)&.*')
        balancer_uri_pattern = re.compile('balancer://(.*)')

        # remove form from page -- this contains extra tables which do not contain clusters or routes
        for form in bsoup.find_all('form'):
            form.extract()

        # initial bs4 parsing
        _bs_dt = bsoup.find_all('dt')
        _bs_tables = bsoup.find_all('table')
        _bs_table_clusters = _bs_tables[::2]
        _bs_table_routes = _bs_tables[1::2]

        if len(_bs_dt) >= 1:

            # set/update httpd version
            match = re.match(r'^Server\ Version:\ Apache/([\.0-9]*)', _bs_dt[0].text)
            if match:
                self.httpd_version = match.group(1)
            else:
                raise BalancerManagerParseError('the content of the first "dt" element did not contain the version of httpd')

            # set/update openssl version
            match = re.search(r'OpenSSL\/([0-9\.a-z]*)', _bs_dt[0].text)
            if match:
                self.openssl_version = match.group(1)

        else:
            raise BalancerManagerParseError('could not parse text from the first "dt" element')

        if len(_bs_dt) >= 2:

            # set/update httpd compile datetime
            match = re.match(r'Server Built:\ (.*)', _bs_dt[1].text)
            if match:
                self.httpd_compile_datetime = parse_from_local_timezone(match.group(1))

        # only iterate through odd tables which contain cluster data
        for table in _bs_table_clusters:

            header_elements = table.findPreviousSiblings('h3', limit=1)
            if len(header_elements) == 1:
                header = header_elements[0]
            else:
                raise BalancerManagerParseError('single h3 element is required but not found')

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

                if self.httpd_version_is('2.4.'):
                    cluster.max_members, cluster.max_members_used = _parse_max_members(cells[0].text)
                    # below is a workaround for a bug in the html formatting in httpd 2.4.20 in which the StickySession cell closing tag comes after DisableFailover
                    # HTML = <td>JSESSIONID<td>Off</td></td>
                    sticky_session_value = cells[1].find(text=True, recursive=False).strip()
                    cluster.sticky_session = False if sticky_session_value == '(None)' else sticky_session_value
                    cluster.disable_failover = 'On' in cells[2].text
                    cluster.timeout = int(cells[3].text)
                    cluster.failover_attempts = int(cells[4].text)
                    cluster.method = cells[5].text
                    cluster.path = cells[6].text
                    cluster.active = 'Yes' in cells[7].text

                elif self.httpd_version_is('2.2.'):
                    cluster.sticky_session = False if cells[0].text == '(None)' else cells[0].text
                    cluster.timeout = int(cells[1].text)
                    cluster.failover_attempts = int(cells[2].text)
                    cluster.method = cells[3].text

            cluster.updated_datetime = now()

        # only iterate through even tables which contain route data
        for table in _bs_table_routes:
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

                if self.httpd_version_is('2.4.'):
                    route.worker = cells[0].find('a').text
                    route.name = route_name
                    route.priority = i
                    route.route_redir = cells[2].text
                    route.factor = float(cells[3].text)
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

                elif self.httpd_version_is('2.2.'):
                    route.worker = cells[0].find('a').text
                    route.name = cells[1].text
                    route.priority = i
                    route.route_redir = cells[2].text
                    route.factor = float(cells[3].text)
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
                    raise ValueError('this module only supports httpd 2.2 and 2.4')

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
            if cluster.updated_datetime is None or self.updated_datetime > cluster.updated_datetime:
                self.logger.info('removing defunct cluster: {}'.format(cluster.name))
                self.clusters.remove(cluster)
                continue

            for route in cluster.routes:
                if route.updated_datetime is None or self.updated_datetime > route.updated_datetime:
                    self.logger.info('removing defunct route: {}'.format(route.name))
                    cluster.routes.remove(route)

    @staticmethod
    def _decode_data_useage(value):

        value = value.strip()

        try:
            # match string from manager page to number + kilo/mega/giga/tera-byte
            match = re.match(r'([[0-9]\d\.]*)([KMGT]?)', value)
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
