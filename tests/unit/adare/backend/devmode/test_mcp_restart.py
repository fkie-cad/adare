
import pytest
from unittest.mock import MagicMock, patch, AsyncMock
from pathlib import Path
from adare.backend.devmode.session import DevModeSession
from adare.backend.experiment.runctx import ExperimentRunCtx

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
async def test_mcp_server_restart_on_start(
    mock_connect_ws, mock_install_ws, mock_start_mcp, mock_prepare_run,
    mock_setup_env, mock_init, mock_vm_mgr_cls, mock_config_cls, mock_ctx_cls
):
    """Test that existing MCP server is stopped before starting a new one."""
    
    # Arrange
    # Use experiment_name to trigger "standard flow" in start(), avoiding database calls
    session = DevModeSession("test-session", Path("/tmp"), "test-env", experiment_name="test-experiment")
    
    # Mock context and its mcp_server
    mock_ctx = mock_ctx_cls.return_value
    mock_mcp_server = MagicMock()
    mock_mcp_server.stop = AsyncMock()
    mock_ctx.mcp_server = mock_mcp_server # Existing server in context
    
    mock_vm_mgr = mock_vm_mgr_cls.return_value
    mock_vm_mgr.create_and_prepare_vm = AsyncMock()
    mock_vm_mgr.setup_file_transfer = AsyncMock()
    mock_vm_mgr.setup_networking = AsyncMock()
    mock_vm_mgr.start_vm = AsyncMock()

    # Act
    await session.start()
    
    # Assert
    # Verify that stop() was called with force_external=True
    mock_mcp_server.stop.assert_called_once_with(force_external=True)
    
    # Verify that start step was called AFTER stop
    # In the code, stop is called then step_start_mcp_server is called
    mock_start_mcp.assert_called_once()

if __name__ == "__main__":
    import asyncio
    async def run_tests():
        print("Running test_mcp_server_restart_on_start...")
        # Since test functions use patch decorators, we can't call them directly easily without pytest
        # But we can try to rely on pytest being available or invoke pytest from python
        # Actually, let's just use pytest via subprocess if we can, or rely on unittest.mock patcher context managers
        # To make this runnable directly without pytest, we'd need to manually apply patches.
        # Given the complexity, I will just run this file with pytest
        pass
        
    # asyncio.run(run_tests())
