from pydantic import PrivateAttr

from .client import Client
from .immutable.server_status import ImmutableServerStatus


class ServerStatus(ImmutableServerStatus):
    _client: Client = PrivateAttr()
    _include_workers: bool = PrivateAttr()

    class Config:
        allow_mutation = True
        validate_assignment = True

    def __init__(self, *args, **kwargs):
        self._client = kwargs.pop("client")
        self._include_workers = kwargs.pop("include_workers")
        super().__init__(*args, **kwargs)

    async def update(self) -> None:
        async with self._client.http_client() as http_client:
            response = await http_client.get(self._client.server_status_path)
        response.raise_for_status()
        new_model = await self.async_parse(
            client=self._client,
            payload=response.text,
            include_workers=self._include_workers,
        )
        for field, value in new_model:
            setattr(self, field, value)

    @classmethod
    async def create(cls, client: Client, include_workers: bool = True):
        async with client.http_client() as http_client:
            response = await http_client.get(client.server_status_path)
        return await cls.async_parse(
            client, response.text, include_workers=include_workers
        )

    @classmethod
    async def async_parse(
        cls, client: Client, payload: str, include_workers: bool = True
    ):
        return await client._sync_handler(
            cls.parse_payload,
            payload=payload,
            client=client,
            include_workers=include_workers,
        )
