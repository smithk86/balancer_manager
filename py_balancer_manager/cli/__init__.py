import asyncio
from .manage import main as async_manage
from .validate import main as async_validate


def manage():
    asyncio.run(async_manage())


def validate():
    asyncio.run(async_validate())
