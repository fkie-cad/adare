"""Boot-retry teardown in QEMULifecycleStrategy.

``adare vm test`` configures its share on the VM config itself and has no
experiment run directory, so a retry must not re-run the strategy's pre-boot
setup (which builds shares from that run directory and crashed with
``'NoneType' object has no attribute 'path'``).
"""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from adare.hypervisor.qemu.lifecycle import QEMULifecycleStrategy

pytestmark = [pytest.mark.unit, pytest.mark.asyncio]


def _strategy():
    strategy = QEMULifecycleStrategy.__new__(QEMULifecycleStrategy)  # retry teardown needs only file_transfer
    strategy.file_transfer = MagicMock()
    strategy.file_transfer.setup = AsyncMock()
    return strategy


def _context():
    vm = MagicMock()
    vm.stop = AsyncMock()
    vm.cleanup_overlay_disk = AsyncMock()
    vm.create_overlay_disk = AsyncMock(return_value='/tmp/fresh-overlay.qcow2')
    return SimpleNamespace(vm=vm, experiment_run_ulid='01TEST', experiment_run_directory=None)


@pytest.mark.parametrize('rerun', [True, False])
async def test_retry_reruns_file_transfer_only_when_asked(rerun):
    strategy = _strategy()
    ctx = _context()

    await strategy._reset_vm_for_boot_retry(ctx, rerun_file_transfer=rerun)

    ctx.vm.stop.assert_awaited_once_with(force=True, silent=True)
    assert ctx.vm.config.disk_path == '/tmp/fresh-overlay.qcow2'
    assert strategy.file_transfer.setup.await_count == (1 if rerun else 0)


async def test_start_passes_retry_flag_to_teardown(monkeypatch):
    """A boot attempt that never reaches the guest agent triggers the teardown with the caller's flag."""
    strategy = _strategy()
    resets = []

    async def fake_reset(context, rerun_file_transfer=True):
        resets.append(rerun_file_transfer)
        raise RuntimeError('stop after first retry')

    monkeypatch.setattr(strategy, '_reset_vm_for_boot_retry', fake_reset)
    monkeypatch.setattr(QEMULifecycleStrategy, '_boot_attempts', classmethod(lambda cls: 2))
    monkeypatch.setattr(QEMULifecycleStrategy, '_ready_timeout_for_attempt', classmethod(lambda cls, a, p=None: 1))
    monkeypatch.setattr(
        'adare.backend.experiment.execution.gui_executor_factory.resolve_gui_execution_mode', lambda vm, s: None
    )

    ctx = _context()
    ctx.playbook = None
    ctx.guest_platform = 'linux'
    ctx.user_interrupt_event = None
    ctx.vm.vm_name = 'test-vm'
    ctx.vm.start = AsyncMock()
    ctx.vm.wait_until_fully_booted = AsyncMock(return_value=False)

    with pytest.raises(RuntimeError, match='stop after first retry'):
        await strategy.start_and_initialize_vm(ctx, rerun_file_transfer_on_retry=False)

    assert resets == [False]
