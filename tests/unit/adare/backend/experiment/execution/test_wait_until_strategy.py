
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
async def test_wait_until_strategy_once_latch(executor):
    """Test 'once' strategy: once constraint matches, it is ignored subsequent times"""
    # Setup action with skip.pixel_change.below = 5.0 and strategy = 'once'
    action = WaitUntilAction(
        condition=WaitCondition(exists=Target(image="test.png")),
        timeout=1.0,
        check_interval=0.1,
        initial_delay=0,
        skip=SkipOptions(pixel_change=PixelChangeConstraint(below=5.0, strategy='once'))
    )

    # 1. First screen (baseline)
    # 2. Second (0.1 < 5.0) -> Skip
    # 3. Third (10.0 > 5.0) -> Pass -> Latch
    # 4. Fourth (0.1 < 5.0) -> Pass (because latched) -> Check Condition -> Success
    
    executor.target_resolution.get_current_screenshot_with_path.side_effect = [
        ("base64_img1", "path1"),
        ("base64_img2", "path2"),
        ("base64_img3", "path3"),
        ("base64_img4", "path4"),
        ("base64_img4", "path4"),
    ]

    with patch('adare.backend.experiment.execution.flow_control.calculate_pixel_change') as mock_calc:
        # Check 1: No prev
        # Check 2: 0.1 < 5.0 (Skip)
        # Check 3: 10.0 > 5.0 (Pass, Latch)
        # Check 4: 0.1 (Would skip, but Latch prevents check)
        mock_calc.side_effect = [0.1, 10.0, 0.1]
        
        # Condition evaluation:
        # Check 1: Call (False) (No pixel check yet)
        # Check 2: Skip
        # Check 3: Call (False)
        # Check 4: Call (True)
        executor._evaluate_wait_condition = AsyncMock(side_effect=[False, False, True])

        result = await executor.execute_wait_until(action)

        assert result.success
        assert executor._evaluate_wait_condition.call_count == 3
        # calculate_pixel_change called for check 2 and 3. Not called for check 4 because latched strategies avoid calc if possible?
        # Wait, my implementation checks `if should_evaluate_pixel_constraint` before calc. 
        # So yes, it should NOT calculate for check 4.
        assert mock_calc.call_count == 2 


@pytest.mark.asyncio
async def test_wait_until_strategy_continuous(executor):
    """Test 'continuous' strategy: constraint is always enforced"""
    # Setup action with skip.pixel_change.below = 5.0 and strategy = 'continuous'
    action = WaitUntilAction(
        condition=WaitCondition(exists=Target(image="test.png")),
        timeout=1.0,
        check_interval=0.1,
        initial_delay=0,
        skip=SkipOptions(pixel_change=PixelChangeConstraint(below=5.0, strategy='continuous'))
    )

    # 1. First screen (baseline)
    # 2. Second (0.1 < 5.0) -> Skip
    # 3. Third (10.0 > 5.0) -> Pass
    # 4. Fourth (0.1 < 5.0) -> Skip (Enforced)
    # 5. Fifth (10.0 > 5.0) -> Pass -> Check Condition -> Success

    executor.target_resolution.get_current_screenshot_with_path.side_effect = [
        ("base64_img1", "path1"),
        ("base64_img2", "path_skip1"),
        ("base64_img3", "path_pass1"),
        ("base64_img4", "path_skip2"),
        ("base64_img5", "path_pass2"),
        ("base64_img5", "path_pass2"),
    ]

    with patch('adare.backend.experiment.execution.flow_control.calculate_pixel_change') as mock_calc:
        # Check 1: No prev
        # Check 2: 0.1 (Skip)
        # Check 3: 10.0 (Pass)
        # Check 4: 0.1 (Skip)
        # Check 5: 10.0 (Pass)
        mock_calc.side_effect = [0.1, 10.0, 0.1, 10.0]
        
        # Condition evaluation:
        # Check 1: Call (False)
        # Check 2: Skip
        # Check 3: Call (False)
        # Check 4: Skip
        # Check 5: Call (True)
        executor._evaluate_wait_condition = AsyncMock(side_effect=[False, False, True])

        result = await executor.execute_wait_until(action)

        assert result.success
        assert executor._evaluate_wait_condition.call_count == 3
        assert mock_calc.call_count == 4

@pytest.mark.asyncio
async def test_strategy_defaults_to_once():
    """Verify default strategy is 'once'"""
    constraint = PixelChangeConstraint()
    assert constraint.strategy == 'once'
