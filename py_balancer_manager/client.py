import re
import time
import logging
from collections import OrderedDict

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

    def close(self):

        self.session.close()

    def _request_session_get(self, *args, **kwargs):

        kwargs['method'] = 'get'
        return self._request_session(*args, **kwargs)

    def _request_session_post(self, *args, **kwargs):

        kwargs['method'] = 'post'
        return self._request_session(*args, **kwargs)

    def _request_session(self, *args, **kwargs):

        if 'timeout' not in kwargs:
            kwargs['timeout'] = self.timeout

        request_method = kwargs.pop('method', 'get')

        response = None

        try:

            response = getattr(self.session, request_method)(*args, **kwargs)

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

        self._request_session_get(self.url, verify=not self.insecure)

    def _get_soup_html(self):

        req = self._request_session_get(self.url, verify=not self.insecure)

        if req.status_code is not requests.codes.ok:
            req.raise_for_status()

        return BeautifulSoup(req.text, 'html.parser')

    def _get_empty_cluster_dictionary(self):

        return {
            'max_members': None,
            'max_members_used': None,
            'sticky_session': None,
            'disable_failover': None,
            'timeout': None,
            'failover_attempts': None,
            'method': None,
            'path': None,
            'active': None,
            'routes': list()
        }

    def _get_empty_route_dictionary(self):

        return {
            'worker': None,
            'route': None,
            'priority': -1,
            'route_redir': None,
            'factor': None,
            'set': None,
            'active': None,
            'status_ok': None,
            'status_error': None,
            'status_ignore_errors': None,
            'status_draining_mode': None,
            'status_disabled': None,
            'status_hot_standby': None,
            'elected': None,
            'busy': None,
            'load': None,
            'to': None,
            'from': None,
            'session_nonce_uuid': None,
            'cluster': None,
            'url': self.url
        }

    def get_clusters(self, cluster=None, use_cache=True):

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

        if cluster:
            if cluster in self.cache_clusters:
                return {
                    cluster: self.cache_clusters[cluster]
                }
            else:
                raise KeyError('cluster does not exist: {cluster}'.format(**locals()))
        else:
            return self.cache_clusters

    def get_routes(self, cluster=None, use_cache=True):

        routes = list()
        clusters = self.get_clusters(cluster=cluster, use_cache=use_cache)

        for cluster in clusters.values():
            routes += cluster['routes']

        return routes

    def get_route(self, cluster, name, use_cache=True):

        for route in self.get_routes(cluster=cluster, use_cache=use_cache):
            if route['route'] == name:
                return route

        return None

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

        clusters = OrderedDict()

        # only iterate through odd tables which contain cluster data
        for table in page_cluster_tables:

            cluster = self._get_empty_cluster_dictionary()
            cluster_name = None

            header = table.findPreviousSiblings('h3', limit=1)[0]
            balancer_uri_pattern = re.compile('balancer://(.*)')
            header_text = header.a.text if header.a else header.text
            m = balancer_uri_pattern.search(header_text)
            if m:
                cluster_name = m.group(1)
            else:
                raise ValueError('cluster name could not be parsed from <h3> tag')

            if cluster_name in clusters:
                continue

            for row in table.find_all('tr'):
                cells = row.find_all('td')

                if len(cells) == 0:
                    continue

                if self.apache_version_is('2.4.'):
                    cluster['max_members'], cluster['max_members_used'] = parse_max_members(cells[0].text)
                    # below is a workaround for a bug in the html formatting in apache 2.4.20 in which the StickySession cell closing tag comes after DisableFailover
                    # HTML = <td>JSESSIONID<td>Off</td></td>
                    cluster['sticky_session'] = cells[1].find(text=True, recursive=False).strip()
                    cluster['disable_failover'] = 'On' in cells[2].text
                    cluster['timeout'] = int(cells[3].text)
                    cluster['failover_attempts'] = int(cells[4].text)
                    cluster['method'] = cells[5].text
                    cluster['path'] = cells[6].text
                    cluster['active'] = 'Yes' in cells[7].text

                elif self.apache_version_is('2.2.'):
                    cluster['sticky_session'] = cells[0].text
                    cluster['timeout'] = int(cells[1].text)
                    cluster['failover_attempts'] = int(cells[2].text)
                    cluster['method'] = cells[3].text

            clusters[cluster_name] = cluster

        # only iterate through even tables which contain route data
        for table in page_route_tables:
            for i, row in enumerate(table.find_all('tr')):
                cells = row.find_all('td')

                if len(cells) == 0:
                    continue

                worker_url = cells[0].find('a')['href']
                session_nonce_uuid = None
                cluster_name = None

                if worker_url:

                    session_nonce_uuid_match = session_nonce_uuid_pattern.search(worker_url)
                    if session_nonce_uuid_match:
                        session_nonce_uuid = session_nonce_uuid_match.group(1)

                    cluster_name_match = cluster_name_pattern.search(worker_url)
                    if cluster_name_match:
                        cluster_name = cluster_name_match.group(1)

                route_dict = self._get_empty_route_dictionary()

                if self.apache_version_is('2.4.'):
                    route_dict['worker'] = cells[0].find('a').text
                    route_dict['route'] = cells[1].text
                    route_dict['priority'] = i
                    route_dict['route_redir'] = cells[2].text
                    route_dict['factor'] = int(cells[3].text)
                    route_dict['set'] = int(cells[4].text)
                    route_dict['status_ok'] = 'Ok' in cells[5].text
                    route_dict['status_error'] = 'Err' in cells[5].text
                    route_dict['status_ignore_errors'] = 'Ign' in cells[5].text
                    route_dict['status_draining_mode'] = 'Drn' in cells[5].text
                    route_dict['status_disabled'] = 'Dis' in cells[5].text
                    route_dict['status_hot_standby'] = 'Stby' in cells[5].text
                    route_dict['elected'] = int(cells[6].text)
                    route_dict['busy'] = int(cells[7].text)
                    route_dict['load'] = int(cells[8].text)
                    route_dict['to'] = cells[9].text
                    route_dict['to_raw'] = _decode_data_useage(cells[9].text)
                    route_dict['from'] = cells[10].text
                    route_dict['from_raw'] = _decode_data_useage(cells[10].text)
                    route_dict['session_nonce_uuid'] = session_nonce_uuid
                    route_dict['cluster'] = cluster_name

                elif self.apache_version_is('2.2.'):
                    route_dict['worker'] = cells[0].find('a').text
                    route_dict['route'] = cells[1].text
                    route_dict['priority'] = i
                    route_dict['route_redir'] = cells[2].text
                    route_dict['factor'] = int(cells[3].text)
                    route_dict['set'] = int(cells[4].text)
                    route_dict['status_ok'] = 'Ok' in cells[5].text
                    route_dict['status_error'] = 'Err' in cells[5].text
                    route_dict['status_ignore_errors'] = None
                    route_dict['status_draining_mode'] = None
                    route_dict['status_disabled'] = 'Dis' in cells[5].text
                    route_dict['status_hot_standby'] = 'Stby' in cells[5].text
                    route_dict['elected'] = int(cells[6].text)
                    route_dict['busy'] = None
                    route_dict['load'] = None
                    route_dict['to'] = cells[7].text
                    route_dict['to_raw'] = _decode_data_useage(cells[7].text)
                    route_dict['from'] = cells[8].text
                    route_dict['from_raw'] = _decode_data_useage(cells[8].text)
                    route_dict['session_nonce_uuid'] = session_nonce_uuid
                    route_dict['cluster'] = cluster_name

                else:
                    raise ValueError('this module only supports apache 2.2 and 2.4')

                if route_dict['cluster'] not in clusters:
                    clusters[route_dict['cluster']] = {'routes': list()}

                clusters[route_dict['cluster']]['routes'].append(route_dict)

        return clusters

    def change_route_status(self, route, status_ignore_errors=None, status_draining_mode=None, status_disabled=None, status_hot_standby=None):

        if self.apache_version_is('2.2.'):
            if status_ignore_errors is not None:
                raise ApacheVersionError('status_ignore_errors is not supported in apache 2.2')
            if status_draining_mode is not None:
                raise ApacheVersionError('status_draining_mode is not supported in apache 2.2')
            if status_hot_standby is not None:
                raise ApacheVersionError('status_hot_standby is not supported in apache 2.2')

        if type(status_ignore_errors) is bool:
            route['status_ignore_errors'] = status_ignore_errors
        if type(status_draining_mode) is bool:
            route['status_draining_mode'] = status_draining_mode
        if type(status_disabled) is bool:
            route['status_disabled'] = status_disabled
        if type(status_hot_standby) is bool:
            route['status_hot_standby'] = status_hot_standby

        if self.apache_version_is('2.4.'):
            post_data = {
                'w_lf': '1',
                'w_ls': '0',
                'w_wr': route['route'],
                'w_rr': '',
                'w_status_I': int(route['status_ignore_errors']),
                'w_status_N': int(route['status_draining_mode']),
                'w_status_D': int(route['status_disabled']),
                'w_status_H': int(route['status_hot_standby']),
                'w': route['worker'],
                'b': route['cluster'],
                'nonce': route['session_nonce_uuid']
            }
            self._request_session_post(self.url, data=post_data, verify=not self.insecure)

        elif self.apache_version_is('2.2.'):
            get_data = {
                'lf': '1',
                'ls': '0',
                'wr': route['route'],
                'rr': '',
                'dw': 'Disable' if route['status_disabled'] else 'Enable',
                'w': route['worker'],
                'b': route['cluster'],
                'nonce': route['session_nonce_uuid']
            }
            self._request_session_get(self.url, params=get_data, verify=not self.insecure)

        else:
            raise ValueError('this module only supports apache 2.2 and 2.4')

        # expire cache to force refresh
        self.expire_route_cache()
