from datetime import datetime

import httpx
import pytest
import respx
from packaging import version

from httpd_manager.server_status import Bytes, ServerStatus, Worker, WorkerStates


@pytest.mark.asyncio
async def test_live(py_httpd_client):
    # get performance stats
    stats = ServerStatus(py_httpd_client)

    # do update
    async with stats:
        await stats.update(include_workers=True)

    assert type(stats) is ServerStatus

    assert type(stats.date) is datetime
    assert isinstance(stats.httpd_version, version.Version)
    assert type(stats.httpd_built_date) is datetime
    assert isinstance(stats.openssl_version, version._BaseVersion)
    assert type(stats.requests_per_sec) is float or stats.requests_per_sec is None
    assert stats._bytes_per_second is None or type(stats._bytes_per_second) is Bytes
    assert stats.bytes_per_second is None or type(stats.bytes_per_second) is int
    assert type(stats._bytes_per_request) is Bytes
    assert type(stats.bytes_per_request) is int
    assert type(stats.ms_per_request) is float

    assert type(stats.worker_states) is WorkerStates

    # len(stats.workers) could be zero
    # but this is also tested in mocked as well
    for w in stats.workers:
        assert type(w) is Worker

    # confirm workers are not parsed if include_workers=False
    stats = ServerStatus(py_httpd_client)
    async with stats:
        await stats.update(include_workers=False)
    assert stats.workers is None


@pytest.mark.asyncio
async def test_mocked(mocked_client, test_files_dir):
    with open(f"{test_files_dir}/server-status-mock-1.html", "r") as fh:
        html_payload = fh.read()

    with respx.mock as respx_mock:
        respx_mock.get("http://respx").mock(
            return_value=httpx.Response(status_code=200, text=html_payload)
        )
        async with mocked_client:
            stats = await mocked_client.server_status(include_workers=True)
            stats_without_workers = await mocked_client.server_status(
                include_workers=False
            )

    assert type(stats) is ServerStatus

    assert type(stats.date) is datetime
    assert stats.httpd_version == version.Version("2.4.39")
    assert type(stats.httpd_built_date) == datetime
    assert stats.openssl_version == version.Version("1.1.1rc0")

    assert stats.requests_per_sec == 76.9
    assert stats._bytes_per_second.raw == 0.7
    assert stats._bytes_per_second.unit == "M"
    assert int(stats._bytes_per_second) == 700000
    assert stats.bytes_per_second == 700000
    assert stats._bytes_per_request.raw == 9.7
    assert stats._bytes_per_request.unit == "K"
    assert int(stats._bytes_per_request) == 9700
    assert stats.bytes_per_request == 9700
    assert stats.ms_per_request == 56.4499

    assert type(stats.worker_states) is WorkerStates
    assert stats.worker_states.closing_connection == 37
    assert stats.worker_states.dns_lookup == 0
    assert stats.worker_states.gracefully_finishing == 0
    assert stats.worker_states.idle == 0
    assert stats.worker_states.keepalive == 123
    assert stats.worker_states.logging == 0
    assert stats.worker_states.open == 1800
    assert stats.worker_states.reading_request == 0
    assert stats.worker_states.sending_reply == 5
    assert stats.worker_states.starting_up == 0
    assert stats.worker_states.waiting_for_connection == 535

    for w in stats.workers:
        assert type(w) is Worker

    assert stats_without_workers.workers is None
