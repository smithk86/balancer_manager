from concurrent.futures import ProcessPoolExecutor
from datetime import datetime
from pathlib import Path

import pytest
from pytest_httpx import HTTPXMock

from httpd_manager import ServerStatus, Worker, WorkerStateCount, executor
from httpd_manager.httpx import HttpxServerStatus

pytestmark = pytest.mark.asyncio


def validate_properties(server_status: ServerStatus) -> None:
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


@pytest.fixture
def server_status_url(httpd_endpoint: str) -> str:
    return f"{httpd_endpoint}/server-status"


async def test_server_status(server_status_url: str) -> None:
    server_status = await HttpxServerStatus.async_model_validate_url(server_status_url, include_workers=False)
    validate_properties(server_status)
    assert server_status.workers is None

    # test update
    _original_date = server_status.date
    await server_status.update()
    assert _original_date < server_status.date

    # confirm workers if include_workers=True
    server_status = await HttpxServerStatus.async_model_validate_url(server_status_url, include_workers=True)
    validate_properties(server_status)
    assert isinstance(server_status.workers, list)


async def test_with_process_pool(server_status_url: str) -> None:
    with ProcessPoolExecutor(max_workers=10) as ppexec:
        _token = executor.set(ppexec)

        server_status = await HttpxServerStatus.async_model_validate_url(server_status_url, include_workers=False)
        validate_properties(server_status)
        assert server_status.workers is None

        # test update
        _original_date = server_status.date
        await server_status.update()
        assert _original_date < server_status.date

        # confirm workers if include_workers=True
        server_status = await HttpxServerStatus.async_model_validate_url(server_status_url, include_workers=True)
        validate_properties(server_status)
        assert isinstance(server_status.workers, list)

        executor.reset(_token)


async def test_mocked_server_status_1(httpx_mock: HTTPXMock, test_files_dir: Path) -> None:
    with test_files_dir.joinpath("server-status-mock-1.html").open("r") as fh:
        html_payload = fh.read()

    httpx_mock.add_response(url="http://testserver.local/server-status", text=html_payload)

    server_status = await HttpxServerStatus.async_model_validate_url(
        "http://testserver.local/server-status", include_workers=True
    )
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

    assert isinstance(server_status.workers, list)
    assert len(server_status.workers) == 38
    for w in server_status.workers:
        assert isinstance(w, Worker)

    assert server_status.workers[37].srv == "2-0"
    assert server_status.workers[37].pid is None
    assert server_status.workers[37].acc == "0/2/2"
    assert server_status.workers[37].m == "_"
    assert server_status.workers[37].cpu == 0.06
    assert server_status.workers[37].ss == 9
    assert server_status.workers[37].req == 0
    assert server_status.workers[37].dur == 0
    assert server_status.workers[37].conn == 0.0
    assert server_status.workers[37].child == 0.01
    assert server_status.workers[37].slot == 0.01
    assert server_status.workers[37].client == "172.30.0.1"
    assert server_status.workers[37].protocol == "http/1.1"
    assert server_status.workers[37].vhost == "172.30.0.3:80"
    assert server_status.workers[37].request == "GET /favicon.ico HTTP/1.1"


async def test_mocked_server_status_2(httpx_mock: HTTPXMock, test_files_dir: Path) -> None:
    with test_files_dir.joinpath("server-status-mock-2.html").open("r") as fh:
        html_payload = fh.read()

    httpx_mock.add_response(url="http://testserver.local/server-status", text=html_payload)

    server_status = await HttpxServerStatus.async_model_validate_url(
        "http://testserver.local/server-status", include_workers=True
    )
    validate_properties(server_status)
    assert server_status.httpd_version == "2.4.53"
    assert server_status.openssl_version == "1.1.1n"
    assert server_status.requests_per_sec == 0.115
    assert server_status.bytes_per_second == 315
    assert server_status.bytes_per_request == 2730
    assert server_status.ms_per_request == 0.666667
    assert server_status.worker_states.closing_connection == 0
    assert server_status.worker_states.dns_lookup == 0
    assert server_status.worker_states.gracefully_finishing == 0
    assert server_status.worker_states.idle == 0
    assert server_status.worker_states.keepalive == 0
    assert server_status.worker_states.logging == 0
    assert server_status.worker_states.open == 325
    assert server_status.worker_states.reading_request == 0
    assert server_status.worker_states.sending_reply == 1
    assert server_status.worker_states.starting_up == 0
    assert server_status.worker_states.waiting_for_connection == 74

    assert isinstance(server_status.workers, list)
    assert len(server_status.workers) == 4
    for w in server_status.workers:
        assert isinstance(w, Worker)

    assert server_status.workers[3].srv == "2-0"
    assert server_status.workers[3].pid == 10
    assert server_status.workers[3].acc == "2/0/0"
    assert server_status.workers[3].m == "W"
    assert server_status.workers[3].cpu == 0.0
    assert server_status.workers[3].ss == 0
    assert server_status.workers[3].req == 0
    assert server_status.workers[3].dur == 0
    assert server_status.workers[3].conn == 0.0
    assert server_status.workers[3].child == 0.0
    assert server_status.workers[3].slot == 0.0
    assert server_status.workers[3].client == "192.168.128.1"
    assert server_status.workers[3].protocol == "http/1.1"
    assert server_status.workers[3].vhost == "192.168.128.2:80"
    assert server_status.workers[3].request == "GET /server-status HTTP/1.1"


async def test_bad_payload(httpx_mock: HTTPXMock, test_files_dir: Path) -> None:
    with test_files_dir.joinpath("balancer-manager-mock-1.html").open("r") as fh:
        httpx_mock.add_response(url="http://testserver.local/server-status", text=fh.read())

    with pytest.raises(
        ValueError,
        match=r"initial html validation failed; is this really an Httpd Server Status page?",
    ):
        await HttpxServerStatus.async_model_validate_url("http://testserver.local/server-status")
