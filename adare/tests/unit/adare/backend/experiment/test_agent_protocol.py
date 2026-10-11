"""Host side of the agent protocol (v2): token, welcome handshake, tool contract."""

import ast
import asyncio
import json
import logging
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
import websockets
from websockets.datastructures import Headers

from adare.backend.experiment import websocket_client
from adare.backend.experiment.agent_token import ensure_agent_token
from adare.backend.experiment.websocket_client import AdareVMClient, AgentAuthError, AgentProtocolError
from adarelib.websocket.protocol import (
    PROTOCOL_VERSION,
    BaseMessage,
    EventMessage,
    EventType,
    Tool,
    ToolResultMessage,
    create_event,
    parse_message,
)

pytestmark = pytest.mark.unit

ADARE_PKG = Path(__file__).resolve().parents[5] / 'adare'
TOOLS = sorted(t.value for t in Tool)


def _welcome(version=PROTOCOL_VERSION, tools=TOOLS) -> str:
    return create_event(EventType.WELCOME, {'protocol_version': version, 'tools': tools}).to_json()


class _StubAgent:
    """Minimal agent: optional token check, a configurable first message, echo of tool calls."""

    def __init__(self, first_message: str | None, token: str | None = None):
        self.first_message = first_message
        self.token = token
        self.received: list[dict] = []

    def authenticate(self, connection, request):
        if self.token and request.headers.get('Authorization') != f'Bearer {self.token}':
            return connection.respond(401, 'no\n')
        return None

    async def handler(self, ws):
        if self.first_message is not None:
            await ws.send(self.first_message)
        async for raw in ws:
            message = json.loads(raw)
            self.received.append(message)
            if message['type'] == 'tool_call':
                await ws.send(ToolResultMessage(id=message['id'], result={'tool': message['tool']}).to_json())


async def _serve(agent: _StubAgent):
    return await websockets.serve(agent.handler, '127.0.0.1', 0, process_request=agent.authenticate)


def _port(server) -> int:
    return next(iter(server.sockets)).getsockname()[1]


@pytest.mark.asyncio
async def test_connects_to_a_protocol_2_agent_and_records_its_tools():
    agent = _StubAgent(_welcome(), token='s3cret')
    async with await _serve(agent) as server:
        client = AdareVMClient(host='127.0.0.1', port=_port(server), token='s3cret')
        assert await client.connect(timeout=5) is True
        assert client.available_tools == set(TOOLS)

        result = await client.call_tool(Tool.GET_STATUS)
        await client.disconnect()

    assert result == {'tool': 'get_status'}
    hello, call = agent.received
    assert hello['type'] == 'connect' and hello['client_info']['protocol_version'] == PROTOCOL_VERSION
    assert call['tool'] == 'get_status'  # the enum goes over the wire as its value


@pytest.mark.asyncio
async def test_protocol_1_agent_is_rejected():
    old_welcome = create_event(EventType.LOG, {'message': 'Connected', 'server_info': {'available_tools': []}})
    async with await _serve(_StubAgent(old_welcome.to_json())) as server:
        client = AdareVMClient(host='127.0.0.1', port=_port(server))
        with pytest.raises(AgentProtocolError, match='protocol 1'):
            await client.connect(timeout=5)
    assert client.connected is False


@pytest.mark.asyncio
async def test_other_protocol_version_is_rejected():
    async with await _serve(_StubAgent(_welcome(version=PROTOCOL_VERSION + 1))) as server:
        with pytest.raises(AgentProtocolError, match=f'protocol {PROTOCOL_VERSION + 1}'):
            await AdareVMClient(host='127.0.0.1', port=_port(server)).connect(timeout=5)


@pytest.mark.asyncio
async def test_silent_agent_is_rejected(monkeypatch):
    monkeypatch.setattr(websocket_client, 'WELCOME_TIMEOUT', 0.2)
    async with await _serve(_StubAgent(None)) as server:
        with pytest.raises(AgentProtocolError, match='no welcome'):
            await AdareVMClient(host='127.0.0.1', port=_port(server)).connect(timeout=5)


@pytest.mark.asyncio
@pytest.mark.parametrize('token', [None, 'wrong'])
async def test_wrong_or_missing_token_raises_auth_error(token):
    async with await _serve(_StubAgent(_welcome(), token='s3cret')) as server:
        with pytest.raises(AgentAuthError):
            await AdareVMClient(host='127.0.0.1', port=_port(server), token=token).connect(timeout=5)


@pytest.mark.asyncio
async def test_call_tool_refuses_tools_the_agent_did_not_advertise():
    async with await _serve(_StubAgent(_welcome(tools=['get_status']))) as server:
        client = AdareVMClient(host='127.0.0.1', port=_port(server))
        await client.connect(timeout=5)
        with pytest.raises(RuntimeError, match='does not provide tool'):
            await client.call_tool(Tool.SCREENSHOT)
        await client.disconnect()


def test_parse_message_tolerates_unknown_fields_and_types():
    message = parse_message(json.dumps({'type': 'event', 'event_type': 'log', 'data': {}, 'added_later': 1}))
    assert isinstance(message, EventMessage)

    unknown = parse_message(json.dumps({'type': 'telemetry', 'id': 'x', 'payload': {}}))
    assert type(unknown) is BaseMessage and unknown.id == 'x'

    with pytest.raises(ValueError):
        parse_message('[1, 2]')


def test_auth_header_name_matches_websockets_case_insensitive_lookup():
    assert Headers({'authorization': 'Bearer t'})['Authorization'] == 'Bearer t'


# --- per-run token ----------------------------------------------------------


def _ctx(tmp_path, config=None):
    if config is not None:
        (tmp_path / 'config.json').write_text(json.dumps(config))
    return SimpleNamespace(agent_token=None, experiment_run_directory=SimpleNamespace(path=tmp_path))


def test_token_is_created_once_per_run(tmp_path):
    ctx = _ctx(tmp_path)
    token = ensure_agent_token(ctx)

    assert len(token) >= 40
    assert ensure_agent_token(ctx) == token == ctx.agent_token
    assert ensure_agent_token(_ctx(tmp_path / 'other')) != token


def test_token_is_reused_from_the_run_config(tmp_path):
    """A restored dev session reconnects to the agent that is still running with the old token."""
    assert ensure_agent_token(_ctx(tmp_path, {'agent_token': 'from-config'})) == 'from-config'


def test_token_never_appears_in_logs(tmp_path, caplog):
    token = ensure_agent_token(_ctx(tmp_path))
    caplog.set_level(logging.INFO)

    logging.getLogger('adare.test').info("echo '{\"agent_token\": \"%s\"}' > config.json", token)

    assert token not in caplog.text
    assert '***' in caplog.text


def test_config_builders_carry_the_token():
    from adare.backend.experiment.agent_command_builders import LinuxAgentCommandBuilder
    from adare.hypervisor.qemu.file_transfer.shares import build_config_json

    assert build_config_json(False, 'virtiofs', agent_token='t1')['agent_token'] == 't1'
    assert 'agent_token' not in build_config_json(True, 'smb')

    builder = LinuxAgentCommandBuilder(Path('/nowhere'), {}, 40000, agent_token='t2')
    assert json.loads(builder._build_config_file_payload())['agent_token'] == 't2'


# --- reinstall once on an old agent ------------------------------------------


@pytest.mark.asyncio
async def test_old_agent_is_reinstalled_once(monkeypatch):
    from adare.backend.experiment import agent_lifecycle, run_setup

    connect = AsyncMock(side_effect=[AgentProtocolError('protocol 1'), None])
    stop, install = AsyncMock(), AsyncMock()
    monkeypatch.setattr(agent_lifecycle, 'connect_websocket', connect)
    monkeypatch.setattr(agent_lifecycle, 'stop_agent', stop)
    monkeypatch.setattr(run_setup, 'install_and_run_adare_vm', install)
    ctx = SimpleNamespace(experiment_run_ulid=None, user_interrupt_event=asyncio.Event(), playbook=None)
    ctx.primary_machine = 'default'

    with patch.object(run_setup, 'StageCtxManager'):
        await run_setup.step_connect_websocket(ctx)

    assert connect.await_count == 2
    stop.assert_awaited_once()
    assert install.await_args.kwargs['force_install'] is True


@pytest.mark.asyncio
async def test_still_incompatible_after_reinstall_raises_clear_error(monkeypatch):
    from adare.backend.experiment import agent_lifecycle, run_setup
    from adare.backend.experiment.exceptions import AgentProtocolMismatchError

    monkeypatch.setattr(agent_lifecycle, 'connect_websocket', AsyncMock(side_effect=AgentProtocolError('protocol 1')))
    monkeypatch.setattr(agent_lifecycle, 'stop_agent', AsyncMock())
    monkeypatch.setattr(run_setup, 'install_and_run_adare_vm', AsyncMock())
    ctx = SimpleNamespace(experiment_run_ulid=None, user_interrupt_event=asyncio.Event(), playbook=None)
    ctx.primary_machine = 'default'

    with patch.object(run_setup, 'StageCtxManager'), pytest.raises(AgentProtocolMismatchError):
        await run_setup.step_connect_websocket(ctx)


# --- the host only calls tools the protocol declares --------------------------


def _call_tool_first_args():
    for path in ADARE_PKG.rglob('*.py'):
        tree = ast.parse(path.read_text(encoding='utf-8'))
        for node in ast.walk(tree):
            if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)):
                continue
            if node.func.attr != 'call_tool' or not node.args:
                continue
            receiver = node.func.value
            on_agent_client = (
                isinstance(receiver, ast.Name) and receiver.id == 'self' and path.name == 'websocket_client.py'
            ) or (isinstance(receiver, ast.Attribute) and receiver.attr == 'client')
            if on_agent_client:
                yield f'{path.relative_to(ADARE_PKG)}:{node.lineno}', node.args[0]


def test_every_agent_tool_call_names_a_protocol_tool():
    calls = list(_call_tool_first_args())
    assert calls, 'no agent call_tool sites found'
    for where, arg in calls:
        if isinstance(arg, ast.Attribute) and isinstance(arg.value, ast.Name) and arg.value.id == 'Tool':
            assert arg.attr in Tool.__members__, where
        elif isinstance(arg, ast.Constant):
            assert arg.value in TOOLS, f'{where}: {arg.value!r} is not a protocol tool'
        else:
            assert isinstance(arg, ast.Name) and arg.id == 'tool_name', f'{where}: use Tool.<NAME>'
