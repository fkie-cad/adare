
import pytest
from unittest.mock import MagicMock, patch, AsyncMock
from pathlib import Path
from adare.backend.devmode.session import DevModeSession

@pytest.fixture
def session():
    return DevModeSession(
        session_id="test-session-id",
        project_path=Path("/tmp/test-project"),
        environment_name="test-env",
        experiment_name="test-experiment"
    )

class TestDevModeSession:

    def test_init(self, session):
        assert session.session_id == "test-session-id"
        assert session.environment_name == "test-env"
        assert session.is_running is False
        assert session.actions_executed == 0

    @patch('adare.backend.devmode.session.ExperimentRunCtx')
    @patch('adare.backend.devmode.session.ExperimentConfig')
    @patch('adare.backend.devmode.session.VMLifecycleManager')
    @patch('adare.backend.experiment.run.step_initialize')
    @patch('adare.backend.experiment.run.step_setup_experiment_environment')
    @patch('adare.backend.experiment.run.step_prepare_run_environment')
    @patch('adare.backend.experiment.run.step_start_mcp_server')
    @patch('adare.backend.experiment.run.step_install_and_run_websocket_server')
    @patch('adare.backend.experiment.run.step_connect_websocket')
    @pytest.mark.asyncio
    async def test_start_success(
        self, mock_connect_ws, mock_install_ws, mock_start_mcp, mock_prepare_run,
        mock_setup_env, mock_init, mock_vm_mgr_cls, mock_config_cls, mock_ctx_cls, session
    ):
        # Arrange
        mock_vm_mgr = mock_vm_mgr_cls.return_value
        mock_vm_mgr.create_and_prepare_vm = AsyncMock()
        mock_vm_mgr.setup_file_transfer = AsyncMock()
        mock_vm_mgr.setup_networking = AsyncMock()
        mock_vm_mgr.start_vm = AsyncMock()
        mock_vm_mgr.stop_vm = AsyncMock() # Fix await stop_vm

        mock_ctx = mock_ctx_cls.return_value
        mock_ctx.mcp_server.stop = AsyncMock() # Fix await mcp_server.stop
        mock_ctx.experiment_run_ulid = "test-run-id"
        mock_ctx.experiment_run_directory.log_directory = Path("/tmp")
        
        # Act
        result = await session.start()
        
        # Assert
        assert result is True
        assert session.is_running is True
        mock_init.assert_called_once()
        mock_setup_env.assert_called_once()
        mock_prepare_run.assert_called_once()
        mock_start_mcp.assert_called_once()
        
        mock_vm_mgr.create_and_prepare_vm.assert_called_once()
        mock_vm_mgr.start_vm.assert_called_once()
        
        mock_install_ws.assert_called_once()
        mock_connect_ws.assert_called_once()

    @pytest.mark.asyncio
    async def test_execute_action_not_running(self, session):
        result = await session.execute_action(MagicMock())
        assert result.success is False
        assert "Session not running" in result.message

    @patch('adare.backend.devmode.session.PlaybookController')
    @pytest.mark.asyncio
    async def test_execute_action_running(self, mock_controller_cls, session):
        # Arrange
        session.is_running = True
        session.experiment_ctx = MagicMock()
        session.experiment_ctx.project_directory.path = Path("/tmp")
        session.experiment_ctx.experiment_run_directory.screenshots_directory = Path("/tmp/screens")
        
        mock_controller = mock_controller_cls.return_value
        session.playbook_controller = mock_controller
        
        action_result = MagicMock()
        action_result.success = True
        mock_controller.action_executor.execute_action = AsyncMock(return_value=action_result)
        
        # Act
        action = MagicMock()
        result = await session.execute_action(action)
        
        # Assert
        assert result.success is True
        mock_controller.action_executor.execute_action.assert_called_once()
        assert session.actions_executed == 1

    @pytest.mark.asyncio
    async def test_reset_soft_no_snapshots(self, session):
        session.is_running = True
        session.snapshots = []
        result = await session.reset_soft()
        assert result is False

    @patch('adare.backend.devmode.session.StageCtxManager')
    @patch.object(DevModeSession, '_ensure_playbook_controller')
    @pytest.mark.asyncio
    async def test_reset_soft_qemu(self, mock_ensure_ctrl, mock_stage_mgr, session):
        # Arrange
        mock_ensure_ctrl.return_value = True
        session.is_running = True
        session.playbook_controller = MagicMock()
        
        snapshot = MagicMock()
        snapshot.snapshot_name = "initial"
        snapshot.variable_state = {}
        session.snapshots = [snapshot]
        
        session.experiment_ctx = MagicMock()
        session.experiment_ctx.hypervisor_type = 'qemu'
        session.experiment_ctx.client = AsyncMock() # WebSocket client
        
        # Act
        result = await session.reset_soft()
        
        # Assert
        assert result is True
        # Verify restore external snapshot call
        session.experiment_ctx.vm.restore_external_snapshot.assert_called_once()
        # Verify websocket disconnect/reconnect
        session.experiment_ctx.client.disconnect.assert_called_once()

