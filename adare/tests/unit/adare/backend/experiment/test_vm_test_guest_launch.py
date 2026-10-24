"""The source launch of adarevm in `adare vm test` (VirtualBox/OVA; QEMU uses the experiment's).

It must not write into the shared, installed appdata from the guest: the guest
agent runs as root, so a venv, bytecode or rewritten uv.lock there ends up
root-owned on the host and breaks the next `make install`.
"""

import shutil
import subprocess
import sys
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from adare.backend.experiment import agent_readiness, vm_test_ova

pytestmark = [pytest.mark.unit, pytest.mark.asyncio]


def _context(platform):
    vm = MagicMock()
    vm.config.smb_share_path = None
    vm.run_command = AsyncMock(return_value=SimpleNamespace(returncode=0, stderr=''))
    return SimpleNamespace(
        vm=vm,
        guest_platform=platform,
        user_interrupt_event=None,
        config=SimpleNamespace(websocket_port=19000),
    )


@pytest.mark.parametrize('platform', ['linux', 'windows'])
async def test_guest_keeps_venv_and_bytecode_off_the_share(platform, monkeypatch):
    monkeypatch.setattr(agent_readiness, 'wait_for_agent', AsyncMock())
    ctx = _context(platform)

    ok, _ = await vm_test_ova.check_source_agent_start(ctx, None)

    assert ok
    uv_commands = [c.args[0] for c in ctx.vm.run_command.await_args_list if 'uv ' in c.args[0]]
    assert uv_commands
    for command in uv_commands:
        assert 'UV_PROJECT_ENVIRONMENT' in command
        assert 'PYTHONDONTWRITEBYTECODE' in command
        assert '--frozen' in command
        assert '/adare/vm' not in command.split('UV_PROJECT_ENVIRONMENT')[1].split()[0]


async def test_windows_command_has_no_single_quotes():
    """run_as_user embeds the command in a single-quoted PowerShell string."""
    ctx = _context('windows')

    await vm_test_ova.check_source_agent_start(ctx, None)

    assert "'" not in ctx.vm.run_command.await_args.args[0]


@pytest.mark.skipif(sys.platform == 'win32' or shutil.which('bash') is None, reason='needs bash')
async def test_linux_launch_returns_while_server_keeps_running(tmp_path, monkeypatch):
    """The guest agent waits for the command's output pipes to close.

    A backgrounded `cd X && nohup server &` keeps them open for the server's
    lifetime, so the launch hung until the 300s guest-command timeout.
    """
    monkeypatch.setattr(agent_readiness, 'wait_for_agent', AsyncMock())
    ctx = _context('linux')
    await vm_test_ova.check_source_agent_start(ctx, None)
    command = ctx.vm.run_command.await_args.args[0]
    assert 'adarevm' in command

    # Same shell structure on the host: the server is a 3s sleep, xhost a no-op.
    command = (
        command.replace('uv run --frozen adarevm', 'sleep 3')
        .replace('/tmp/adarevm.log', str(tmp_path / 'adarevm.log'))
        .replace('/adare/vm/adarevm', str(tmp_path))
        .replace('xhost +SI:localuser:root', 'true')
    )
    subprocess.run(['bash', '-c', command], capture_output=True, check=True, timeout=2)
