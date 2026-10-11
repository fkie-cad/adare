"""Readiness probing of the guest agent: real handshake polling instead of fixed sleeps."""

import asyncio
import logging
import socket
import threading
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
import websockets

from adare.backend.experiment import agent_lifecycle, agent_readiness, websocket_client
from adare.backend.experiment.agent_readiness import connect_with_backoff, wait_for_agent
from adare.backend.experiment.websocket_client import AdareVMClient, AgentProtocolError
from adare.exceptions import LoggedException
from adarelib.websocket.protocol import PROTOCOL_VERSION, EventType, create_event

pytestmark = pytest.mark.unit


def _welcome(version=PROTOCOL_VERSION) -> str:
    return create_event(EventType.WELCOME, {'protocol_version': version, 'tools': []}).to_json()


def _agent_handler(first_message: str):
    async def handler(ws):
        await ws.send(first_message)
        async for _ in ws:
            pass

    return handler


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(('127.0.0.1', 0))
        return s.getsockname()[1]


async def _accept_and_close(reader, writer):
    """What QEMU hostfwd does while nothing listens in the guest: accept, then hang up."""
    writer.close()


@pytest.mark.asyncio
async def test_connects_as_soon_as_a_late_agent_starts_listening():
    port = _free_port()
    client = AdareVMClient(host='127.0.0.1', port=port)

    async def start_late():
        await asyncio.sleep(0.4)
        return await websockets.serve(_agent_handler(_welcome()), '127.0.0.1', port)

    loop = asyncio.get_running_loop()
    started = loop.time()
    server_task = asyncio.create_task(start_late())
    try:
        assert await connect_with_backoff(client, budget=10.0) is True
        elapsed = loop.time() - started
        assert client.connected
        await client.disconnect()
    finally:
        server = await server_task
        server.close()
        await server.wait_closed()
    assert 0.4 <= elapsed < 2.0  # seen within one backoff step, not after a fixed sleep


@pytest.mark.asyncio
async def test_a_port_that_accepts_tcp_but_never_handshakes_is_not_ready():
    server = await asyncio.start_server(_accept_and_close, '127.0.0.1', 0)
    port = server.sockets[0].getsockname()[1]
    client = AdareVMClient(host='127.0.0.1', port=port)
    connect = AsyncMock(wraps=client.connect)
    client.connect = connect

    loop = asyncio.get_running_loop()
    started = loop.time()
    async with server:
        assert await connect_with_backoff(client, budget=0.8) is False
    assert loop.time() - started < 2.0  # bounded by the budget
    assert connect.await_count >= 3  # 0, 0.1, 0.3, 0.7 s ...
    assert all(call.kwargs['quiet'] for call in connect.await_args_list)


@pytest.mark.asyncio
async def test_failed_probe_attempts_are_not_logged_as_errors(caplog):
    server = await asyncio.start_server(_accept_and_close, '127.0.0.1', 0)
    port = server.sockets[0].getsockname()[1]
    with caplog.at_level(logging.DEBUG, logger=websocket_client.log.name):
        async with server:
            await connect_with_backoff(AdareVMClient(host='127.0.0.1', port=port), budget=0.3)
    assert not [r for r in caplog.records if r.levelno >= logging.ERROR]


@pytest.mark.asyncio
async def test_stop_event_ends_the_wait():
    stop = threading.Event()
    stop.set()
    client = MagicMock()
    client.connect = AsyncMock(return_value=False)
    assert await connect_with_backoff(client, budget=30.0, stop_event=stop) is False
    client.connect.assert_not_awaited()


@pytest.mark.asyncio
async def test_backoff_doubles_up_to_the_cap(monkeypatch):
    sleeps = []

    async def fake_sleep(delay):
        sleeps.append(delay)

    client = MagicMock()
    client.connect = AsyncMock(side_effect=[False] * 7 + [True])
    monkeypatch.setattr(agent_readiness.asyncio, 'sleep', fake_sleep)
    assert await connect_with_backoff(client, budget=60.0) is True
    assert sleeps == pytest.approx([0.1, 0.2, 0.4, 0.8, 1.6, 2.0, 2.0])


@pytest.mark.asyncio
async def test_protocol_mismatch_propagates_from_the_probe():
    async with websockets.serve(_agent_handler(_welcome(PROTOCOL_VERSION + 1)), '127.0.0.1', 0) as server:
        port = next(iter(server.sockets)).getsockname()[1]
        with pytest.raises(AgentProtocolError):
            await connect_with_backoff(AdareVMClient(host='127.0.0.1', port=port), budget=2.0)


@pytest.mark.asyncio
async def test_wait_for_agent_disconnects_after_a_successful_probe(monkeypatch):
    connections = []

    async def handler(ws):
        connections.append(ws)
        await ws.send(_welcome())
        async for _ in ws:
            pass

    monkeypatch.setattr(agent_readiness, 'AdareVMClient', lambda port, token: AdareVMClient('127.0.0.1', port, token))
    async with websockets.serve(handler, '127.0.0.1', 0) as server:
        port = next(iter(server.sockets)).getsockname()[1]
        assert await wait_for_agent(port, budget=2.0) is True
        await asyncio.wait_for(connections[0].wait_closed(), timeout=2.0)


@pytest.mark.asyncio
async def test_wait_for_agent_counts_a_refused_handshake_as_up(monkeypatch):
    monkeypatch.setattr(agent_readiness, 'AdareVMClient', lambda port, token: AdareVMClient('127.0.0.1', port, token))
    async with websockets.serve(_agent_handler(_welcome(PROTOCOL_VERSION + 1)), '127.0.0.1', 0) as server:
        port = next(iter(server.sockets)).getsockname()[1]
        assert await wait_for_agent(port, budget=2.0) is True


@pytest.mark.asyncio
async def test_wait_for_agent_gives_up_after_its_budget(monkeypatch):
    monkeypatch.setattr(agent_readiness, 'AdareVMClient', lambda port, token: AdareVMClient('127.0.0.1', port, token))
    assert await wait_for_agent(_free_port(), budget=0.3) is False


# --- connect_websocket: probe first, diagnostics only when the agent is slow ---


def _context():
    stage = SimpleNamespace(sub_msg='', status=None)
    ctx = SimpleNamespace(
        config=SimpleNamespace(websocket_port=19000),
        hypervisor_type='qemu',
        adarevm_pid=None,
        guest_platform='linux',
        vm=MagicMock(),
        stop_event=threading.Event(),
        client=None,
    )
    return ctx, SimpleNamespace(stage=stage, set_status=MagicMock())


def _patch_client(monkeypatch, probe_result):
    client = MagicMock()
    client.connect = AsyncMock(return_value=False)
    client.ping = AsyncMock(return_value=True)
    client.get_status = AsyncMock(return_value={})
    monkeypatch.setattr(websocket_client, 'AdareVMClient', MagicMock(return_value=client))
    monkeypatch.setattr(agent_lifecycle, 'ensure_agent_token', lambda ctx: 'tok')
    probe = AsyncMock(return_value=probe_result)
    monkeypatch.setattr(agent_readiness, 'connect_with_backoff', probe)
    diagnose = AsyncMock(return_value=False)
    monkeypatch.setattr(agent_lifecycle, '_diagnose_websocket_connection', diagnose)
    return client, probe, diagnose


@pytest.mark.asyncio
async def test_connect_websocket_skips_diagnostics_when_the_agent_answers_at_once(monkeypatch):
    ctx, stage_ctx = _context()
    client, probe, diagnose = _patch_client(monkeypatch, probe_result=True)

    await agent_lifecycle.connect_websocket(ctx, stage_ctx)

    probe.assert_awaited_once()
    assert probe.await_args.args[1] == agent_lifecycle._STARTUP_GRACE
    diagnose.assert_not_awaited()
    client.ping.assert_awaited_once()
    client.connect.assert_not_awaited()  # no loud retries


@pytest.mark.asyncio
async def test_connect_websocket_still_fails_fast_when_the_agent_died_at_startup(monkeypatch):
    ctx, stage_ctx = _context()
    client, _probe, diagnose = _patch_client(monkeypatch, probe_result=False)

    with pytest.raises(LoggedException, match='exited immediately'):
        await agent_lifecycle.connect_websocket(ctx, stage_ctx)

    assert [c.kwargs['full'] for c in diagnose.await_args_list] == [False, True]
    client.connect.assert_not_awaited()


@pytest.mark.asyncio
async def test_connect_websocket_keeps_the_old_retry_budget_for_a_slow_agent(monkeypatch):
    ctx, stage_ctx = _context()
    client, _probe, diagnose = _patch_client(monkeypatch, probe_result=False)
    diagnose.return_value = True  # alive, just not answering
    sleeps = []

    async def fake_sleep(delay):
        sleeps.append(delay)

    monkeypatch.setattr(agent_lifecycle.asyncio, 'sleep', fake_sleep)
    with pytest.raises(LoggedException, match='after 6 attempts'):
        await agent_lifecycle.connect_websocket(ctx, stage_ctx)

    assert client.connect.await_count == 6
    assert sleeps == [1, 2, 4, 8, 12]
    assert sum(sleeps) == sum([2, 3, 5, 7, 10])  # same patience as the old delays
