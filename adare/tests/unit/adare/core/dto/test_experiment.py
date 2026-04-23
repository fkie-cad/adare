from datetime import timedelta
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

from adare.core.dto.experiment import (
    BatchRunResultItem,
    BatchRunSummary,
    ExperimentCreateRequest,
    ExperimentRunResult,
    ExperimentValidateResult,
    ValidationCheckResult,
)


class TestExperimentCreateRequest:
    def test_construction(self):
        req = ExperimentCreateRequest(project_path=Path("/p"), name="exp1")
        assert req.name == "exp1"
        assert req.project_path == Path("/p")


class TestExperimentRunResult:
    def test_successful_run(self):
        result = ExperimentRunResult(
            was_interrupted=False, was_successful=True,
        )
        assert result.was_successful is True
        assert result.run_info is None
        assert result.error_message is None

    def test_failed_run(self):
        result = ExperimentRunResult(
            was_interrupted=False, was_successful=False,
            error_message="VM crashed",
        )
        assert result.error_message == "VM crashed"


class TestExperimentValidateResult:
    def test_empty_checks(self):
        vr = ExperimentValidateResult(name="exp")
        assert vr.passed_count == 0
        assert vr.failed_count == 0
        assert vr.warning_count == 0
        assert vr.is_valid is True

    def test_mixed_checks(self):
        checks = [
            ValidationCheckResult(name="c1", passed=True, message="ok"),
            ValidationCheckResult(name="c2", passed=False, message="fail"),
            ValidationCheckResult(name="c3", passed=False, message="warn", is_warning=True),
        ]
        vr = ExperimentValidateResult(name="exp", checks=checks)
        assert vr.passed_count == 1
        assert vr.failed_count == 1
        assert vr.warning_count == 1
        assert vr.is_valid is False

    def test_all_passing(self):
        checks = [
            ValidationCheckResult(name="c1", passed=True, message="ok"),
            ValidationCheckResult(name="c2", passed=True, message="ok"),
        ]
        vr = ExperimentValidateResult(name="exp", checks=checks)
        assert vr.is_valid is True


class TestBatchRunSummary:
    def test_construction(self):
        item = BatchRunResultItem(
            environment_name="env1", experiment_name="exp1",
            status="SUCCESS", duration=timedelta(seconds=30),
        )
        summary = BatchRunSummary(
            results=[item], total_combinations=1,
            successful_runs=1, failed_runs=0,
            interrupted_runs=0, skipped_runs=0,
            total_duration=timedelta(seconds=30),
        )
        assert len(summary.results) == 1
        assert summary.successful_runs == 1
