import asyncio
from functools import partial

from pydantic import PrivateAttr

from .client import Client
from .executor import executor
from .immutable.server_status import (
    ImmutableServerStatus,
    Worker,
    WorkerState,
    WorkerStateCount,
)


class ServerStatus(ImmutableServerStatus):
    _client: Client = PrivateAttr()
    _include_workers: bool = PrivateAttr()

    class Config:
        allow_mutation = True
        validate_assignment = True

    def __init__(self, *args, **kwargs):
        assert "client" in kwargs, "client argument is required"
        self._client = kwargs["client"]
        self._include_workers = kwargs.pop("include_workers", False)
        super().__init__(*args, **kwargs)

    async def update(self) -> None:
        async with self._client.http_client() as http_client:
            response = await http_client.get(self._client.server_status_path)
        response.raise_for_status()
        new_model = await self.async_parse_payload(
            client=self._client,
            payload=response.text,
            include_workers=self._include_workers,
        )
        for field, value in new_model:
            setattr(self, field, value)

    @classmethod
    async def parse(
        cls, client: Client, include_workers: bool = True
    ) -> "ServerStatus":
        async with client.http_client() as http_client:
            response = await http_client.get(client.server_status_path)
        response.raise_for_status()

        return await cls.async_parse_payload(
            response.text, client=client, include_workers=include_workers
        )

    @classmethod
    async def async_parse_payload(
        cls, payload: str, client: Client, include_workers: bool = True, **kwargs
    ):
        _executor = executor.get()
        _loop = asyncio.get_running_loop()
        _func = partial(
            cls.parse_payload,
            payload=payload,
            client=client,
            include_workers=include_workers,
            **kwargs
        )
        return await _loop.run_in_executor(_executor, _func)
