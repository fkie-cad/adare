"""Fixtures for the guest-agent tests (run on the guest's Python, 3.10+)."""

import pytest
import pytest_asyncio

from adarevm.core.server import AdareVMServer

TOKEN = 'test-token'


@pytest.fixture(autouse=True)
def _host_gui_mode(monkeypatch):
    # Never touch pyautogui / a display: GUI work is the host's in these tests.
    monkeypatch.setenv('ADARE_GUI_MODE', 'host')


@pytest_asyncio.fixture
async def agent():
    """A real agent server on an ephemeral loopback port; yields (server, url)."""
    server = AdareVMServer(host='127.0.0.1', port=0, token=TOKEN)
    ws_server = await server.start_server()
    port = next(iter(ws_server.sockets)).getsockname()[1]
    yield server, f'ws://127.0.0.1:{port}'
    ws_server.close()
    await ws_server.wait_closed()
