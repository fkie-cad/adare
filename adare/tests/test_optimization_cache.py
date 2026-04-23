from unittest.mock import AsyncMock, MagicMock

import pytest

from adare.backend.experiment.execution.target_resolution import TargetResolutionExecutor
from adare.types.playbook import BestConfidenceStrategy, Target


@pytest.fixture
def mock_dependencies():
    client = AsyncMock()
    client.screenshot.return_value = {'image': {'data': 'fake_base64'}}

    target_resolver = AsyncMock()
    # Mock match result
    mock_match = MagicMock()
    mock_match.coordinates = (100, 200)
    mock_match.region = (80, 180, 40, 40)
    target_resolver.resolve_target.return_value = mock_match

    return client, target_resolver

@pytest.mark.asyncio
async def test_cache_storage_and_retrieval(mock_dependencies):
    client, target_resolver = mock_dependencies
    executor = TargetResolutionExecutor(client, target_resolver)

    # Define a target
    target = Target(image="button.png", strategy=BestConfidenceStrategy())

    # 1. Simulate "WaitUntil" - Manual caching or via flow control
    # But here we test the executors directly.
    # We call resolve_target directly first to populate cache?
    # Wait, resolve_target doesn't populate cache automatically (only flow control does)
    # UNLESS we manually call cache_match as flow control would.

    # Simulate resolution
    match = await target_resolver.resolve_target(target, "fake_screenshot")
    executor.cache_match(target, match, "path/to/screenshot.png")

    # Verify it is in cache
    cached_result, cached_path, age = executor.get_cached_match(target)
    assert cached_result is not None
    assert cached_result.coordinates == (100, 200)
    assert cached_path == "path/to/screenshot.png"
    assert age < 1.0

@pytest.mark.asyncio
async def test_resolve_uses_cache_heuristically(mock_dependencies):
    client, target_resolver = mock_dependencies
    executor = TargetResolutionExecutor(client, target_resolver)

    target = Target(image="button.png", strategy=BestConfidenceStrategy())

    # 1. Pre-populate cache (as if WaitUntil just ran)
    mock_match = MagicMock()
    mock_match.coordinates = (150, 250)
    executor.cache_match(target, mock_match, "path/to/screenshot.png")

    # 2. Call resolve_target_with_steps (Simulate ClickAction)
    # Reset mock to ensure it's NOT called
    target_resolver.resolve_target.reset_mock()

    result = await executor.resolve_target_with_steps(target)

    # 3. Verify result is from cache
    assert result == (150, 250)

    # 4. Verify expensive resolver was NOT called
    target_resolver.resolve_target.assert_not_called()
    # Verify we didn't take a new screenshot either
    client.screenshot.assert_not_called()

@pytest.mark.asyncio
async def test_resolve_uses_cache_explicitly(mock_dependencies):
    client, target_resolver = mock_dependencies
    executor = TargetResolutionExecutor(client, target_resolver)

    target = Target(image="button.png", strategy=BestConfidenceStrategy(), use_cache=True)

    # 1. Pre-populate cache OLDER than heuristic (e.g. manually set timestamp)
    mock_match = MagicMock()
    mock_match.coordinates = (300, 400)

    import time
    executor.last_match_cache[executor._get_target_hash(target)] = {
        'result': mock_match,
        'timestamp': time.time() - 10.0, # 10 seconds old (older than 5s heuristic)
        'screenshot_path': "old/path.png"
    }

    # 2. Call resolve
    target_resolver.resolve_target.reset_mock()
    result = await executor.resolve_target_with_steps(target)

    # 3. Verify result is from cache despite age, because use_cache=True
    assert result == (300, 400)
    target_resolver.resolve_target.assert_not_called()

@pytest.mark.asyncio
async def test_resolve_skips_stale_cache(mock_dependencies):
    client, target_resolver = mock_dependencies
    executor = TargetResolutionExecutor(client, target_resolver)

    target = Target(image="button.png", strategy=BestConfidenceStrategy())
    # No use_cache=True

    # 1. Pre-populate stale cache
    mock_match = MagicMock()
    mock_match.coordinates = (500, 600)

    import time
    executor.last_match_cache[executor._get_target_hash(target)] = {
        'result': mock_match,
        'timestamp': time.time() - 10.0, # Stale
        'screenshot_path': "stale/path.png"
    }

    # 2. Call resolve
    target_resolver.resolve_target.reset_mock()
    # Mock resolved result for NEW call
    new_match = MagicMock()
    new_match.coordinates = (550, 650)
    new_match.region = (0,0,0,0)
    target_resolver.resolve_target.return_value = new_match

    result = await executor.resolve_target_with_steps(target)

    # 3. Verify it did NOT use stale cache
    assert result == (550, 650)
    target_resolver.resolve_target.assert_called_once()
