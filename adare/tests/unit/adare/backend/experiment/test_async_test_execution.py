"""Tests for GuestToHostTestExecutor._run_test() async/sync handling.

Verifies that _run_test() correctly handles both sync and async test() methods
without triggering 'RuntimeError: This event loop is already running'.
"""


import pytest

pytestmark = pytest.mark.unit

from adare.backend.experiment.guest_to_host_test_executor import GuestToHostTestExecutor
from adarelib.constants import StatusEnum
from adarelib.event.event import TestResult

# ============================================================================
# Mock test instances (no attrs dependency needed — _run_test only calls .test())
# ============================================================================


class SyncTestInstance:
    def test(self):
        return TestResult(status=StatusEnum.SUCCESS, details=['sync test passed'])


class AsyncTestInstance:
    async def test(self):
        return TestResult(status=StatusEnum.SUCCESS, details=['async test passed'])


class FailingTestInstance:
    def test(self):
        raise ValueError("test failure")


class AsyncFailingTestInstance:
    async def test(self):
        raise ValueError("async test failure")


# ============================================================================
# Fixtures
# ============================================================================


@pytest.fixture
def executor():
    """Create a GuestToHostTestExecutor with mocked dependencies.

    Only _run_test() is under test, so the proxies are irrelevant.
    """
    from unittest.mock import MagicMock
    return GuestToHostTestExecutor(
        guest_file=MagicMock(),
        guest_command=MagicMock(),
        testfunction_collection={},
    )


# ============================================================================
# Tests
# ============================================================================


@pytest.mark.asyncio
async def test_run_test_sync_returns_test_result(executor):
    """_run_test() runs sync test methods via asyncio.to_thread() and returns TestResult."""
    result = await executor._run_test(SyncTestInstance())

    assert isinstance(result, TestResult)
    assert result.status == StatusEnum.SUCCESS
    assert result.details == ['sync test passed']


@pytest.mark.asyncio
async def test_run_test_async_returns_test_result(executor):
    """_run_test() correctly awaits async test methods and returns TestResult."""
    result = await executor._run_test(AsyncTestInstance())

    assert isinstance(result, TestResult)
    assert result.status == StatusEnum.SUCCESS
    assert result.details == ['async test passed']


@pytest.mark.asyncio
async def test_run_test_sync_propagates_exceptions(executor):
    """_run_test() propagates exceptions from sync tests."""
    with pytest.raises(ValueError, match="test failure"):
        await executor._run_test(FailingTestInstance())


@pytest.mark.asyncio
async def test_run_test_async_propagates_exceptions(executor):
    """_run_test() propagates exceptions from async tests."""
    with pytest.raises(ValueError, match="async test failure"):
        await executor._run_test(AsyncFailingTestInstance())


@pytest.mark.asyncio
async def test_no_event_loop_runtime_error(executor):
    """Calling _run_test() from an async context does not raise RuntimeError.

    The old _run_test_sync() used asyncio.get_event_loop().run_until_complete()
    which would raise 'RuntimeError: This event loop is already running' when
    called from within an already-running event loop (i.e., from any async method).
    The new _run_test() avoids this by using await and asyncio.to_thread().
    """
    # This test itself runs in an async context (pytest-asyncio).
    # If _run_test used run_until_complete(), this would raise RuntimeError.
    sync_result = await executor._run_test(SyncTestInstance())
    async_result = await executor._run_test(AsyncTestInstance())

    assert sync_result.status == StatusEnum.SUCCESS
    assert async_result.status == StatusEnum.SUCCESS
