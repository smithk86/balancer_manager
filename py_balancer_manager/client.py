import re
import time
import logging
import threading

import requests
from bs4 import BeautifulSoup

from .errors import BalancerManagerError


logger = logging.getLogger(__name__)


class ApacheVersionError(BalancerManagerError):

    def __init__(self, *args, **kwargs):
        super(ApacheVersionError, self).__init__(self, *args, **kwargs)


class Client:

    def __init__(self, url, verify_ssl_cert=True, username=None, password=None, cache_ttl=5):

        if verify_ssl_cert is False:
            logger.warn('ssl certificate verification is disabled')

        self.url = url
        self.verify_ssl_cert = verify_ssl_cert
        self.auth_username = username
        self.auth_password = password
        self.apache_version = None
        self.request_exception = None

        self.cache_ttl = cache_ttl
        self.cache_routes = None
        self.cache_routes_time = 0

        self.session = requests.Session()
        self.session.headers.update({
            'User-agent': 'py_balancer_manager.Client'
        })

        if self.auth_username and self.auth_password:
            self.session.auth = (self.auth_username, self.auth_password)

    def _request_session_get(self, *args, **kwargs):

        kwargs['method'] = 'get'
        return self._request_session(*args, **kwargs)

    def _request_session_post(self, *args, **kwargs):

        kwargs['method'] = 'post'
        return self._request_session(*args, **kwargs)

    def _request_session(self, *args, **kwargs):

        request_method = kwargs.pop('method', 'get')

        response = None

        try:

            response = getattr(self.session, request_method)(*args, **kwargs)

            if response.status_code is not requests.codes.ok:

                response.raise_for_status()

        except requests.exceptions.RequestException as e:

            self.request_exception = e
            raise

        return response

    def set_apache_version(self):

        if self.apache_version:
            # do not re-poll if self.apache_version is already set
            return True

        page = self._get_soup_html()

        full_version_string = page.find('dt').string
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

    def _get_soup_html(self):

        req = self._request_session_get(self.url, verify=self.verify_ssl_cert)

        if req.status_code is not requests.codes.ok:
            req.raise_for_status()

        return BeautifulSoup(req.text, 'html.parser')

    def _get_empty_route_dictionary(self):
        return {
            'url': None,
            'route': None,
            'route_redir': None,
            'factor': None,
            'set': None,
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
            'apache_manager_url': self.url,
            'apache_version': self.apache_version
        }

    def get_routes(self, cluster=None, use_cache=True):

        self.set_apache_version()

        now = time.time()

        if self.cache_routes is None or self.cache_routes_time < (now - self.cache_ttl):
            self.cache_routes = self._get_routes_from_apache()
            self.cache_routes_time = now

        if cluster:
            routes = []
            for route in self.cache_routes:
                if route['cluster'] == cluster:
                    routes.append(route)
            return routes
        else:
            return self.cache_routes

    def get_route(self, cluster, name, use_cache=True):

        for route in self.get_routes(cluster=cluster, use_cache=use_cache):
            if route['route'] == name:
                return route

        return None

    def get_validation_properties(self):

        if self.apache_version_is('2.2.'):

            return [
                'status_disabled',
                'status_hot_standby'
            ]

        elif self.apache_version_is('2.4.'):

            return [
                'status_ignore_errors',
                'status_draining_mode',
                'status_disabled',
                'status_hot_standby'
            ]

        else:

            return []

    def _get_routes_from_apache(self):

        page = self._get_soup_html()
        session_nonce_uuid_pattern = re.compile(r'.*&nonce=([-a-f0-9]{36}).*')
        cluster_name_pattern = re.compile(r'.*\?b=(.*?)&.*')

        routes = []
        tables = page.find_all('table')

        # only iterate through even tables
        # odd tables contain data about the cluster itself
        for table in tables[1::2]:
            for row in table.find_all('tr'):
                route = row.find_all('td')
                if len(route) > 0:
                    cells = row.find_all('td')
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
                        route_dict['url'] = cells[0].find('a').string
                        route_dict['route'] = cells[1].string
                        route_dict['route_redir'] = cells[2].string
                        route_dict['factor'] = cells[3].string
                        route_dict['set'] = cells[4].string
                        route_dict['status_ok'] = 'Ok' in cells[5].string
                        route_dict['status_error'] = 'Err' in cells[5].string
                        route_dict['status_ignore_errors'] = 'Ign' in cells[5].string
                        route_dict['status_draining_mode'] = 'Drn' in cells[5].string
                        route_dict['status_disabled'] = 'Dis' in cells[5].string
                        route_dict['status_hot_standby'] = 'Stby' in cells[5].string
                        route_dict['elected'] = cells[6].string
                        route_dict['busy'] = cells[7].string
                        route_dict['load'] = cells[8].string
                        route_dict['to'] = cells[9].string
                        route_dict['from'] = cells[10].string
                        route_dict['session_nonce_uuid'] = session_nonce_uuid
                        route_dict['cluster'] = cluster_name

                    elif self.apache_version_is('2.2.'):
                        route_dict['url'] = cells[0].find('a').string
                        route_dict['route'] = cells[1].string
                        route_dict['route_redir'] = cells[2].string
                        route_dict['factor'] = cells[3].string
                        route_dict['set'] = cells[4].string
                        route_dict['status_ok'] = 'Ok' in cells[5].string
                        route_dict['status_error'] = 'Err' in cells[5].string
                        route_dict['status_ignore_errors'] = None
                        route_dict['status_draining_mode'] = None
                        route_dict['status_disabled'] = 'Dis' in cells[5].string
                        route_dict['status_hot_standby'] = 'Stby' in cells[5].string
                        route_dict['elected'] = cells[6].string
                        route_dict['busy'] = None
                        route_dict['load'] = None
                        route_dict['to'] = cells[7].string
                        route_dict['from'] = cells[8].string
                        route_dict['session_nonce_uuid'] = session_nonce_uuid
                        route_dict['cluster'] = cluster_name

                    else:
                        raise ValueError('this module only supports apache 2.2 and 2.4')

                    routes.append(route_dict)

        return routes

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
                'w': route['url'],
                'b': route['cluster'],
                'nonce': route['session_nonce_uuid']
            }
            self._request_session_post(self.url, data=post_data, verify=self.verify_ssl_cert)

        elif self.apache_version_is('2.2.'):
            get_data = {
                'lf': '1',
                'ls': '0',
                'wr': route['route'],
                'rr': '',
                'dw': 'Disable' if route['status_disabled'] else 'Enable',
                'w': route['url'],
                'b': route['cluster'],
                'nonce': route['session_nonce_uuid']
            }
            self._request_session_get(self.url, params=get_data, verify=self.verify_ssl_cert)

        else:
            raise ValueError('this module only supports apache 2.2 and 2.4')


class ClientThread(threading.Thread):

    def __init__(self, client):
        threading.Thread.__init__(self)

        if type(client) is not Client:
            raise TypeError('first argument must be of type py_balancer_manager.Client')

        self.client = client
        self.routes = None

    def run(self):

        self.routes = self.client.get_routes()


class ClientAggregator:

    def __init__(self):
        self.clients = {}

    def add_client(self, client, client_id=None):

        if type(client) is Client:

            if client_id:
                self.clients.client_id = client_id

            self.clients.append(client)

    def get_servers(self):

        servers = []
        threads = []

        for client in self.clients:
            threads.append(ClientThread(client))

        for thread in threads:
            thread.start()

        for thread in threads:
            thread.join()

        for thread in threads:
            servers.append(thread.routes)

        return servers
