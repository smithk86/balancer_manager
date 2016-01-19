import re
import logging
import threading

import requests
from bs4 import BeautifulSoup


""" balancer_manager.py: Library for programatically interacting with Apache's mod_proxy_balancer management interface """

__author__ = "Kyle Smith"
__email__ = "smithk86@gmail.com"
__license__ = "GPL"
__version__ = "1.0.1"

logger = logging.getLogger(__name__)


class ApacheBalancerManager:

    def __init__(self, url, verify_ssl_cert=True, username=None, password=None):

        if verify_ssl_cert is False:
            logger.warn('ssl certificate verification is disabled')

        self.url = url
        self.verify_ssl_cert = verify_ssl_cert
        self.auth_username = username
        self.auth_password = password
        self.apache_version = None

        self.session = requests.Session()
        self.session.headers.update({'User-agent': 'balancer_manager.py/{version}'.format(version=__version__)})
        if self.auth_username and self.auth_password:
            self.session.auth = (self.auth_username, self.auth_password)

        page = self._get_soup_html()
        full_version_string = page.find('dt').string
        match = re.match(r'^Server\ Version:\ Apache/([\.0-9]*)', full_version_string)
        if match:
            self.apache_version = match.group(1)

        if self.apache_version is None:
            raise TypeError('apache version parse failed')

        logger.info('apache version: {apache_version}'.format(apache_version=self.apache_version))

    def _get_soup_html(self):

        if self.url.find('/') >= 0:
            url = self.url
        else:
            url = 'http://{url}/balancer-manager'.format(url=self.url)

        req = self.session.get(url, verify=self.verify_ssl_cert)

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
            'status_init': None,
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

    def get_routes(self):
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

                    if self.apache_version[0:4] == '2.4.':
                        route_dict['url'] = cells[0].find('a').string
                        route_dict['route'] = cells[1].string
                        route_dict['route_redir'] = cells[2].string
                        route_dict['factor'] = cells[3].string
                        route_dict['set'] = cells[4].string
                        route_dict['status_init'] = 'Init' in cells[5].string
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

                    elif self.apache_version[0:4] == '2.2.':
                        route_dict['url'] = cells[0].find('a').string
                        route_dict['route'] = cells[1].string
                        route_dict['route_redir'] = cells[2].string
                        route_dict['factor'] = cells[3].string
                        route_dict['set'] = cells[4].string
                        route_dict['status_init'] = 'Ok' in cells[5].string
                        route_dict['status_ignore_errors'] = 'n/a'
                        route_dict['status_draining_mode'] = 'n/a'
                        route_dict['status_disabled'] = 'Dis' in cells[5].string
                        route_dict['status_hot_standby'] = 'Stby' in cells[5].string
                        route_dict['elected'] = cells[6].string
                        route_dict['busy'] = 'n/a'
                        route_dict['load'] = 'n/a'
                        route_dict['to'] = cells[7].string
                        route_dict['from'] = cells[8].string
                        route_dict['session_nonce_uuid'] = session_nonce_uuid
                        route_dict['cluster'] = cluster_name

                    else:
                        raise ValueError('this module only supports apache 2.2 and 2.4')

                    routes.append(route_dict)

        return routes

    def change_route_status(self, route, status_ignore_errors=None, status_draining_mode=None, status_disabled=None, status_hot_standby=None):

        if type(status_ignore_errors) is bool:
            route['status_ignore_errors'] = status_ignore_errors
        if type(status_draining_mode) is bool:
            route['status_draining_mode'] = status_draining_mode
        if type(status_disabled) is bool:
            route['status_disabled'] = status_disabled
        if type(status_hot_standby) is bool:
            route['status_hot_standby'] = status_hot_standby

        if self.apache_version[0:4] == '2.4.':
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
            self.session.post(self.url, data=post_data, verify=self.verify_ssl_cert)

        elif self.apache_version[0:4] == '2.2.':
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
            self.session.get(self.url, params=get_data, verify=self.verify_ssl_cert)

        else:
            raise ValueError('this module only supports apache 2.2 and 2.4')


class ApacheBalancerManagerPollThread(threading.Thread):

    def __init__(self, url, **kwargs):
        threading.Thread.__init__(self)

        self.url = url
        self.kwargs = kwargs
        self.routes = None

    def run(self):

        abm = ApacheBalancerManager(self.url, **self.kwargs)
        self.routes = abm.get_routes()
