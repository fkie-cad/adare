from unittest.mock import AsyncMock, MagicMock

import pytest

pytestmark = pytest.mark.unit

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

    # 1. Simulate a wait_until exists check caching a match at the current
    # resolution generation (as flow_control does after begin_resolution()).
    match = await target_resolver.resolve_target(target, "fake_screenshot")
    executor.cache_match(target, match, "path/to/screenshot.png")

    # 2. Simulate the next target-resolution attempt beginning.
    executor.begin_resolution()

    # Verify it is in cache for that immediately-following attempt
    cached_result, cached_path, age = executor.get_cached_match(target)
    assert cached_result is not None
    assert cached_result.coordinates == (100, 200)
    assert cached_path == "path/to/screenshot.png"
    assert age < 1.0

@pytest.mark.asyncio
async def test_resolve_uses_cache_automatically(mock_dependencies):
    """Default (use_cache unset) auto-reuses a match from the immediately
    preceding target-resolution attempt - no opt-in flag required."""
    client, target_resolver = mock_dependencies
    executor = TargetResolutionExecutor(client, target_resolver)

    target = Target(image="button.png", strategy=BestConfidenceStrategy())

    # 1. Pre-populate cache (as if a wait_until exists check just ran)
    mock_match = MagicMock()
    mock_match.coordinates = (150, 250)
    executor.cache_match(target, mock_match, "path/to/screenshot.png")

    # 2. Call resolve_target_with_steps (simulates the very next ClickAction)
    target_resolver.resolve_target.reset_mock()

    result = await executor.resolve_target_with_steps(target)

    # 3. Verify result is from cache
    assert result == (150, 250)

    # 4. Verify expensive resolver was NOT called
    target_resolver.resolve_target.assert_not_called()
    # Verify we didn't take a new screenshot either
    client.screenshot.assert_not_called()

@pytest.mark.asyncio
async def test_resolve_opt_out_with_use_cache_false(mock_dependencies):
    """Explicit use_cache: false forces fresh detection even though the
    cached match is otherwise valid for this resolution generation."""
    client, target_resolver = mock_dependencies
    executor = TargetResolutionExecutor(client, target_resolver)

    target = Target(image="button.png", strategy=BestConfidenceStrategy(), use_cache=False)

    # 1. Pre-populate cache (as if a wait_until exists check just ran)
    mock_match = MagicMock()
    mock_match.coordinates = (300, 400)
    executor.cache_match(target, mock_match, "path/to/screenshot.png")

    # 2. Call resolve
    target_resolver.resolve_target.reset_mock()
    new_match = MagicMock()
    new_match.coordinates = (350, 450)
    new_match.region = (0, 0, 0, 0)
    target_resolver.resolve_target.return_value = new_match

    result = await executor.resolve_target_with_steps(target)

    # 3. Verify the cache was bypassed and fresh detection ran
    assert result == (350, 450)
    target_resolver.resolve_target.assert_called_once()

@pytest.mark.asyncio
async def test_resolve_skips_stale_cache(mock_dependencies):
    """A cache entry is dropped once another target-resolution attempt has
    happened in between - it's only valid for the immediately-next attempt."""
    client, target_resolver = mock_dependencies
    executor = TargetResolutionExecutor(client, target_resolver)

    target = Target(image="button.png", strategy=BestConfidenceStrategy())
    # No use_cache override

    # 1. Populate cache at the current generation
    mock_match = MagicMock()
    mock_match.coordinates = (500, 600)
    executor.cache_match(target, mock_match, "stale/path.png")

    # 2. Simulate an intervening target-resolution attempt (e.g. another
    # wait_until exists/not_exists check) that consumes the next generation
    # slot without hitting this cache entry.
    executor.begin_resolution()

    # 3. Call resolve for the original target - this is now two attempts
    # after the one that cached the match, so it must miss and fall back.
    target_resolver.resolve_target.reset_mock()
    new_match = MagicMock()
    new_match.coordinates = (550, 650)
    new_match.region = (0, 0, 0, 0)
    target_resolver.resolve_target.return_value = new_match

    result = await executor.resolve_target_with_steps(target)

    # 4. Verify it did NOT use the stale cache
    assert result == (550, 650)
    target_resolver.resolve_target.assert_called_once()
