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
async def test_wait_until_pixel_change_enforces_min_interval_when_initial_check_interval_low(executor):
    """Test that MIN_PIXEL_POLL_INTERVAL is enforced when skipping and check_interval is low"""
    # Setup action with low check_interval (0.1) and pixel skip
    action = WaitUntilAction(
        condition=WaitCondition(exists=Target(image="test.png")),
        timeout=1.0,
        check_interval=0.1,  # Less than MIN_PIXEL_POLL_INTERVAL (0.5)
        initial_delay=0,
        skip=SkipOptions(pixel_change=PixelChangeConstraint(above=0.1))
    )

    # Scenarios:
    # 1. First check: No prev screen. Normal sleep (0.1).
    # 2. Second check: High change -> Skip. Should force sleep 0.5.
    # 3. Third check: Low change -> Check condition -> Success.

    executor.target_resolution.get_current_screenshot_with_path.side_effect = [
        ("base64_img1", "path1"),
        ("base64_img2", "path2"),
        ("base64_img3", "path3"),
        ("base64_img3", "path3"),
    ]

    with patch('adare.backend.experiment.execution.flow_control.calculate_pixel_change') as mock_calc:
        # Check 1: N/A
        # Check 2: 50.0 > 0.1 -> SKIP
        # Check 3: 0.0 < 0.1 -> CHECK
        mock_calc.side_effect = [50.0, 0.0, 0.0]

        executor._evaluate_wait_condition = AsyncMock(side_effect=[False, True])

        # Spy on asyncio.sleep
        with patch('asyncio.sleep', new_callable=AsyncMock) as mock_sleep:
            result = await executor.execute_wait_until(action)

            assert result.success
            
            # Verify sleep calls
            # Call 1: 0.1s (normal interval after first check)
            # Call 2: 0.5s (forced min interval after skip)
            assert mock_sleep.call_count >= 2
            
            # arguments are floats, so check approximation or exact values
            # We expect at least one call with 0.5
            calls = [c.args[0] for c in mock_sleep.call_args_list]
            assert 0.5 in calls
            assert 0.1 in calls


@pytest.mark.asyncio
async def test_wait_until_pixel_change_respects_high_check_interval(executor):
    """Test that configured check_interval is used if it's higher than MIN_PIXEL_POLL_INTERVAL"""
    # Setup action with high check_interval (1.0)
    action = WaitUntilAction(
        condition=WaitCondition(exists=Target(image="test.png")),
        timeout=2.0,
        check_interval=1.0,  # Higher than 0.5
        initial_delay=0,
        skip=SkipOptions(pixel_change=PixelChangeConstraint(above=0.1))
    )

    executor.target_resolution.get_current_screenshot_with_path.side_effect = [
        ("base64_img1", "path1"),
        ("base64_img2", "path2"),
        ("base64_img3", "path3"),
    ]

    with patch('adare.backend.experiment.execution.flow_control.calculate_pixel_change') as mock_calc:
        # Skip validation triggers
        mock_calc.return_value = 50.0 # Always skip

        executor._evaluate_wait_condition = AsyncMock(return_value=False)
        
        # We need to let it timeout to checking multiple sleep calls
        # triggering timeout logic requires side effects or just check sleep values before return

        # Actually, let's just run it and check the sleeps until timeout
        # Using a shorter timeout/interval check for test speed
        action.timeout = 1.5 
        
        with patch('asyncio.sleep', new_callable=AsyncMock) as mock_sleep:
            result = await executor.execute_wait_until(action)
            
            assert not result.success # Timeout
            
            # Should have slept 1.0s each time, never 0.5s
            for call in mock_sleep.call_args_list:
                assert call.args[0] == 1.0

