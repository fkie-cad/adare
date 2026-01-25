
import asyncio
import os
import time
import pytest
import yaml
from pathlib import Path
from unittest.mock import MagicMock, AsyncMock, patch
import sys

from adare.backend.devmode.recorder import SessionRecorder
from adare.hypervisor.qemu.vm import QEMUVM
from adare.types.playbook import ClickAction, KeyboardAction, ScreenshotAction

@pytest.mark.asyncio
async def test_session_recorder_parsing(tmp_path):
    # Setup
    log_file = tmp_path / "experiment.log"
    output_file = tmp_path / "playbook.yml"
    
    # Create empty log file
    log_file.touch()
    
    # Mock VM
    mock_vm = MagicMock(spec=QEMUVM)
    mock_vm.enable_input_tracing = AsyncMock(return_value=True)
    mock_vm.disable_input_tracing = AsyncMock(return_value=True)
    mock_vm.vm_name = "TestVM"
    # Mock screen resolution
    mock_vm._screen_width = 1920
    mock_vm._screen_height = 1080
    
    # Patch get_experiment_log_file to return our temp log file
    with patch('adare.backend.devmode.recorder.get_experiment_log_file', return_value=log_file):
        
        # Initialize Recorder
        recorder = SessionRecorder(mock_vm, output_file)
        
        # Start recording
        await recorder.start()
        
        # Give the recorder loop time to start and seek to EOF (which is 0 now)
        await asyncio.sleep(0.1)
        
        assert recorder.is_recording
        mock_vm.enable_input_tracing.assert_called_once()
        
        # Simulate QEMU/Libvirt Trace Log Entries
        # 1. Mouse Move (to set position)
        # 2. Mouse Click (Left Down)
        # 3. Mouse Click (Left Up)
        # 4. Key Press (A Down)
        # 5. Key Press (A Up)
        
        lines = [
            # Move to ~center (16383, 16383 roughly)
            "26428@1737803621.100000:input_event_abs con 0 axis 0 (x) value 16383\n",
            "26428@1737803621.100000:input_event_abs con 0 axis 1 (y) value 16383\n",
            
            # Click Left Button Down
            "26428@1737803622.200000:input_event_btn con 0 button 0 (left) down true\n",
            
            # Click Left Button Up
            "26428@1737803622.300000:input_event_btn con 0 button 0 (left) down false\n",
            
            # Key 'a' Down
            "26428@1737803623.400000:input_event_key_qcode con 0 qcode 30 (a) down true\n",
            
            # Key 'a' Up
            "26428@1737803623.500000:input_event_key_qcode con 0 qcode 30 (a) down false\n",
        ]
        
        # Write lines to log file with small delays to simulate stream
        with open(log_file, 'a') as f:
            for line in lines:
                f.write(line)
                f.flush()
                os.fsync(f.fileno())
                # await asyncio.sleep(0.01) 

        
        # Wait for recorder to process lines
        await asyncio.sleep(0.5)
        
        # Stop recording
        await recorder.stop()
        
        mock_vm.disable_input_tracing.assert_called_once()
        
        # Verify Output
        assert output_file.exists()
        
        with open(output_file, 'r') as f:
            data = yaml.safe_load(f)
            
        print(f"Generated Playbook:\n{yaml.dump(data)}")
        
        actions = data['actions']
        
        # Expected Actions:
        # 1. Idle (start to click) - skipped if < 1s but here timestamp diff is 1.1s (start=now vs log time?)
        #    Actually SessionRecorder uses time.time() for idle calculation, not log timestamps (yet).
        #    So idle actions might be 0 or small depending on test execution speed.
        
        # 2. Screenshot (before click)
        # 3. Click Left at ~960, 540 (16383/32767 * 1920/1080)
        # 4. Keyboard 'a'
        
        # We need to filter for specific types
        
        screenshots = [a for a in actions if 'screenshot' in a]
        clicks = [a for a in actions if 'click' in a]
        keyboards = [a for a in actions if 'keyboard' in a]
        
        assert len(screenshots) >= 1, "Should have screenshot before click"
        assert len(clicks) == 1
        assert len(keyboards) == 1
        
        # Verify Click
        click = clicks[0]['click']
        assert click['type'] == 'left'
        pos = click['target']['position']
        # 16383 / 32767 * 1920 ~= 959.9 => 959
        # 16383 / 32767 * 1080 ~= 539.9 => 539
        assert 950 <= pos[0] <= 970
        assert 530 <= pos[1] <= 550
        
        # Verify Keyboard
        kb = keyboards[0]['keyboard']
        assert kb['key'] == 'a'

if __name__ == "__main__":
    # Allow running directly
    import sys
    sys.exit(pytest.main([__file__]))
