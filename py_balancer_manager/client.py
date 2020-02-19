import asyncio
import logging
import re
from collections import namedtuple
from datetime import datetime, timedelta
from uuid import UUID

import httpx
from bs4 import BeautifulSoup
from packaging import version

from .cluster import Cluster
from .errors import BalancerManagerError
from .helpers import now, parse_from_local_timezone, find_object, VERSION_24
from .route import Route
from .status import Statuses, Status


class BalancerData(object):
    def __init__(self, client):
        self.client = client
        self.updated_datetime = None
        self.httpd_version = None
        self.httpd_compile_datetime = None
        self.openssl_version = None
        self.clusters = list()

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
            await self.client.data(data=self)
        else:
            self.client._parse(response_payload, data=self)


class Client(object):
    # compile patterns
    httpd_server_version_pattern = re.compile(r'^Server\ Version:\ Apache/([\.0-9]*)')
    httpd_server_build_date_pattern = re.compile(r'Server Built:\ (.*)')
    openssl_version_pattern = re.compile(r'OpenSSL\/([0-9\.a-z]*)')
    session_nonce_uuid_pattern = re.compile(r'.*&nonce=([-a-f0-9]{36}).*')
    cluster_name_pattern = re.compile(r'.*\?b=(.*?)&.*')
    balancer_uri_pattern = re.compile('balancer://(.*)')
    route_used_pattern = re.compile(r'^(\d*) \[(\d*) Used\]$')
    route_data_used_pattern = re.compile(r'([0-9\d\.]*)([KMGT]?)')

    def __init__(self, url, insecure=False, username=None, password=None, cache_ttl=60, timeout=30):
        self.logger = logging.getLogger(__name__)

        if type(insecure) is not bool:
            raise TypeError('insecure must be type bool')

        if insecure is True:
            self.logger.warning('ssl certificate verification is disabled')

        self.url = url
        self.insecure = insecure
        self.timeout = timeout
        self.user_agent = 'py-balancer-manager.Client'
        self.http_auth = httpx.BasicAuth(username, password=password) if (username and password) else None

    def __repr__(self):
        return f'<py_balancer_manager.Client object: {self.url}>'

    def asdict(self):
        return {
            'updated_datetime': self.updated_datetime,
            'url': self.url,
            'insecure': self.insecure,
            'httpd_version': self.httpd_version,
            'httpd_compile_datetime': self.httpd_compile_datetime,
            'openssl_version': self.openssl_version,
            'holistic_error_status': self.holistic_error_status,
            'clusters': [c.asdict() for c in self.clusters] if self.clusters else None
        }

    def _http_client(self):
        return httpx.AsyncClient(
            auth=self.http_auth,
            timeout=self.timeout,
            headers={
                'User-Agent': self.user_agent
            }
        )

    async def data(self, data=None):
        async with self._http_client() as client:
            r = await client.get(self.url)
            response_payload = r.text
        # update routes
        return Client._parse(self, response_payload, data=data)

    def _parse(self, response_payload, data=None):
        def _parse_max_members(value):
            m = Client.route_used_pattern.match(value)
            if m:
                return(
                    int(m.group(1)),
                    int(m.group(2))
                )
            raise ValueError('MaxMembers value from httpd could not be parsed')

        # parse payload with beautiful soup
        bsoup = BeautifulSoup(response_payload, 'html.parser')

        # init the data container
        if data is None:
            data = BalancerData(self)

        data.updated_datetime = now()

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
            match = Client.httpd_server_version_pattern.match(_bs_dt[0].text)
            if match:
                data.httpd_version = version.parse(match.group(1))
            else:
                raise BalancerManagerError('the content of the first "dt" element did not contain the version of httpd')

            if data.httpd_version < VERSION_24:
                raise BalancerManagerError('apache httpd versions less than 2.4 are not supported')

            # set/update openssl version
            match = Client.openssl_version_pattern.search(_bs_dt[0].text)
            if match:
                data.openssl_version = version.parse(match.group(1))
        else:
            raise BalancerManagerError('could not parse text from the first "dt" element')

        if len(_bs_dt) >= 2:
            # set/update httpd compile datetime
            match = Client.httpd_server_build_date_pattern.match(_bs_dt[1].text)
            if match:
                data.httpd_compile_datetime = parse_from_local_timezone(match.group(1))

        # only iterate through odd tables which contain cluster data
        for table in _bs_table_clusters:
            header_elements = table.findPreviousSiblings('h3', limit=1)
            if len(header_elements) == 1:
                header = header_elements[0]
            else:
                raise BalancerManagerError('single h3 element is required but not found')

            header_text = header.a.text if header.a else header.text

            m = Client.balancer_uri_pattern.search(header_text)
            if m:
                cluster_name = m.group(1)
            else:
                raise ValueError('cluster name could not be parsed from <h3> tag')

            try:
                cluster = data.cluster(cluster_name)
            except BalancerManagerError:
                cluster = data.new_cluster(cluster_name)

            for row in table.find_all('tr'):
                cells = row.find_all('td')

                if len(cells) == 0:
                    continue

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
                    session_nonce_uuid_match = Client.session_nonce_uuid_pattern.search(worker_url)
                    if session_nonce_uuid_match:
                        session_nonce_uuid = session_nonce_uuid_match.group(1)

                cluster_name_match = Client.cluster_name_pattern.search(worker_url)

                if not cluster_name_match:
                    raise BalancerManagerError("could not determine route's cluster")

                cluster_name = cluster_name_match.group(1)
                cluster = data.cluster(cluster_name)

                try:
                    route = cluster.route(route_name)
                except BalancerManagerError:
                    route = cluster.new_route(route_name)

                route.worker = cells[0].find('a').text
                route.priority = i
                route.route_redir = cells[2].text
                route.factor = float(cells[3].text)
                route.lbset = int(cells[4].text)
                route.elected = int(cells[6].text)
                route.busy = int(cells[7].text)
                route.load = int(cells[8].text)
                route.traffic_to = cells[9].text
                route.traffic_to_raw = Client._decode_data_usage(cells[9].text)
                route.traffic_from = cells[10].text
                route.traffic_from_raw = Client._decode_data_usage(cells[10].text)
                route.session_nonce_uuid = UUID(session_nonce_uuid)
                route._status = Statuses(
                    ok=Status(value='Ok' in cells[5].text, immutable=True, http_form_code=None),
                    error=Status(value='Err' in cells[5].text, immutable=True, http_form_code=None),
                    ignore_errors=Status(value='Ign' in cells[5].text, immutable=False, http_form_code='I'),
                    draining_mode=Status(value='Drn' in cells[5].text, immutable=False, http_form_code='N'),
                    disabled=Status(value='Dis' in cells[5].text, immutable=False, http_form_code='D'),
                    hot_standby=Status(value='Stby' in cells[5].text, immutable=False, http_form_code='H'),
                    hot_spare=Status(value='Spar' in cells[5].text, immutable=False, http_form_code='R') if data.httpd_version >= version.parse('2.4.34') else None,
                    stopped=Status(value='Stop' in cells[5].text, immutable=False, http_form_code='S') if data.httpd_version >= version.parse('2.4.23') else None
                )

        # iterate clusters for post-parse processing
        for cluster in data.clusters:
            # determine if standby routes are active for cluster
            cluster.standby_activated = True
            for route in cluster.routes:
                if route._status.ok.value and route._status.hot_standby.value is False:
                    cluster.standby_activated = False
                    break
            # determine if the route is actively taking taffic
            for route in cluster.routes:
                route.taking_traffic = (route._status.error.value is False and route._status.disabled.value is False and (route._status.draining_mode is None or route._status.draining_mode.value is False) and (route._status.hot_standby.value is False or cluster.standby_activated is True))
            # calculate the number of routes which are eligible to take traffic
            cluster.eligible_routes = 0
            for route in cluster.routes:
                if route._status.error.value is False and route._status.disabled.value is False and (route._status.draining_mode is None or route._status.draining_mode.value is not True):
                    cluster.eligible_routes += 1

        return data

    @staticmethod
    def _decode_data_usage(value):
        value = value.strip()
        try:
            # match string from manager page to number + kilo/mega/giga/tera-byte
            match = Client.route_data_used_pattern.match(value)
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
