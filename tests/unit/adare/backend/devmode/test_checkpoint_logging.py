
import pytest
from unittest.mock import MagicMock, patch, AsyncMock
from pathlib import Path
from adare.backend.devmode.session import DevModeSession

class TestCheckpointLogging:
    @pytest.fixture
    def session(self):
        return DevModeSession(
            session_id="test-session-id",
            project_path=Path("/tmp/test-project"),
            environment_name="test-env",
            experiment_name="test-experiment"
        )
    
    @patch.object(DevModeSession, '_create_dev_snapshot')
    @patch.object(DevModeSession, '_command_logger')
    @pytest.mark.asyncio
    async def test_create_checkpoint_no_extra_log(
        self, mock_command_logger, mock_create_snapshot, session
    ):
        # Arrange
        session.is_running = True
        session.experiment_ctx = MagicMock()
        session.experiment_ctx.experiment_run_directory.log_directory = Path("/tmp/logs")
        
        # Verify that _write_checkpoint_log does not exist on the session object
        assert not hasattr(session, '_write_checkpoint_log'), "_write_checkpoint_log method should have been removed"
        
        # Mock successful snapshot creation
        mock_create_snapshot.return_value = None
        
        # Act
        result = await session.create_checkpoint("test-checkpoint", "description")
        
        # Assert
        assert result is True
        mock_command_logger.assert_called_with("checkpoint_create_test-checkpoint")
        mock_create_snapshot.assert_called_with("test-checkpoint", "description")

    @patch('adare.database.api.devmode.DevModeApi')
    @patch.object(DevModeSession, '_command_logger')
    @pytest.mark.asyncio
    async def test_restore_checkpoint_no_extra_log(
        self, mock_command_logger, mock_api_cls, session
    ):
        # Arrange
        session.is_running = True
        session.experiment_ctx = MagicMock()
        # Mock hypervisor type to skip complex logic that requires more mocks
        session.experiment_ctx.hypervisor_type = 'qemu' 
        # But wait, restore_checkpoint calls restore_external_snapshot which we would need to mock
        # Let's mock vm instead
        session.experiment_ctx.vm = MagicMock()
        session.experiment_ctx.vm.restore_external_snapshot.return_value = True
        
        # Mock client for disconnect
        session.experiment_ctx.client = MagicMock()
        session.experiment_ctx.client.disconnect = AsyncMock()
        
        # Mock playbook controller
        session.playbook_controller = MagicMock()
        session.playbook_controller.execution_context = {}

        # Mock wait_for_vm_ready
        session._wait_for_vm_ready_after_restore = AsyncMock()
        # Mock websocket connect
        with patch('adare.backend.experiment.run.step_connect_websocket', new=AsyncMock()):
            with patch('adare.backend.devmode.session.StageCtxManager'):
                # Mock API return
                mock_api = mock_api_cls.return_value.__enter__.return_value
                mock_checkpoint = MagicMock()
                mock_checkpoint.checkpoint_id = "test-id"
                mock_checkpoint.snapshot_name = "test-snap"
                mock_api.get_checkpoint.return_value = mock_checkpoint
                
                # Mock snapshots list to avoid finding one
                session.snapshots = []

                # Act
                result = await session.restore_checkpoint("test-checkpoint")

                # Assert
                assert result is True
                mock_command_logger.assert_called_with("checkpoint_restore_test-checkpoint")
                
                # Verify no other file writing logic is triggered (implicit by code inspection but good to know test passes)
                # And since we removed _write_checkpoint_log, we know it can't be called.
        
        # Verify we didn't crash trying to call the removed method
        # If the method call wasn't removed, this test would fail with AttributeError during execution
        # or we'd see a mock call if we had mocked it (which we didn't, intentionally)
