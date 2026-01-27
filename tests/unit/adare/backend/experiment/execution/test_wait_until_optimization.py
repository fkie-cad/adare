
import pytest
from unittest.mock import MagicMock, patch, AsyncMock
from adare.backend.experiment.execution.flow_control import FlowControlExecutor, ActionResult
from adare.types.playbook import WaitUntilAction, WaitCondition, ExistsCondition, Target, SkipOptions, PixelChangeConstraint

@pytest.fixture
def mock_deps():
    return {
        'websocket_client': MagicMock(),
        'target_resolution_executor': AsyncMock(),
        'condition_checker': AsyncMock(),
    }

@pytest.fixture
def executor(mock_deps):
    return FlowControlExecutor(**mock_deps)

@pytest.mark.asyncio
async def test_wait_until_pixel_change_skip_above(executor):
    """Test that check is skipped when pixel change is ABOVE threshold (stability check)"""
    # Setup action with skip.pixel_change.above = 0.1
    action = WaitUntilAction(
        condition=WaitCondition(exists=Target(image="test.png")),
        timeout=1.0,
        check_interval=0.1,
        initial_delay=0,
        skip=SkipOptions(pixel_change=PixelChangeConstraint(above=0.1))
    )

    # Mock screenshot series:
    # 1. First screen (baseline)
    # 2. Second screen (high change -> skip check)
    # 3. Third screen (low change -> perform check -> success)
    
    executor.target_resolution.get_current_screenshot_with_path.side_effect = [
        ("base64_img1", "path1"),
        ("base64_img2", "path2"),
        ("base64_img3", "path3"),
        ("base64_img3", "path3"), # Extra in case of timing
    ]

    # Mock pixel change calculation
    with patch('adare.backend.experiment.execution.flow_control.calculate_pixel_change') as mock_calc:
        # First check: No prev screen, so no calc. Condition gets checked.
        # Second check: img1 vs img2. Return 50.0 (> 0.1). SHOULD SKIP condition check.
        # Third check: img2 vs img3. Return 0.0 (< 0.1). Should check condition.
        mock_calc.side_effect = [50.0, 0.0, 0.0]
        
        # Mock condition evaluation
        # We expect it to be called for check 1 (no prev screen)
        # NOT called for check 2 (skipped)
        # Called for check 3 (success)
        executor._evaluate_wait_condition = AsyncMock(side_effect=[False, True]) 

        result = await executor.execute_wait_until(action)

        assert result.success
        assert "Condition satisfied" in result.message
        
        # calculate_pixel_change should have been called twice (for check 2 and 3)
        assert mock_calc.call_count >= 2
        
        # _evaluate_wait_condition should have been called only twice (skipped once)
        # If it wasn't skipped, it would be called 3 times (False, False, True)
        assert executor._evaluate_wait_condition.call_count == 2

@pytest.mark.asyncio
async def test_wait_until_pixel_change_skip_below(executor):
    """Test that check is skipped when pixel change is BELOW threshold (activity check)"""
    # Setup action with skip.pixel_change.below = 5.0
    action = WaitUntilAction(
        condition=WaitCondition(exists=Target(image="test.png")),
        timeout=1.0,
        check_interval=0.1,
        initial_delay=0,
        skip=SkipOptions(pixel_change=PixelChangeConstraint(below=5.0))
    )

    executor.target_resolution.get_current_screenshot_with_path.side_effect = [
        ("base64_img1", "path1"),
        ("base64_img2", "path2"),
        ("base64_img3", "path3"),
        ("base64_img3", "path3"),
    ]

    with patch('adare.backend.experiment.execution.flow_control.calculate_pixel_change') as mock_calc:
        # Check 1: No prev screen -> Check condition (False)
        # Check 2: Change 0.1 (< 5.0) -> SKIP condition check
        # Check 3: Change 10.0 (> 5.0) -> Check condition (True)
        mock_calc.side_effect = [0.1, 10.0, 10.0]
        
        executor._evaluate_wait_condition = AsyncMock(side_effect=[False, True])

        result = await executor.execute_wait_until(action)

        assert result.success
        
        # Verify skip happened
        assert executor._evaluate_wait_condition.call_count == 2
        assert mock_calc.call_count >= 2
