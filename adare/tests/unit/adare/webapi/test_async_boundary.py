"""Web API handlers must never run a synchronous service on the server's event loop.

Services drive VMs through their own ``asyncio.run()``, which raises inside a
running loop (and would block the server even where it does not). Handlers
without awaits are therefore plain ``def`` (FastAPI's threadpool), and async
handlers hand service calls to ``asyncio.to_thread``.
"""

import ast
import asyncio
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from adare.core.dto.devmode import DevActionResult, DevSessionInfo
from adare.core.result import Result

pytestmark = pytest.mark.unit

WEBAPI_DIR = Path(__file__).resolve().parents[4] / 'adare' / 'webapi'
WEBAPI_FILES = sorted([WEBAPI_DIR / 'main.py', *(WEBAPI_DIR / 'routes').glob('*.py')])


def _is_service_call(call: ast.Call) -> bool:
    """``api.<area>.<method>(...)`` or ``_api().<area>.<method>(...)``."""
    func = call.func
    if not (isinstance(func, ast.Attribute) and isinstance(func.value, ast.Attribute)):
        return False
    root = func.value.value
    return (isinstance(root, ast.Name) and root.id == 'api') or (
        isinstance(root, ast.Call) and isinstance(root.func, ast.Name) and root.func.id == '_api'
    )


def _blocking_service_calls(path: Path) -> list[str]:
    found = []
    for node in ast.parse(path.read_text()).body:
        if not isinstance(node, ast.AsyncFunctionDef):
            continue
        awaited = {id(n.value) for n in ast.walk(node) if isinstance(n, ast.Await)}
        for call in (n for n in ast.walk(node) if isinstance(n, ast.Call)):
            if _is_service_call(call) and id(call) not in awaited:
                found.append(f'{path.name}:{call.lineno} {node.name}')
    return found


@pytest.mark.parametrize('path', WEBAPI_FILES, ids=lambda p: p.name)
def test_async_handlers_do_not_call_sync_services_on_the_loop(path):
    """Service calls in async handlers must be awaited (async API) or passed to asyncio.to_thread."""
    assert _blocking_service_calls(path) == []


# --- runtime: the routes changed for this rule ---------------------------------

_real_asyncio_run = asyncio.run


def _guarded_asyncio_run(coro, **kwargs):
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return _real_asyncio_run(coro, **kwargs)
    coro.close()
    raise AssertionError('asyncio.run() reached from the server event loop')


def _service(result):
    """A sync service method that, like the real ones, runs its own event loop."""

    def call(*args, **kwargs):
        asyncio.run(asyncio.sleep(0))
        return result

    return call


@pytest.fixture
def client():
    from adare.webapi import main

    session = DevSessionInfo(
        session_id='s1',
        project_path=Path('/p'),
        environment_name='env',
        vm_running=True,
        actions_executed=0,
        created_at=datetime.now(UTC),
        current_variables={},
        available_snapshots=[],
    )
    devmode = MagicMock()
    devmode.start_session = _service(Result.ok(session))
    devmode.stop_session = _service(Result.ok(None))
    devmode.execute_action = _service(Result.ok(DevActionResult(success=True, message='ok', execution_time=0.1)))
    devmode.create_checkpoint = _service(Result.ok(None))
    devmode.reset_soft = _service(Result.ok(None))
    devmode.restore_checkpoint = _service(Result.ok(None))
    devmode.list_sessions = _service(Result.ok([]))

    with (
        patch.object(main, 'api', SimpleNamespace(devmode=devmode)),
        patch.object(main, 'ws_manager', AsyncMock()),
        patch('asyncio.run', _guarded_asyncio_run),
    ):
        yield TestClient(main.app)


@pytest.mark.parametrize(
    ('method', 'url', 'body'),
    [
        ('post', '/api/sessions/start', {'project_path': '/p', 'experiment_name': 'e', 'environment_name': 'env'}),
        ('post', '/api/sessions/s1/stop', None),
        ('post', '/api/sessions/s1/actions/execute', {'action_yaml': 'type: wait'}),
        ('post', '/api/sessions/s1/checkpoints', {'name': 'cp'}),
        ('post', '/api/sessions/s1/reset?reset_type=soft', None),
        ('post', '/api/sessions/s1/checkpoints/cp/restore', None),
        ('get', '/api/sessions', None),
    ],
)
def test_devmode_routes_run_services_off_the_loop(client, method, url, body):
    response = getattr(client, method)(url, json=body) if body is not None else getattr(client, method)(url)

    assert response.status_code == 200, response.text
