"""Tests for `_resolve_experiment_verdict` in adare.backend.experiment.run."""

from types import SimpleNamespace

import pytest

pytestmark = pytest.mark.unit

from adare.backend.experiment.run import _resolve_experiment_verdict
from adarelib.constants import StatusEnum


def _make_run(*, abstract_tests=None, tests=None, result_status=StatusEnum.SUCCESS,
              experiment_present=True, experiment_name="exp"):
    """Build a minimal duck-typed ExperimentRun row."""
    if experiment_present:
        experiment = SimpleNamespace(
            name=experiment_name,
            abstract_tests=list(abstract_tests or []),
        )
    else:
        experiment = None
    return SimpleNamespace(
        experiment=experiment,
        tests=list(tests or []),
        result_status=result_status,
    )


class TestSmokeRun:
    def test_no_tests_no_abstract_tests_passes_when_execution_succeeds(self):
        """verify-vm shape: test=False, no abstract tests, no test events → trust playbook."""
        run = _make_run(abstract_tests=[], tests=[], result_status=StatusEnum.SUCCESS)
        success, diag = _resolve_experiment_verdict(run, test_mode=False, execution_success=True)
        assert success is True
        assert diag["smoke_mode"] is True
        assert diag["verdict"] == "SUCCESS"
        assert diag["abstract_tests"] == 0
        assert diag["test_events"] == 0

    def test_smoke_run_fails_when_execution_failed(self):
        run = _make_run(abstract_tests=[], tests=[], result_status=StatusEnum.SUCCESS)
        success, diag = _resolve_experiment_verdict(run, test_mode=False, execution_success=False)
        assert success is False
        assert diag["smoke_mode"] is True
        assert diag["verdict"] == "FAILED"

    def test_smoke_run_passes_even_if_result_status_is_error(self):
        """The bug we're fixing: result_status=ERROR (e.g. relationship lazy-load fail)
        must not fail a smoke run when the playbook completed."""
        run = _make_run(abstract_tests=[], tests=[], result_status=StatusEnum.ERROR)
        success, diag = _resolve_experiment_verdict(run, test_mode=False, execution_success=True)
        assert success is True
        assert diag["smoke_mode"] is True

    def test_smoke_gate_when_run_row_missing(self):
        """If the run row is not found, fall back to execution_success for test=False."""
        success, diag = _resolve_experiment_verdict(None, test_mode=False, execution_success=True)
        assert success is True
        assert diag["smoke_mode"] is True
        assert diag["run_found"] is False

    def test_smoke_gate_when_experiment_relationship_unloaded(self):
        """If experiment can't be loaded across session boundary, abstract_tests
        defaults to 0 and the smoke gate still trips."""
        class _BadRel:
            @property
            def experiment(self):
                raise RuntimeError("session detached")

            tests = []
            result_status = StatusEnum.ERROR

        success, diag = _resolve_experiment_verdict(_BadRel(), test_mode=False, execution_success=True)
        assert success is True
        assert diag["smoke_mode"] is True
        assert diag["experiment_loaded"] is False


class TestFullTestRun:
    def test_test_mode_true_requires_strict_status_success(self):
        """test=True must keep the strict verdict — playbook completion alone is not enough."""
        run = _make_run(abstract_tests=[], tests=[], result_status=StatusEnum.FAILED)
        success, diag = _resolve_experiment_verdict(run, test_mode=True, execution_success=True)
        assert success is False
        assert diag["smoke_mode"] is False
        assert diag["verdict"] == "FAILED"

    def test_test_mode_true_passes_on_status_success(self):
        run = _make_run(abstract_tests=[], tests=[], result_status=StatusEnum.SUCCESS)
        success, diag = _resolve_experiment_verdict(run, test_mode=True, execution_success=True)
        assert success is True
        assert diag["smoke_mode"] is False

    def test_abstract_tests_present_demands_strict_status_success(self):
        """test=False but abstract_tests non-empty must NOT relax the verdict."""
        abstract_test = SimpleNamespace(id="t1")
        run = _make_run(
            abstract_tests=[abstract_test],
            tests=[],
            result_status=StatusEnum.TEST_MISSING,
        )
        success, diag = _resolve_experiment_verdict(run, test_mode=False, execution_success=True)
        assert success is False
        assert diag["smoke_mode"] is False
        assert diag["abstract_tests"] == 1

    def test_abstract_tests_present_passes_on_status_success(self):
        abstract_test = SimpleNamespace(id="t1")
        run = _make_run(
            abstract_tests=[abstract_test],
            tests=[SimpleNamespace(success=True, abstract_test_id="t1", result=None)],
            result_status=StatusEnum.SUCCESS,
        )
        success, diag = _resolve_experiment_verdict(run, test_mode=False, execution_success=True)
        assert success is True
        assert diag["smoke_mode"] is False

    def test_run_missing_with_test_mode_true_is_failure(self):
        """Full test run with no run row in DB → cannot confirm success."""
        success, diag = _resolve_experiment_verdict(None, test_mode=True, execution_success=True)
        assert success is False
        assert diag["smoke_mode"] is False
        assert diag["run_found"] is False
