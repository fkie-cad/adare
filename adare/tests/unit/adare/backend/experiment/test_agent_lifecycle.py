"""Tests for agent_lifecycle module extracted from run.py."""

import asyncio
import logging
import threading
from unittest.mock import AsyncMock, MagicMock

import pytest

from adare.backend.experiment.agent_lifecycle import _run_command_with_retry
from adare.backend.experiment.exceptions import VMSetupError


LOG = logging.getLogger("test_agent_lifecycle")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_vm(return_codes: list[int], stdout: str = "", stderr: str = ""):
    """Create a mock VM whose run_command returns the given return codes sequentially."""
    vm = MagicMock()
    vm.vm_name = "test-vm"

    results = []
    for rc in return_codes:
        result = MagicMock()
        result.returncode = rc
        result.stdout = stdout
        result.stderr = stderr
        results.append(result)

    vm.run_command = AsyncMock(side_effect=results)
    return vm


def _make_stop_event() -> threading.Event:
    return threading.Event()


# ---------------------------------------------------------------------------
# _run_command_with_retry
# ---------------------------------------------------------------------------

class TestRunCommandWithRetry:
    """Tests for the shared retry helper."""

    @pytest.mark.asyncio
    async def test_succeeds_on_first_attempt(self):
        """Command that succeeds immediately should return without retry."""
        vm = _make_vm([0], stdout="ok")
        stop_event = _make_stop_event()

        result = await _run_command_with_retry(
            vm, "echo hello", stop_event, label="test",
        )

        assert result.returncode == 0
        assert vm.run_command.call_count == 1

    @pytest.mark.asyncio
    async def test_retries_on_agent_failure_then_succeeds(self):
        """Command that fails with -1 (agent not responding) then succeeds on 2nd attempt."""
        vm = _make_vm([-1, 0])
        stop_event = _make_stop_event()

        result = await _run_command_with_retry(
            vm, "install pkg", stop_event,
            max_retries=3, initial_delay=0.01, label="install",
        )

        assert result.returncode == 0
        assert vm.run_command.call_count == 2

    @pytest.mark.asyncio
    async def test_raises_after_max_retries(self):
        """Should raise VMSetupError after exhausting all retries."""
        vm = _make_vm([-1, -1, -1])
        stop_event = _make_stop_event()

        with pytest.raises(VMSetupError):
            await _run_command_with_retry(
                vm, "failing cmd", stop_event,
                max_retries=3, initial_delay=0.01, label="failing",
            )

        assert vm.run_command.call_count == 3

    @pytest.mark.asyncio
    async def test_handles_timeout_with_retry(self):
        """asyncio.TimeoutError should trigger retry, not immediate failure."""
        vm = MagicMock()
        vm.vm_name = "test-vm"

        ok_result = MagicMock()
        ok_result.returncode = 0
        ok_result.stdout = ""
        ok_result.stderr = ""

        vm.run_command = AsyncMock(
            side_effect=[asyncio.TimeoutError("timed out"), ok_result]
        )
        stop_event = _make_stop_event()

        result = await _run_command_with_retry(
            vm, "slow cmd", stop_event,
            max_retries=3, initial_delay=0.01, label="slow",
        )

        assert result.returncode == 0
        assert vm.run_command.call_count == 2

    @pytest.mark.asyncio
    async def test_timeout_exhausted_raises(self):
        """Repeated timeouts should raise VMSetupError after max retries."""
        vm = MagicMock()
        vm.vm_name = "test-vm"
        vm.run_command = AsyncMock(side_effect=asyncio.TimeoutError("timed out"))
        stop_event = _make_stop_event()

        with pytest.raises(VMSetupError, match="Timeout after 2 attempts"):
            await _run_command_with_retry(
                vm, "timeout cmd", stop_event,
                max_retries=2, initial_delay=0.01, label="timeout",
            )

        assert vm.run_command.call_count == 2

    @pytest.mark.asyncio
    async def test_real_command_failure_fails_fast(self):
        """A non-zero, non -1 return code should fail immediately without retry."""
        vm = _make_vm([42], stderr="syntax error")
        stop_event = _make_stop_event()

        with pytest.raises(VMSetupError):
            await _run_command_with_retry(
                vm, "bad cmd", stop_event,
                max_retries=3, initial_delay=0.01, label="bad",
            )

        # Should fail on first attempt, not retry
        assert vm.run_command.call_count == 1
