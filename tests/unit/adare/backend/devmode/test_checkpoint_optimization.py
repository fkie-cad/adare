
import pytest
from unittest.mock import MagicMock, patch, AsyncMock
from pathlib import Path
from adare.backend.devmode.manager import DevModeSessionManager
from adare.backend.devmode.session import DevModeSession

@pytest.fixture
def manager():
    # managers are singletons, so we need to reset the instance for each test
    DevModeSessionManager._instance = None
    mgr = DevModeSessionManager()
    yield mgr
    DevModeSessionManager._instance = None

@pytest.fixture
def mock_session():
    session = MagicMock(spec=DevModeSession)
    session.start = AsyncMock(return_value=True)
    session.shutdown = AsyncMock()
    session.stop_and_remove = AsyncMock()
    return session

class TestCheckpointOptimization:
    
    @patch('adare.database.api.devmode.DevModeApi')
    @patch('adare.backend.devmode.manager.is_vm_running')
    @patch('adare.backend.devmode.manager.restore_context')
    @patch('adare.backend.environment.database.resolve_environment_identifier')
    @patch('adare.backend.environment.database.get_environment_hypervisor')
    @pytest.mark.asyncio
    async def test_restore_session_skip_websocket(
        self, mock_get_hypervisor, mock_resolve_env, mock_restore_ctx, 
        mock_is_vm_running, mock_db_api_cls, manager
    ):
        # Arrange
        session_id = 'restored-session-no-ws'
        db_api = MagicMock()
        mock_db_api_cls.return_value = db_api
        
        db_session = MagicMock()
        db_session.status = 'running'
        db_session.project_path = '/tmp/proj'
        db_session.environment_name = 'env'
        db_session.vm_name = 'vm-1'
        db_api.get_session.return_value = db_session
        
        mock_is_vm_running.return_value = True
        mock_restore_ctx.return_value = True
        
        # Test connect_websocket=False
        # We patch sys.modules to detect if import is attempted
        with patch.dict('sys.modules', {'adare.backend.experiment.websocket_client': MagicMock()}) as patched_modules:
             MockClientModule = patched_modules['adare.backend.experiment.websocket_client']
             
             # Act
             session = await manager.restore_session(session_id, connect_websocket=False)
        
             # Assert
             assert session is not None
             # The module should NOT have been accessed/imported for Client if we skipped it
             # But since we patched it, we can't easily check 'import'.
             # Instead, we can check if AdareVMClient was instantiated.
             # Wait, if we patch sys.modules, the import line `from ... import AdareVMClient` 
             # will get the mock from our patched modules.
             
             # Let's verify AdareVMClient was NOT instantiated
             MockClientModule.AdareVMClient.assert_not_called()

    @patch('adare.database.api.devmode.DevModeApi')
    @patch('adare.backend.devmode.manager.is_vm_running')
    @patch('adare.backend.devmode.manager.restore_context')
    @patch('adare.backend.environment.database.resolve_environment_identifier')
    @patch('adare.backend.environment.database.get_environment_hypervisor')
    @pytest.mark.asyncio
    async def test_restore_session_with_websocket(
        self, mock_get_hypervisor, mock_resolve_env, mock_restore_ctx, 
        mock_is_vm_running, mock_db_api_cls, manager
    ):
        # Arrange
        session_id = 'restored-session-ws'
        db_api = MagicMock()
        mock_db_api_cls.return_value = db_api
        
        db_session = MagicMock()
        db_session.status = 'running'
        db_session.project_path = '/tmp/proj'
        db_session.environment_name = 'env'
        db_session.vm_name = 'vm-1'
        db_api.get_session.return_value = db_session
        
        mock_is_vm_running.return_value = True
        mock_restore_ctx.return_value = True
        
        # Act
        # We patch the module to verify interaction
        mock_client_module = MagicMock()
        mock_client_class = MagicMock()
        mock_client_instance = AsyncMock()
        # setup connection return
        mock_client_instance.reconnect.return_value = True
        mock_client_instance.connect.return_value = True
        mock_client_class.return_value = mock_client_instance
        mock_client_module.AdareVMClient = mock_client_class
        
        # We also need to mock session.experiment_ctx which is created inside restore_context
        # But restore_context is mocked.
        # Wait, manager.restore_session creates DevModeSession BEFORE calling restore_context.
        # So we can spy on DevModeSession constructor or just check the returned session.
        # However, restore_session logic accesses session.experiment_ctx which is populated by restore_context.
        # Since restore_context is mocked, session.experiment_ctx might be missing or empty?
        # restore_session calls: session = DevModeSession(...)
        # then success = await restore_context(session, ...)
        # calling mocked restore_context(session, ...)
        # The mock doesn't populate session!
        
        # So we need the side_effect of mock_restore_ctx to populate session
        def populate_session(session, *args, **kwargs):
            session.experiment_ctx = MagicMock()
            session.experiment_ctx.hypervisor_type = 'qemu'
            session.experiment_ctx.vm = MagicMock()
            # mock vm methods needed for ws connection
            session.experiment_ctx.vm.list_port_forwarding_rules = AsyncMock(return_value={
                'adarevm': MagicMock(host_port=12345, guest_port=18765)
            })
            # mock qemu process check
            session.experiment_ctx.vm._qemu_process = MagicMock()
            session.experiment_ctx.vm._qemu_process.poll.return_value = None
            
            session.playbook_controller = MagicMock()
            return True
            
        mock_restore_ctx.side_effect = populate_session

        with patch.dict('sys.modules', {'adare.backend.experiment.websocket_client': mock_client_module}):
             session = await manager.restore_session(session_id, connect_websocket=True)
        
             # Assert
             assert session is not None
             # Verify AdareVMClient WAS instantiated
             mock_client_class.assert_called_once_with(port=12345)
