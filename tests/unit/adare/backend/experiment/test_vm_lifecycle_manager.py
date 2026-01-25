
import pytest
from unittest.mock import MagicMock, patch, AsyncMock
from pathlib import Path

from adare.backend.experiment.vm_lifecycle_manager import VMLifecycleManager
from adare.backend.experiment.runctx import ExperimentRunCtx
from adare.backend.experiment.directory import ExperimentRunDirectory

@pytest.fixture
def manager():
    with patch('adare.hypervisor.qemu.lifecycle.QEMULifecycleStrategy') as mock_strat:
        # We need to mock the strategy class instantiation inside __init__
        return VMLifecycleManager(hypervisor_type='qemu')

@pytest.fixture
def run_ctx():
    ctx = MagicMock(spec=ExperimentRunCtx)
    ctx.vm = MagicMock()
    ctx.experiment_run_ulid = "run_123"
    ctx.user_interrupt_event = MagicMock()
    ctx.config = MagicMock()
    ctx.config.preserve_snapshot = False
    return ctx

class TestVMLifecycleManager:

    @patch('adare.backend.experiment.vm_lifecycle_manager.experiment_database')
    @patch('adare.backend.experiment.vm_lifecycle_manager.environment_database')
    @patch('adare.backend.experiment.vm_lifecycle_manager.StageCtxManager')
    def test_start_vm(self, mock_stage, mock_env_db, mock_exp_db, manager, run_ctx):
        # Setup
        manager.strategy = AsyncMock() # Mock the strategy instance
        
        # Act
        import asyncio
        asyncio.run(manager.start_vm(run_ctx))
        
        # Assert
        manager.strategy.start_and_initialize_vm.assert_called_once_with(run_ctx)

    @patch('adare.backend.experiment.vm_lifecycle_manager.StageCtxManager')
    def test_stop_vm(self, mock_stage, manager, run_ctx):
        # Setup
        run_ctx.vm.stop = AsyncMock()
        
        # Act
        import asyncio
        asyncio.run(manager.stop_vm(run_ctx))
        
        # Assert
        run_ctx.vm.stop.assert_called_once()
        
    @patch('adare.backend.experiment.vm_lifecycle_manager.StageCtxManager')
    def test_cleanup_vm(self, mock_stage, manager, run_ctx):
        # Setup
        manager.strategy = AsyncMock()
        run_ctx.vm.cleanup_overlay_disk = AsyncMock()
        
        # Mocks for _release_vm_instance
        with patch.object(manager, '_release_vm_instance', new_callable=AsyncMock) as mock_release:
            import asyncio
            asyncio.run(manager.cleanup_vm(run_ctx))
            
            # Assert
            manager.strategy.cleanup_vm.assert_called_once()
            run_ctx.vm.cleanup_overlay_disk.assert_called()
            mock_release.assert_called_once()
