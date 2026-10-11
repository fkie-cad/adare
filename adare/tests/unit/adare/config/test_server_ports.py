import os
import subprocess
import sys

import pytest

pytestmark = pytest.mark.unit


def _ports(env_overrides: dict[str, str]) -> list[int]:
    code = 'from adare.config import server as s; print(s.MCP_CONTROL_PORT, s.LOCATE_PORT, s.GUI_MCP_PORT)'
    env = {
        k: v for k, v in os.environ.items() if k not in ('ADARE_MCP_PORT', 'ADARE_LOCATE_PORT', 'ADARE_GUI_MCP_PORT')
    }
    proc = subprocess.run(
        [sys.executable, '-c', code], env={**env, **env_overrides}, capture_output=True, text=True, check=True
    )
    return [int(p) for p in proc.stdout.split()]


def test_default_local_server_ports_do_not_collide():
    """mcp serve and the LocateAnything server both defaulted to 13111 and could not run together."""
    ports = _ports({})
    assert ports == [13112, 13111, 13110]
    assert len(set(ports)) == len(ports)


def test_mcp_control_port_env_override():
    assert _ports({'ADARE_MCP_PORT': '14000'})[0] == 14000


def test_mcp_serve_cli_uses_configured_port(monkeypatch):
    from types import SimpleNamespace

    from adare.cli import mcp_control

    seen = {}
    monkeypatch.setattr('adare.backend.chat.mcp_control_server.serve', lambda **kw: seen.update(kw), raising=True)
    mcp_control.exec_mcp_serve(SimpleNamespace(transport='http', host='127.0.0.1', port=None))

    assert seen['port'] == mcp_control.MCP_CONTROL_PORT
