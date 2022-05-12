import asyncio
import socket
import time
from collections import namedtuple
from contextlib import contextmanager
from typing import Dict, Generator, List, Tuple

import docker
from docker.client import DockerClient
from docker.models.containers import Container


ContainerInfo = namedtuple("ContainerInfo", ["ports", "container"])


def wait_for_port(host: str, port: int, timeout: int = 5) -> bool:
    start_time = time.perf_counter()
    while True:
        try:
            with socket.create_connection((host, port), timeout=timeout):
                return True
        except OSError as ex:
            time.sleep(0.01)
            if time.perf_counter() - start_time >= timeout:
                return False


@contextmanager
def run(
    image: str, ports: List[int], environment: Dict[str, str] | None = None
) -> Generator[ContainerInfo, None, None]:
    container_run_ports: Dict[int, Tuple[str, None]] = dict()
    for port in ports:
        container_run_ports[port] = ("0.0.0.0", None)
    client: docker.DockerClient = docker.from_env()
    container: Container = client.containers.run(
        image,
        detach=True,
        auto_remove=True,
        ports=container_run_ports,
        environment=environment,
    )

    _ports: Dict[int, List[Dict[str, str]]] = client.api.inspect_container(
        container.id
    )["NetworkSettings"]["Ports"]
    _binded_ports: Dict[int, int] = dict()
    for port in ports:
        _binded_ports[port] = int(_ports[port][0]["HostPort"])
    for port in _binded_ports.values():
        if wait_for_port("localhost", port, timeout=15) is False:
            raise RuntimeError(f"{image} did not start within 15s")

    try:
        yield ContainerInfo(ports=_binded_ports, container=container)
    finally:
        container.stop()
