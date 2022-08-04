from concurrent.futures import ProcessPoolExecutor
from datetime import datetime

import pytest

from httpd_manager import *


pytestmark = pytest.mark.anyio


def validate_properties(server_status):
    assert isinstance(server_status, ServerStatus)
    assert isinstance(server_status.date, datetime)
    assert isinstance(server_status.httpd_version, str)
    assert isinstance(server_status.httpd_built_date, datetime)
    assert isinstance(server_status.openssl_version, str)
    assert isinstance(server_status.requests_per_sec, float)
    assert isinstance(server_status.bytes_per_second, int)
    assert isinstance(server_status.bytes_per_request, int)
    assert isinstance(server_status.ms_per_request, float)
    assert isinstance(server_status.worker_states, WorkerStateCount)
    assert server_status.workers is None or isinstance(server_status.workers, list)


async def test_server_status(client):
    server_status = await client.server_status()
    validate_properties(server_status)
    assert server_status.workers is None

    # test update
    _original_date = server_status.date
    await server_status.update()
    assert _original_date < server_status.date

    # confirm workers if include_workers=True
    server_status = await client.server_status(include_workers=True)
    validate_properties(server_status)
    assert isinstance(server_status.workers, list)


async def test_with_process_pool(client):
    with ProcessPoolExecutor(max_workers=10) as ppexec:
        _token = executor.set(ppexec)

        server_status = await client.server_status()
        validate_properties(server_status)
        assert server_status.workers is None

        # test update
        _original_date = server_status.date
        await server_status.update()
        assert _original_date < server_status.date

        # confirm workers if include_workers=True
        server_status = await client.server_status(include_workers=True)
        validate_properties(server_status)
        assert isinstance(server_status.workers, list)

        executor.reset(_token)


async def test_mocked_server_status(create_client, httpx_mock, test_files_dir):
    mocked_client = create_client("https://pytest-httpx")

    with open(test_files_dir.joinpath("server-status-mock-1.html"), "r") as fh:
        html_payload = fh.read()

    httpx_mock.add_response(url="https://pytest-httpx/server-status", text=html_payload)

    server_status = await mocked_client.server_status(include_workers=True)
    validate_properties(server_status)
    assert server_status.httpd_version == "2.4.39"
    assert server_status.openssl_version == "1.1.1c"
    assert server_status.requests_per_sec == 76.9
    assert server_status.bytes_per_second == 700000
    assert server_status.bytes_per_request == 9700
    assert server_status.ms_per_request == 56.4499
    assert server_status.worker_states.closing_connection == 37
    assert server_status.worker_states.dns_lookup == 0
    assert server_status.worker_states.gracefully_finishing == 0
    assert server_status.worker_states.idle == 0
    assert server_status.worker_states.keepalive == 123
    assert server_status.worker_states.logging == 0
    assert server_status.worker_states.open == 1800
    assert server_status.worker_states.reading_request == 0
    assert server_status.worker_states.sending_reply == 5
    assert server_status.worker_states.starting_up == 0
    assert server_status.worker_states.waiting_for_connection == 535

    for w in server_status.workers:
        assert isinstance(w, Worker)
