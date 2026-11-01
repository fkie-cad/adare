"""Host-evaluated TestResults must reach TestResultProcessor in the agent's reply shape."""

import pytest

from adare.backend.experiment.execution.test_actions import _as_tool_result
from adare.backend.experiment.test_result_processor import TestResultProcessor
from adarelib.event.event import TestResult

pytestmark = pytest.mark.unit


def test_success_is_a_passing_action():
    result = TestResultProcessor.process_test_result('t', _as_tool_result(TestResult.success(['ok'])))
    assert result.success and result.data['result_category'] == 'success'


def test_failed_is_a_failing_action_with_the_test_failure_category():
    result = TestResultProcessor.process_test_result('t', _as_tool_result(TestResult.failed(['no'])))
    assert not result.success and result.data['result_category'] == 'test_failure'


def test_expect_to_fail_inverts_a_host_evaluated_failure():
    result = TestResultProcessor.process_test_result(
        't', _as_tool_result(TestResult.failed(['no'])), expect_to_fail=True
    )
    assert result.success


def test_execution_error_stays_an_error():
    result = TestResultProcessor.process_test_result('t', _as_tool_result(TestResult.error(['boom'])))
    assert not result.success and result.data['result_category'] == 'execution_error'
