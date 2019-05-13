import asyncio
from collections import namedtuple

import docker


ContainerInfo = namedtuple('ContainerInfo', ['address', 'port', 'container'])


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


def run(image, port, protocol='tcp', address='127.0.0.1'):
    bind_port = f'{port}/{protocol}'
    client = docker.from_env()
    container = client.containers.run(
        image,
        detach=True,
        auto_remove=True,
        ports={bind_port: (address, None)}
    )

    _ports = client.api.inspect_container(container.id)['NetworkSettings']['Ports']
    _address = _ports[bind_port][0]['HostIp']
    _port = int(_ports[bind_port][0]['HostPort'])

    if asyncio.run(wait_for_port(_address, _port, timeout=5)) is False:
        raise RuntimeException('httpd did not start within 5s')

    return ContainerInfo(
        address=_address,
        port=_port,
        container=container
    )
