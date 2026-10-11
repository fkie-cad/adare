"""The agent's WebSocket server end to end: auth, welcome, tool calls."""

import json
import logging

import pytest
import websockets
from websockets.exceptions import InvalidStatus

from adarelib.websocket.protocol import PROTOCOL_VERSION, Tool
from adarevm.core.server import AdareVMServer

from .conftest import TOKEN

AUTH = {'Authorization': f'Bearer {TOKEN}'}


async def _recv_json(ws) -> dict:
    return json.loads(await ws.recv())


@pytest.mark.asyncio
async def test_welcome_announces_protocol_versions_and_tools(agent):
    _, url = agent
    async with websockets.connect(url, additional_headers=AUTH) as ws:
        welcome = await _recv_json(ws)

    assert welcome['type'] == 'event' and welcome['event_type'] == 'welcome'
    data = welcome['data']
    assert data['protocol_version'] == PROTOCOL_VERSION
    assert data['tools'] == sorted(tool.value for tool in Tool)
    assert {'adarevm_version', 'adarelib_version'} <= set(data)


@pytest.mark.asyncio
async def test_tool_call_round_trip_tolerates_unknown_fields(agent):
    _, url = agent
    async with websockets.connect(url, additional_headers=AUTH) as ws:
        await _recv_json(ws)  # welcome
        await ws.send(json.dumps({'type': 'connect', 'client_info': {'protocol_version': PROTOCOL_VERSION}}))
        call = {'type': 'tool_call', 'id': 'c1', 'tool': 'get_status', 'params': {}, 'added_in_v3': True}
        await ws.send(json.dumps(call))
        result = await _recv_json(ws)

    assert result['type'] == 'tool_result' and result['id'] == 'c1'
    assert result['success'] is True
    assert result['result']['connected_clients'] == 1


@pytest.mark.asyncio
async def test_unknown_tool_is_a_failed_result(agent):
    _, url = agent
    async with websockets.connect(url, additional_headers=AUTH) as ws:
        await _recv_json(ws)
        await ws.send(json.dumps({'type': 'tool_call', 'id': 'c2', 'tool': 'run_all_tests', 'params': {}}))
        result = await _recv_json(ws)

    assert result['success'] is False and 'Unknown tool' in result['error']


@pytest.mark.asyncio
@pytest.mark.parametrize('headers', [None, {'Authorization': 'Bearer wrong'}, {'Authorization': TOKEN}])
async def test_missing_or_wrong_token_is_rejected(agent, headers):
    _, url = agent
    with pytest.raises(InvalidStatus) as excinfo:
        async with websockets.connect(url, additional_headers=headers):
            pass
    assert excinfo.value.response.status_code == 401


@pytest.mark.asyncio
async def test_without_a_configured_token_connections_are_accepted_with_a_warning(caplog):
    caplog.set_level(logging.WARNING)
    server = AdareVMServer(host='127.0.0.1', port=0)
    ws_server = await server.start_server()
    port = next(iter(ws_server.sockets)).getsockname()[1]
    try:
        async with websockets.connect(f'ws://127.0.0.1:{port}') as ws:
            assert (await _recv_json(ws))['event_type'] == 'welcome'
    finally:
        ws_server.close()
        await ws_server.wait_closed()
    assert 'unauthenticated' in caplog.text
