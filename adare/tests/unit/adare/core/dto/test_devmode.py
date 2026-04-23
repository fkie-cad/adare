from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

from datetime import datetime

from adare.core.dto.devmode import (
    DevActionResult,
    DevCheckpointInfo,
    DevCleanupResult,
    DevPlaybookResult,
    DevResetResult,
    DevSessionStartRequest,
    DevSessionStopRequest,
)


class TestDevSessionStartRequest:
    def test_defaults(self):
        req = DevSessionStartRequest(
            project_path=Path("/p"), environment_name="env1",
        )
        assert req.gui_mode is None
        assert req.vm_memory is None
        assert req.debug_screenshots is False
        assert req.shared_directories is None

    def test_full_construction(self):
        req = DevSessionStartRequest(
            project_path=Path("/p"), environment_name="env1",
            gui_mode="headless", vm_memory=4096, vm_cpus=2,
            debug_screenshots=True, console_ulid="abc",
        )
        assert req.vm_memory == 4096
        assert req.vm_cpus == 2


class TestDevSessionStopRequest:
    def test_construction(self):
        req = DevSessionStopRequest(session_id="s1", remove_resources=True)
        assert req.remove_resources is True


class TestDevActionResult:
    def test_construction(self):
        r = DevActionResult(success=True, message="done", execution_time=1.5)
        assert r.coordinates is None
        assert r.data is None


class TestDevPlaybookResult:
    def test_construction(self):
        r = DevPlaybookResult(
            success=True, total_actions=10,
            successful_actions=9, failed_actions=1,
            execution_time=30.0,
        )
        assert r.action_results == []
        assert r.error_message is None


class TestDevCheckpointInfo:
    def test_construction(self):
        now = datetime.now()
        info = DevCheckpointInfo(name="cp1", description="base", created_at=now)
        assert info.variable_count == 0
        assert info.file_size_mb == 0.0


class TestDevResetResult:
    def test_construction(self):
        r = DevResetResult(success=True, reset_type="hard", execution_time=2.0, message="Reset complete")
        assert r.reset_type == "hard"


class TestDevCleanupResult:
    def test_construction(self):
        r = DevCleanupResult(sessions_removed=3, removed_session_ids=["a", "b", "c"])
        assert len(r.removed_session_ids) == 3
