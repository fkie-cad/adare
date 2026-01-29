
import sys
from unittest.mock import MagicMock, AsyncMock
from enum import IntEnum

# Mock adarelib before importing adare modules
mock_adarelib = MagicMock()
class StatusEnum(IntEnum):
    SUCCESS = 0
    FAILED = 1
    SKIPPED = 2
    NONE = 3
    FINISHED = 4

mock_adarelib.constants.StatusEnum = StatusEnum
sys.modules['adarelib'] = mock_adarelib
sys.modules['adarelib.helper'] = mock_adarelib
sys.modules['adarelib.helper.yaml'] = mock_adarelib
sys.modules['adarelib.constants'] = mock_adarelib
sys.modules['adarelib.constants'].StatusEnum = StatusEnum
sys.modules['adarelib.common'] = mock_adarelib
sys.modules['adarelib.common.variables'] = mock_adarelib
sys.modules['adarelib.testset'] = mock_adarelib
sys.modules['adarelib.testset.type'] = mock_adarelib

import pytest
from adare.backend.experiment.execution.target_resolution import TargetResolutionExecutor
from adare.backend.experiment.target_resolver import TargetMatch
from adare.types.playbook import Target, Offset

@pytest.fixture
def mock_resolver():
    resolver = AsyncMock()
    return resolver

@pytest.fixture
def mock_client():
    client = AsyncMock()
    client.screenshot.return_value = {'image': {'data': 'base64data'}}
    return client

@pytest.fixture
def executor(mock_client, mock_resolver):
    executor = TargetResolutionExecutor(mock_client, mock_resolver, experiment_run_id="test_run")
    executor.get_current_screenshot_with_path = AsyncMock(return_value=('base64data', 'path/to/screenshot.png'))
    return executor

@pytest.mark.asyncio
async def test_offset_center_right_with_region(executor, mock_resolver):
    # Setup: User scenario
    # Target "Help" text. 
    # Assume center at (100, 100), Width 60, Height 20.
    # Region Top-Left: (100-30, 100-10) = (70, 90). W=60, H=20.
    # Center-Right Anchor: X = 70 + 60 = 130. Y = 90 + 20//2 = 100.
    # Offset: x=30.
    # Expected Final: (130 + 30, 100) = (160, 100).
    
    target = Target(text="Help", offset=Offset(x=30, y=0, base='center-right'))
    match = TargetMatch(
        coordinates=(100, 100), 
        confidence=0.9, 
        method='text', 
        region=(70, 90, 60, 20)
    )
    mock_resolver.resolve_target.return_value = match
    
    # Execute
    coords = await executor.resolve_target_with_steps(target)
    
    # Verify
    assert coords == (160, 100)

@pytest.mark.asyncio
async def test_offset_center_default_with_region(executor, mock_resolver):
    # Setup
    target = Target(text="Submit", offset=Offset(x=10, y=20))
    match = TargetMatch(
        coordinates=(100, 100), 
        confidence=0.9, 
        method='text', 
        region=(70, 90, 60, 20) # Center is (100, 100)
    )
    mock_resolver.resolve_target.return_value = match
    
    # Execute
    coords = await executor.resolve_target_with_steps(target)
    
    # Verify
    # Center (100, 100) + Offset (10, 20) = (110, 120)
    assert coords == (110, 120)

@pytest.mark.asyncio
async def test_offset_top_left_with_region(executor, mock_resolver):
    # Setup
    target = Target(text="Submit", offset=Offset(x=5, y=5, base='top-left'))
    match = TargetMatch(
        coordinates=(100, 100), 
        confidence=0.9, 
        method='text', 
        region=(70, 90, 60, 20) # Top-Left (70, 90)
    )
    mock_resolver.resolve_target.return_value = match
    
    # Execute
    coords = await executor.resolve_target_with_steps(target)
    
    # Verify
    # Top-Left (70, 90) + Offset (5, 5) = (75, 95)
    assert coords == (75, 95)
