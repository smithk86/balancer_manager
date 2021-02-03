import logging
import re

import httpx

from .errors import BalancerManagerError


logger = logging.getLogger(__name__)


class Client(httpx.AsyncClient):
    url_endpoint_pattern = re.compile(r'(.*)\/balancer-manager')

    def __init__(self, url: str, username=None, password=None, insecure=False, **kwargs):
        self.url = url

        # setup auth
        kwargs['auth'] = httpx.BasicAuth(username, password=password) if (username and password) else None

        if 'headers' not in kwargs:
            kwargs['headers'] = {}

        kwargs['headers'].update({
            'User-Agent': 'py-balancer-manager.Client'
        })

        if kwargs.get('verify') is False or insecure is True:
            kwargs['verify'] = False
            logger.warning('ssl certificate verification is disabled')

        super().__init__(**kwargs)

    def generate_referer_headers(self, referer_params):
        headers = {}

        m = Client.url_endpoint_pattern.match(self.url)
        if m:
            headers['Origin'] = m.group(1)

        referer_dict = referer_params._asdict()
        referer_pairs = [f'{key}={value}' for key, value in referer_dict.items()]
        headers['Referer'] = f"{self.url}?{'&'.join(referer_pairs)}"

        return headers

    @property
    def ssl_context(self):
        return self._transport._ssl_context

    async def get(self):
        try:
            return await super().get(self.url)
        except httpx._exceptions.HTTPError:
            raise BalancerManagerError(f'http call to apache failed [url={self.url}]')

    async def post(self, data, referer_params): 
        try:
            return await super().post(self.url, headers=self.generate_referer_headers(referer_params), data=data)
        except httpx._exceptions.HTTPError:
            raise BalancerManagerError(f'http call to apache failed [url={self.url}]')
