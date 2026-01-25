import pytest
from unittest.mock import MagicMock, patch, AsyncMock, mock_open
import asyncio
from pathlib import Path
import time
from adare.backend.devmode.recorder import SessionRecorder
from adare.types.playbook import ClickAction, KeyboardAction

@pytest.fixture
def mock_vm():
    vm = MagicMock()
    vm.vm_name = "test-vm"
    vm.enable_input_tracing = AsyncMock(return_value=True)
    vm.disable_input_tracing = AsyncMock()
    # screen dimensions for click calculation
    vm._screen_width = 1920
    vm._screen_height = 1080
    return vm

@pytest.fixture
def recorder(mock_vm):
    return SessionRecorder(mock_vm, Path("/tmp/playbook.yml"))

class TestSessionRecorder:

    @pytest.mark.asyncio
    async def test_start_success(self, recorder, mock_vm):
        # Act
        await recorder.start()
        
        # Assert
        assert recorder.is_recording is True
        mock_vm.enable_input_tracing.assert_called_once()
        assert recorder._task is not None
        
        # Cleanup
        await recorder.stop()

    @pytest.mark.asyncio
    async def test_start_fail(self, recorder, mock_vm):
        mock_vm.enable_input_tracing.return_value = False
        
        with pytest.raises(RuntimeError, match="Failed to enable QEMU input tracing"):
            await recorder.start()
            
        assert recorder.is_recording is False

    @pytest.mark.asyncio
    async def test_process_log_line_click(self, recorder):
        # Setup state
        recorder._current_x = 0
        recorder._current_y = 0
        recorder._max_x = 100
        recorder._max_y = 100
        recorder.vm._screen_width = 100
        recorder.vm._screen_height = 100
        
        # Call handler directly to test logic, bypassing regex fragility
        await recorder._handle_btn_event("con 0 button 0 (left) down true")
        
        assert recorder._pending_click is not None
        assert recorder._actions[-1].description == "Context before action" # Screenshot taken
        
        # Simulate button up
        await recorder._handle_btn_event("con 0 button 0 (left) down false")
        
        # Should have added a ClickAction
        assert isinstance(recorder._actions[-1], ClickAction)
        assert recorder._actions[-1].type == "left"

    @pytest.mark.asyncio
    async def test_process_log_line_key(self, recorder):
        line = "123@1.0:input_event_key_qcode con 0 qcode 30 (a) down true"
        await recorder._process_log_line(line)
        
        assert isinstance(recorder._actions[-1], KeyboardAction)
        assert recorder._actions[-1].key == "a"

    @pytest.mark.asyncio
    async def test_stop_saves_playbook(self, recorder, mock_vm):
        recorder.is_recording = True
        # Create a real task that finishes immediately
        async def dummy_task(): pass
        recorder._task = asyncio.create_task(dummy_task())
        
        with patch('builtins.open', mock_open()) as mock_file:
            with patch('yaml.dump') as mock_yaml:
                await recorder.stop()
                
                assert recorder.is_recording is False
                mock_vm.disable_input_tracing.assert_called_once()
                mock_file.assert_called_with(Path("/tmp/playbook.yml"), 'w')
                mock_yaml.assert_called_once()
