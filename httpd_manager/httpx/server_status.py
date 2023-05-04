import asyncio
from functools import partial

from pydantic import HttpUrl, PrivateAttr

from .client import http_client
from ..executor import executor
from ..base import ServerStatus


class HttpxServerStatus(ServerStatus):
    _include_workers: bool = PrivateAttr()

    def __init__(self, *args, **kwargs):
        self._include_workers = kwargs.pop("include_workers", False)
        super().__init__(*args, **kwargs)

    async def update(self) -> None:
        client = http_client.get()
        response = await client.get(self.url)
        response.raise_for_status()
        new_model = await self.async_parse_payload(
            url=self.url,
            payload=response.text,
            include_workers=self._include_workers,
        )
        for field, value in new_model:
            setattr(self, field, value)

    @classmethod
    async def parse_from_url(
        cls, url: str | HttpUrl, include_workers: bool = True
    ) -> "HttpxServerStatus":
        client = http_client.get()
        response = await client.get(url)
        response.raise_for_status()

        return await cls.async_parse_payload(
            url, response.text, include_workers=include_workers
        )

    @classmethod
    async def async_parse_payload(
        cls, url: str | HttpUrl, payload: str, include_workers: bool = True, **kwargs
    ):
        _executor = executor.get()
        _loop = asyncio.get_running_loop()
        _func = partial(
            cls.parse_payload,
            url=url,
            payload=payload,
            include_workers=include_workers,
            **kwargs
        )
        return await _loop.run_in_executor(_executor, _func)
