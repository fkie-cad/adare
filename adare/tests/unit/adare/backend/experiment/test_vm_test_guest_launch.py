"""'adare vm test' must not write into the shared ~/.adare/adare from the guest.

virtio-fs does not enforce read-only and the guest agent runs as root, so a
venv, bytecode or rewritten uv.lock there ends up root-owned on the host and
breaks the next `make install`.
"""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from adare.backend.experiment import agent_readiness, vm_test

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

    ok, _ = await vm_test.test_adarevm_server_start(ctx)

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

    await vm_test.test_adarevm_server_start(ctx)

    assert "'" not in ctx.vm.run_command.await_args.args[0]
