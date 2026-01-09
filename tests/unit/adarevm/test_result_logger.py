"""
Unit tests for adarevm.testing.result_logger module.

Tests TestResultLogger class and its methods.
"""
import pytest
import logging
from unittest.mock import MagicMock, patch, call

from adarevm.testing.result_logger import TestResultLogger
from adarelib.constants import StatusEnum
from adarelib.event.event import TestResult


class TestGetStatusName:
    """Tests for TestResultLogger._get_status_name method."""

    def test_get_status_name_success(self):
        """Test _get_status_name returns 'SUCCESS' for StatusEnum.SUCCESS."""
        result = TestResultLogger._get_status_name(StatusEnum.SUCCESS)
        assert result == 'SUCCESS'

    def test_get_status_name_failed(self):
        """Test _get_status_name returns 'FAILED' for StatusEnum.FAILED."""
        result = TestResultLogger._get_status_name(StatusEnum.FAILED)
        assert result == 'FAILED'

    def test_get_status_name_error(self):
        """Test _get_status_name returns 'ERROR' for StatusEnum.ERROR."""
        result = TestResultLogger._get_status_name(StatusEnum.ERROR)
        assert result == 'ERROR'

    def test_get_status_name_warning(self):
        """Test _get_status_name returns 'WARNING' for StatusEnum.WARNING."""
        result = TestResultLogger._get_status_name(StatusEnum.WARNING)
        assert result == 'WARNING'

    def test_get_status_name_none(self):
        """Test _get_status_name returns 'UNKNOWN' for StatusEnum.NONE."""
        result = TestResultLogger._get_status_name(StatusEnum.NONE)
        assert result == 'UNKNOWN'

    def test_get_status_name_running(self):
        """Test _get_status_name returns 'UNKNOWN' for StatusEnum.RUNNING."""
        result = TestResultLogger._get_status_name(StatusEnum.RUNNING)
        assert result == 'UNKNOWN'

    def test_get_status_name_pending(self):
        """Test _get_status_name returns 'UNKNOWN' for StatusEnum.PENDING."""
        result = TestResultLogger._get_status_name(StatusEnum.PENDING)
        assert result == 'UNKNOWN'

    def test_get_status_name_interrupted(self):
        """Test _get_status_name returns 'UNKNOWN' for StatusEnum.INTERRUPTED."""
        result = TestResultLogger._get_status_name(StatusEnum.INTERRUPTED)
        assert result == 'UNKNOWN'

    def test_get_status_name_finished(self):
        """Test _get_status_name returns 'UNKNOWN' for StatusEnum.FINISHED."""
        result = TestResultLogger._get_status_name(StatusEnum.FINISHED)
        assert result == 'UNKNOWN'


class TestFormatResultForResponse:
    """Tests for TestResultLogger.format_result_for_response method."""

    def test_format_result_for_response_with_none_result(self):
        """Test format_result_for_response returns default for None result."""
        result = TestResultLogger.format_result_for_response("test_name", None)

        assert result == {
            'status': 'UNKNOWN',
            'details': ['No result returned']
        }

    def test_format_result_for_response_with_success_result(self):
        """Test format_result_for_response with SUCCESS status."""
        test_result = TestResult.success(details=['Test passed'])
        result = TestResultLogger.format_result_for_response("test_name", test_result)

        assert result == {
            'status': 'SUCCESS',
            'details': ['Test passed']
        }

    def test_format_result_for_response_with_failed_result(self):
        """Test format_result_for_response with FAILED status."""
        test_result = TestResult.failed(details=['Assertion failed', 'Expected X got Y'])
        result = TestResultLogger.format_result_for_response("test_name", test_result)

        assert result == {
            'status': 'FAILED',
            'details': ['Assertion failed', 'Expected X got Y']
        }

    def test_format_result_for_response_with_error_result(self):
        """Test format_result_for_response with ERROR status."""
        test_result = TestResult.error(details=['Test could not execute'])
        result = TestResultLogger.format_result_for_response("test_name", test_result)

        assert result == {
            'status': 'ERROR',
            'details': ['Test could not execute']
        }

    def test_format_result_for_response_with_empty_details(self):
        """Test format_result_for_response with empty details list."""
        test_result = TestResult.success(details=[])
        result = TestResultLogger.format_result_for_response("test_name", test_result)

        assert result == {
            'status': 'SUCCESS',
            'details': []
        }

    def test_format_result_for_response_with_no_details_attribute(self):
        """Test format_result_for_response when result has no details attribute."""
        mock_result = MagicMock()
        mock_result.status = StatusEnum.SUCCESS
        del mock_result.details  # Remove the details attribute

        result = TestResultLogger.format_result_for_response("test_name", mock_result)

        assert result['status'] == 'SUCCESS'
        assert result['details'] == []

    def test_format_result_for_response_with_no_status_attribute(self):
        """Test format_result_for_response when result has no status attribute."""
        mock_result = MagicMock(spec=[])  # Empty spec to not have status

        result = TestResultLogger.format_result_for_response("test_name", mock_result)

        assert result['status'] == 'UNKNOWN'

    def test_format_result_for_response_with_string_details(self):
        """Test format_result_for_response with string details (not list)."""
        mock_result = MagicMock()
        mock_result.status = StatusEnum.SUCCESS
        mock_result.details = "Single string detail"

        result = TestResultLogger.format_result_for_response("test_name", mock_result)

        assert result['status'] == 'SUCCESS'
        assert result['details'] == ['Single string detail']

    def test_format_result_for_response_with_none_details(self):
        """Test format_result_for_response with None details."""
        mock_result = MagicMock()
        mock_result.status = StatusEnum.SUCCESS
        mock_result.details = None

        result = TestResultLogger.format_result_for_response("test_name", mock_result)

        assert result['status'] == 'SUCCESS'
        assert result['details'] == []


class TestLogTestResult:
    """Tests for TestResultLogger.log_test_result method."""

    @patch('adarevm.testing.result_logger.log')
    def test_log_test_result_with_none_result(self, mock_log):
        """Test log_test_result logs warning for None result."""
        TestResultLogger.log_test_result("test_name", None)

        mock_log.warning.assert_called_once_with("Test 'test_name' returned no result")

    @patch('adarevm.testing.result_logger.log')
    def test_log_test_result_with_success(self, mock_log):
        """Test log_test_result logs success result."""
        test_result = TestResult.success(details=['Check passed'])

        TestResultLogger.log_test_result("my_test", test_result)

        # Verify info log was called with the status
        info_calls = [c for c in mock_log.info.call_args_list]
        status_call = [c for c in info_calls if "result: SUCCESS" in str(c)]
        assert len(status_call) > 0

    @patch('adarevm.testing.result_logger.log')
    def test_log_test_result_with_failed(self, mock_log):
        """Test log_test_result logs failed result."""
        test_result = TestResult.failed(details=['Assertion failed'])

        TestResultLogger.log_test_result("failing_test", test_result)

        info_calls = [c for c in mock_log.info.call_args_list]
        status_call = [c for c in info_calls if "result: FAILED" in str(c)]
        assert len(status_call) > 0

    @patch('adarevm.testing.result_logger.log')
    def test_log_test_result_with_error(self, mock_log):
        """Test log_test_result logs error result."""
        test_result = TestResult.error(details=['Exception occurred'])

        TestResultLogger.log_test_result("error_test", test_result)

        info_calls = [c for c in mock_log.info.call_args_list]
        status_call = [c for c in info_calls if "result: ERROR" in str(c)]
        assert len(status_call) > 0

    @patch('adarevm.testing.result_logger.log')
    def test_log_test_result_logs_details_list(self, mock_log):
        """Test log_test_result logs each detail from details list."""
        test_result = TestResult.success(details=['Detail 1', 'Detail 2'])

        TestResultLogger.log_test_result("test_name", test_result)

        info_calls = [str(c) for c in mock_log.info.call_args_list]
        detail_1_logged = any("Detail 1" in c for c in info_calls)
        detail_2_logged = any("Detail 2" in c for c in info_calls)
        assert detail_1_logged
        assert detail_2_logged

    @patch('adarevm.testing.result_logger.log')
    def test_log_test_result_logs_string_details(self, mock_log):
        """Test log_test_result logs non-list details."""
        mock_result = MagicMock()
        mock_result.status = StatusEnum.SUCCESS
        mock_result.details = "Single string detail"

        TestResultLogger.log_test_result("test_name", mock_result)

        info_calls = [str(c) for c in mock_log.info.call_args_list]
        detail_logged = any("Single string detail" in c for c in info_calls)
        assert detail_logged

    @patch('adarevm.testing.result_logger.log')
    def test_log_test_result_with_empty_details(self, mock_log):
        """Test log_test_result with empty details does not log details."""
        test_result = TestResult.success(details=[])

        TestResultLogger.log_test_result("test_name", test_result)

        # Should have debug and info calls, but no detail calls
        info_calls = [str(c) for c in mock_log.info.call_args_list]
        # Only the status should be logged, not details
        assert len([c for c in info_calls if "detail:" in c.lower()]) == 0

    @patch('adarevm.testing.result_logger.log')
    def test_log_test_result_logs_debug_info(self, mock_log):
        """Test log_test_result logs debug information about the result object."""
        test_result = TestResult.success()

        TestResultLogger.log_test_result("test_name", test_result)

        debug_calls = [str(c) for c in mock_log.debug.call_args_list]
        # Should have debug calls about the result object
        assert len(debug_calls) > 0


class TestTestResultLoggerIntegration:
    """Integration tests for TestResultLogger."""

    def test_format_result_matches_log_result_status(self):
        """Test that format_result_for_response and log_test_result use same status conversion."""
        for status_enum in [StatusEnum.SUCCESS, StatusEnum.FAILED, StatusEnum.ERROR]:
            test_result = TestResult(status=status_enum, details=[])
            formatted = TestResultLogger.format_result_for_response("test", test_result)
            expected_status = TestResultLogger._get_status_name(status_enum)
            assert formatted['status'] == expected_status

    def test_execution_error_result_format(self):
        """Test formatting of execution_error result."""
        exc = ValueError("Something went wrong")
        test_result = TestResult.execution_error(exc, context="During test")

        formatted = TestResultLogger.format_result_for_response("test_name", test_result)

        assert formatted['status'] == 'ERROR'
        assert len(formatted['details']) >= 1
        assert "ValueError" in formatted['details'][0]
        assert "Something went wrong" in formatted['details'][0]

    def test_execution_error_with_none_exception(self):
        """Test formatting of execution_error with None exception."""
        test_result = TestResult.execution_error(None, context="Unknown error occurred")

        formatted = TestResultLogger.format_result_for_response("test_name", test_result)

        assert formatted['status'] == 'ERROR'
        assert "Unknown error occurred" in formatted['details'][0]
