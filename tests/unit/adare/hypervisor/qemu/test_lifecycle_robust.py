
import pytest
from unittest.mock import MagicMock, patch, AsyncMock
from pathlib import Path
import asyncio

from adare.hypervisor.qemu.lifecycle import QEMULifecycleStrategy
from adare.backend.experiment.runctx import ExperimentRunCtx
from adare.hypervisor.qemu.vm import QEMUVM

@pytest.fixture
def strategy():
    with patch('adare.hypervisor.qemu.lifecycle.QEMUManager'):
        return QEMULifecycleStrategy()

@pytest.fixture
def run_ctx():
    ctx = MagicMock(spec=ExperimentRunCtx)
    ctx.vm = MagicMock(spec=QEMUVM)
    ctx.vm.vm_name = "test-vm"
    ctx.config = MagicMock()
    ctx.config.gui_mode_override = None
    ctx.experiment_run_ulid = "run_123"
    ctx.user_interrupt_event = MagicMock()
    ctx.adarevm_pid = 12345
    # Mock playbook settings for resolve_gui_execution_mode
    ctx.playbook = MagicMock()
    ctx.playbook.settings = None 
    return ctx

class TestQEMULifecycleStrategyRobust:

    @pytest.mark.asyncio
    @patch('adare.hypervisor.qemu.lifecycle.resolve_gui_execution_mode')
    async def test_start_and_initialize_vm_success(self, mock_resolve_gui, strategy, run_ctx):
        # Setup mocks
        from adare.backend.experiment.execution.base import GUIExecutionMode
        mock_resolve_gui.return_value = GUIExecutionMode.HEADLESS
        
        strategy.qemu_manager.get_vm.return_value = run_ctx.vm
        run_ctx.vm.is_running = AsyncMock(return_value=False)
        run_ctx.vm.start = AsyncMock(return_value=True)
        # Mock wait_for_guest_agent if it exists or wait_for_ssh
        run_ctx.vm.wait_for_ssh = AsyncMock(return_value=True)
        # Mock StageCtxManager to avoid DB calls
        with patch('adare.hypervisor.qemu.lifecycle.StageCtxManager', new_callable=MagicMock):
            await strategy.start_and_initialize_vm(run_ctx)
        
        # Assert
        run_ctx.vm.start.assert_called_once()


    @pytest.mark.asyncio
    async def test_prepare_vm_for_experiment(self, strategy, run_ctx):
        # Setup
        strategy.qemu_manager.get_vm.return_value = run_ctx.vm
        run_ctx.vm.prepare_for_experiment = AsyncMock()
        
        # Act
        await strategy.prepare_vm_for_experiment(run_ctx)
        
        # Assert
        strategy.qemu_manager.get_vm.assert_called()


    @pytest.mark.asyncio
    async def test_cleanup_vm(self, strategy, run_ctx):
        # Act
        # cleanup_vm is async in QEMU lifecycle
        with patch('adare.hypervisor.qemu.lifecycle.log'):
             await strategy.cleanup_vm(run_ctx)
        
        # Assert
        # Check if basic logging happened or no errors raised
        pass

    @patch('subprocess.run')
    def test_copy_files_to_disk_via_libguestfs(self, mock_run, strategy):
        # Setup
        # Mock _detect_root_filesystem to prevent guestfish calls
        strategy._detect_root_filesystem = MagicMock(return_value=('/dev/sda1', 'ext4'))
        
        mock_run.return_value.returncode = 0
        disk_path = "/tmp/disk.qcow2"
        files = [{'source': '/tmp/src', 'dest': 'dest/file'}]
        
        with patch('pathlib.Path.exists', return_value=True):
             strategy._copy_files_to_disk_via_libguestfs(disk_path, files)
             
        assert mock_run.called
        args = mock_run.call_args[0][0]
        assert 'guestfish' in args
        assert 'copy-in' in args
