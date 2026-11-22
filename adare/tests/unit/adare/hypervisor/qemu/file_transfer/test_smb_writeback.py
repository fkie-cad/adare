"""SMB writeback must return the guest's output without reverting host-written files.

The SMB strategy serves a *copy* of each share (setup), and copies read-write shares
back at retrieval/cleanup. The run directory is such a share, and the host keeps
writing files in it during the run (``logs/mcp_gui.log``, ``adare.log``,
``qemu_debug.log``). Copying the whole staged tree back used to reset those to their
setup-time content and mtime: every SMB run lost its cv-server log after the first
~2 s. Only files the guest created or changed may be written back.
"""

import asyncio
import os
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from adare.hypervisor.qemu.file_transfer import smb_strategy
from adare.hypervisor.qemu.file_transfer.smb_strategy import SMBStrategy

pytestmark = pytest.mark.unit


@pytest.fixture
def staged(tmp_path, monkeypatch):
    """An SMBStrategy after setup(), sharing ``run_dir`` read-write as tag 'run'."""
    run_dir = tmp_path / 'run'
    (run_dir / 'logs').mkdir(parents=True)
    (run_dir / 'logs' / 'mcp_gui.log').write_text('startup\n')
    (run_dir / 'logs' / 'adarevm.log').write_text('agent v1\n')

    monkeypatch.setattr(
        smb_strategy,
        'build_share_list',
        lambda ctx, is_windows, base: [
            {'tag': 'run', 'host_path': str(run_dir), 'guest_mount': '/adare/run', 'readonly': False}
        ],
    )
    monkeypatch.setattr(smb_strategy, 'build_config_json', lambda **kwargs: {})
    monkeypatch.setattr(smb_strategy, 'ensure_agent_token', lambda ctx: 'token')
    monkeypatch.setattr(smb_strategy.tempfile, 'mkdtemp', lambda prefix: str(tmp_path / 'smb'))

    context = MagicMock()
    context.guest_platform = 'linux'
    context.experiment_run_directory.path = run_dir
    context.vm.config.vm_name = 'vm'

    strategy = SMBStrategy()
    asyncio.run(strategy.setup(context))
    return strategy, run_dir, tmp_path / 'smb' / 'run'


def _age(path: Path, seconds: int = 10) -> None:
    """Make a guest edit distinguishable even on filesystems with coarse mtimes."""
    st = path.stat()
    os.utime(path, ns=(st.st_atime_ns, st.st_mtime_ns + seconds * 1_000_000_000))


def test_host_log_written_after_setup_survives_writeback(staged):
    strategy, run_dir, _share = staged
    (run_dir / 'logs' / 'mcp_gui.log').write_text('startup\nStarting text search for: ...\n')
    (run_dir / 'logs' / 'adare.log').write_text('host log\n')

    strategy._writeback_to_host()

    assert (run_dir / 'logs' / 'mcp_gui.log').read_text() == 'startup\nStarting text search for: ...\n'
    assert (run_dir / 'logs' / 'adare.log').read_text() == 'host log\n'


def test_guest_written_files_are_copied_back(staged):
    strategy, run_dir, share = staged
    (share / 'artifacts').mkdir()
    (share / 'artifacts' / 'evidence.bin').write_bytes(b'\x00guest')
    (share / 'logs' / 'adarevm.log').write_text('agent v1\nagent finished\n')
    _age(share / 'logs' / 'adarevm.log')
    (share / 'empty_dir').mkdir()

    strategy._writeback_to_host()

    assert (run_dir / 'artifacts' / 'evidence.bin').read_bytes() == b'\x00guest'
    assert (run_dir / 'logs' / 'adarevm.log').read_text() == 'agent v1\nagent finished\n'
    assert (run_dir / 'empty_dir').is_dir()


def test_writeback_is_idempotent_and_cleanup_removes_the_share(staged):
    strategy, run_dir, share = staged
    (share / 'late.txt').write_text('guest')
    strategy._writeback_to_host()
    (run_dir / 'late.txt').write_text('host changed it afterwards')

    strategy.cleanup()  # second writeback must not run again

    assert (run_dir / 'late.txt').read_text() == 'host changed it afterwards'
    assert not share.exists()
