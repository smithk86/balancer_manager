import asyncio


async def wait_for_port(address, port, timeout=5):
    async def port_is_available():
        writer = None
        try:
            _, writer = await asyncio.open_connection(address, port)
            return True
        except ConnectionRefusedError:
            return False
        finally:
            if writer:
                writer.close()

    async def loop():
        while True:
            if await port_is_available():
                break

    try:
        await asyncio.wait_for(loop(), timeout=5)
        return True
    except asyncio.TimeoutError:
        return False
