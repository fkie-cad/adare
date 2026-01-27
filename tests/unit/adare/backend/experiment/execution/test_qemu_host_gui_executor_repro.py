import pytest
from unittest.mock import MagicMock, AsyncMock, call
import asyncio
from adare.backend.experiment.execution.qemu_host_gui_executor import QEMUHostGUIExecutor

@pytest.mark.asyncio
async def test_keyboard_type_special_characters():
    """
    Test that keyboard type action correctly handles special characters like ':'
    that require shift key.
    """
    # Mock VM
    vm_mock = MagicMock()
    vm_mock.send_qmp_keyboard = AsyncMock(return_value=True)
    
    # Initialize executor
    executor = QEMUHostGUIExecutor(vm=vm_mock)
    
    # Test typing a string with a colon
    # "a:b" -> 'a' (no shift), ':' (shift+;), 'b' (no shift)
    await executor.keyboard("type", "a:b")
    
    # Verify calls
    assert vm_mock.send_qmp_keyboard.called
    
    # Get all calls to send_qmp_keyboard
    # calls = vm_mock.send_qmp_keyboard.call_args_list
    # For now, let's just inspect the logic we want to reproduce as failing or succeeding
    # We expect separate calls or a batched call depending on implementation
    # The current implementation batches events per call to keyboard() but keys are processed in loop
    
    # Let's check the events generated
    # We can inspect the internal method _create_type_events to be more granular 
    events = executor._create_type_events(":")
    
    # Expected: Shift down, Semicolon down, Semicolon up, Shift up
    # Current (Broken): Will likely return empty or try to map ':' directly which fails
    
    print(f"\nGenerated events for ':': {events}")
    
    # Check if we have events
    assert len(events) > 0, "No events generated for ':'"
    
    # Check if we have shift modifier
    has_shift = False
    has_semicolon = False
    
    for event in events:
        if event.get("data", {}).get("key", {}).get("data") == "shift":
            has_shift = True
        if event.get("data", {}).get("key", {}).get("data") == "semicolon":
            has_semicolon = True
            
    assert has_shift, "Shift key not used for ':'"
    assert has_semicolon, "Semicolon key not used for ':'" 
