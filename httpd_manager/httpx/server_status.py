import asyncio
from functools import partial
from typing import Any

from pydantic import HttpUrl

from .client import get_http_client
from ..executor import executor as executor_var
from ..base import ServerStatus


def parse_values_from_payload(url: str | HttpUrl, payload: bytes, include_workers: bool = True) -> "HttpxServerStatus":
    model_values = {"url": str(url)}
    model_values.update(dict(ServerStatus.parse_values_from_payload(payload, include_workers=include_workers)))
    return HttpxServerStatus.model_validate(model_values)


class HttpxServerStatus(ServerStatus):
    async def update(self) -> None:
        async with get_http_client() as client:
            response = await client.get(str(self.url))

        response.raise_for_status()
        new_model = await self.async_model_validate_payload(
            url=str(self.url),
            payload=response.content,
            include_workers=self.workers is not None,
        )
        for field, value in new_model:
            setattr(self, field, value)

    @classmethod
    async def async_model_validate_url(cls, url: str | HttpUrl, include_workers: bool = True) -> "HttpxServerStatus":
        async with get_http_client() as client:
            response = await client.get(str(url))
        response.raise_for_status()
        return await cls.async_model_validate_payload(url, response.content, include_workers=include_workers)

    @classmethod
    async def async_model_validate_payload(
        cls, url: str | HttpUrl, payload: str | bytes, include_workers: bool = True
    ) -> "HttpxServerStatus":
        executor = executor_var.get()
        loop = asyncio.get_running_loop()
        handler = partial(parse_values_from_payload, url, payload, include_workers=include_workers)
        return await loop.run_in_executor(executor, handler)
