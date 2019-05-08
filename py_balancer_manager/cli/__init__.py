import asyncio
from .manage import manage as async_manage
from .validate import validate as async_validate


def manage():
    asyncio.run(async_manage())


def validate():
    asyncio.run(async_validate())
