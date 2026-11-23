"""A too-long QEMU socket path is reported at run preparation / instance reservation, before anything starts."""

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from adare.backend.experiment import run_setup
from adare.backend.experiment.runctx import ExperimentConfig, ExperimentRunCtx
from adare.backend.vm import commands
from adare.hypervisor.qemu import socket_paths
from adare.hypervisor.qemu.socket_paths import SocketPathTooLongError

pytestmark = pytest.mark.unit

DEEP_STATE_DIR = Path('/Users/someone/Documents/Projects/ADARE/experiments/some-long-study-name/runs/home') / 'qemu'


@pytest.fixture
def deep_home(monkeypatch):
    monkeypatch.setattr(socket_paths, 'QEMU_STATE_DIR', DEEP_STATE_DIR)
    monkeypatch.setattr(socket_paths.platform, 'system', lambda: 'Darwin')


def _ctx(hypervisor: str) -> ExperimentRunCtx:
    ctx = ExperimentRunCtx(config=ExperimentConfig(project_path=Path('/tmp/p'), environment_name='env'))
    ctx.environment_ulid = '01ENV'
    ctx.hypervisor_type = hypervisor
    return ctx


@pytest.fixture
def vm_name():
    with patch.object(run_setup.environment_database, 'get_environment_by_ulid', return_value={'vm_name': 'ubuntu'}):
        yield


class TestPrepareRunEnvironment:
    def test_qemu_machine_with_deep_home_fails_before_anything_starts(self, deep_home, vm_name):
        with (
            patch.object(run_setup, 'StageCtxManager', MagicMock()),
            patch('adare.backend.system.disk_guard.ensure_free_disk') as disk_guard,
            patch.object(run_setup, 'ExperimentRunDirectory') as run_directory,
            patch('adare.backend.experiment.mcp_server_manager.MCPServerManager') as cv_server,
            pytest.raises(SocketPathTooLongError, match='socket path too long'),
        ):
            run_setup.step_prepare_run_environment(_ctx('qemu'))

        disk_guard.assert_not_called()
        run_directory.assert_not_called()
        cv_server.assert_not_called()

    def test_error_carries_the_fix(self, deep_home, vm_name):
        with pytest.raises(SocketPathTooLongError) as excinfo:
            run_setup._check_qemu_socket_paths(_ctx('qemu'))
        assert str(DEEP_STATE_DIR / 'run' / 'ubuntu_run_00000000.qmp') in excinfo.value.message
        assert any('shorter' in s for s in excinfo.value.possible_solutions)

    def test_virtualbox_machine_is_not_checked(self, deep_home, vm_name):
        run_setup._check_qemu_socket_paths(_ctx('virtualbox'))

    def test_short_home_passes(self, monkeypatch, vm_name):
        monkeypatch.setattr(socket_paths, 'QEMU_STATE_DIR', Path('/tmp/adare/qemu'))
        monkeypatch.setattr(socket_paths.platform, 'system', lambda: 'Darwin')
        run_setup._check_qemu_socket_paths(_ctx('qemu'))

    def test_unregistered_vm_still_checks_the_directory(self, deep_home):
        with (
            patch.object(run_setup.environment_database, 'get_environment_by_ulid', return_value=None),
            pytest.raises(SocketPathTooLongError),
        ):
            run_setup._check_qemu_socket_paths(_ctx('qemu'))


@pytest.mark.asyncio
async def test_run_instance_reservation_fails_before_reconcile_slot_or_port(deep_home):
    source_vm = SimpleNamespace(id='vm-1', name='ubuntu')
    with (
        patch('adare.backend.vm.run_instances.reconcile_instances', new_callable=AsyncMock) as reconcile,
        patch('adare.backend.vm.slots.acquire_slot') as acquire,
        patch.object(commands, 'verify_vm_integrity', new_callable=AsyncMock) as verify,
        patch('adare.backend.vm.run_instances.allocate_qemu_run_instance') as allocate,
        pytest.raises(SocketPathTooLongError),
    ):
        await commands._prepare_qemu_run_instance(source_vm, '01ULID', None, None, test_mode=False)

    reconcile.assert_not_awaited()
    verify.assert_not_awaited()
    acquire.assert_not_called()
    allocate.assert_not_called()
