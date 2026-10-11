"""Dev-session snapshot operations run their blocking libvirt/virsh work off the event loop."""

import threading
from datetime import datetime
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from adare.backend.devmode.session import DevModeSession
from adare.backend.devmode.session.core import DevModeSnapshot
from adare.backend.experiment.runctx import ExperimentRunCtx
from adare.core.result import Result

pytestmark = pytest.mark.unit


@pytest.mark.asyncio
async def test_soft_reset_restores_the_snapshot_in_a_worker_thread():
    session = DevModeSession(session_id='s', project_path=Path('/tmp/project'), environment_name='env')
    session.experiment_ctx = MagicMock(spec=ExperimentRunCtx)
    session.experiment_ctx.experiment_run_directory = None
    session.experiment_ctx.hypervisor_type = 'qemu'
    session.experiment_ctx.client = None
    session._ensure_playbook_controller = AsyncMock(return_value=Result.ok(None))
    session.snapshots = [
        DevModeSnapshot(
            snapshot_name='initial',
            created_at=datetime.now(),
            variable_state={},
            memory_file_path='/tmp/ram.save',
            disk_file_path='/tmp/disk.qcow2',
        )
    ]
    seen = {}

    def restore(memory_path, disk_path):
        seen['thread'] = threading.current_thread()
        seen['args'] = (memory_path, disk_path)
        return False  # take the variable-only fallback: no reconnect needed here

    session.experiment_ctx.vm = MagicMock(restore_external_snapshot=restore)

    result = await session.reset_soft()

    assert result.success
    assert seen['args'] == ('/tmp/ram.save', '/tmp/disk.qcow2')
    assert seen['thread'] is not threading.main_thread()
