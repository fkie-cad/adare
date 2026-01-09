"""
Unit tests for adarelib.event.event module.

Tests cover:
- Event dataclass creation
- TestResult factory methods (success, failed, error, execution_error)
- TestEvent creation with defaults
- ErrorEvent creation
- transform_data_to_event function
- Edge cases (None exception, empty details)
"""
import pytest
from datetime import datetime
from unittest.mock import patch
import re

from adarelib.event.event import (
    Event,
    TestResult,
    TestEvent,
    ErrorEvent,
    transform_data_to_event,
)
from adarelib.constants import StatusEnum, TIMESTAMP_FORMAT


class TestEventClass:
    """Tests for the Event base dataclass."""

    def test_event_creation_with_all_fields(self):
        """Test creating an Event with all required fields."""
        event = Event(
            category="action",
            timestamp="2024-01-15T10:30:00.000000",
            status=StatusEnum.SUCCESS,
            ulid="01HM123ABC456DEF789GHI012",
            error=""
        )

        assert event.category == "action"
        assert event.timestamp == "2024-01-15T10:30:00.000000"
        assert event.status == StatusEnum.SUCCESS
        assert event.ulid == "01HM123ABC456DEF789GHI012"
        assert event.error == ""

    def test_event_with_error_message(self):
        """Test creating an Event with an error message."""
        event = Event(
            category="test",
            timestamp="2024-01-15T10:30:00.000000",
            status=StatusEnum.ERROR,
            ulid="01HM123ABC456DEF789GHI012",
            error="Something went wrong"
        )

        assert event.error == "Something went wrong"
        assert event.status == StatusEnum.ERROR

    def test_event_with_different_status_values(self):
        """Test Event with various StatusEnum values."""
        statuses = [
            StatusEnum.NONE,
            StatusEnum.SUCCESS,
            StatusEnum.FAILED,
            StatusEnum.ERROR,
            StatusEnum.RUNNING,
            StatusEnum.PENDING,
        ]

        for status in statuses:
            event = Event(
                category="test",
                timestamp="2024-01-15T10:30:00.000000",
                status=status,
                ulid="01HM123ABC456DEF789GHI012",
                error=""
            )
            assert event.status == status


class TestTestResultClass:
    """Tests for the TestResult dataclass and factory methods."""

    def test_test_result_direct_creation(self):
        """Test creating TestResult directly."""
        result = TestResult(status=StatusEnum.SUCCESS, details=["test passed"])

        assert result.status == StatusEnum.SUCCESS
        assert result.details == ["test passed"]

    def test_test_result_default_details(self):
        """Test TestResult with default empty details."""
        result = TestResult(status=StatusEnum.FAILED)

        assert result.details == []

    def test_success_factory_with_details(self):
        """Test TestResult.success() factory with details."""
        details = ["assertion passed", "value matched"]
        result = TestResult.success(details=details)

        assert result.status == StatusEnum.SUCCESS
        assert result.details == details

    def test_success_factory_without_details(self):
        """Test TestResult.success() factory without details."""
        result = TestResult.success()

        assert result.status == StatusEnum.SUCCESS
        assert result.details == []

    def test_success_factory_with_none_details(self):
        """Test TestResult.success() factory with None details."""
        result = TestResult.success(details=None)

        assert result.status == StatusEnum.SUCCESS
        assert result.details == []

    def test_failed_factory_with_details(self):
        """Test TestResult.failed() factory with details."""
        details = ["expected 5, got 3"]
        result = TestResult.failed(details=details)

        assert result.status == StatusEnum.FAILED
        assert result.details == details

    def test_failed_factory_without_details(self):
        """Test TestResult.failed() factory without details."""
        result = TestResult.failed()

        assert result.status == StatusEnum.FAILED
        assert result.details == []

    def test_error_factory_with_details(self):
        """Test TestResult.error() factory with details."""
        details = ["test could not execute", "missing dependency"]
        result = TestResult.error(details=details)

        assert result.status == StatusEnum.ERROR
        assert result.details == details

    def test_error_factory_without_details(self):
        """Test TestResult.error() factory without details."""
        result = TestResult.error()

        assert result.status == StatusEnum.ERROR
        assert result.details == []

    def test_execution_error_with_exception(self):
        """Test TestResult.execution_error() with a real exception."""
        try:
            raise ValueError("Test error message")
        except ValueError as e:
            result = TestResult.execution_error(e)

        assert result.status == StatusEnum.ERROR
        assert len(result.details) == 2
        assert "ValueError: Test error message" in result.details[0]
        assert "Stack trace:" in result.details[1]
        assert "ValueError" in result.details[1]

    def test_execution_error_with_context(self):
        """Test TestResult.execution_error() with context message."""
        try:
            raise KeyError("missing_key")
        except KeyError as e:
            result = TestResult.execution_error(e, context="During config load")

        assert result.status == StatusEnum.ERROR
        assert len(result.details) == 2
        assert "During config load" in result.details[0]
        assert "KeyError" in result.details[0]

    def test_execution_error_with_none_exception(self):
        """Test TestResult.execution_error() with None exception."""
        result = TestResult.execution_error(None)

        assert result.status == StatusEnum.ERROR
        assert result.details == ["Unknown error"]

    def test_execution_error_with_none_exception_and_context(self):
        """Test TestResult.execution_error() with None exception but with context."""
        result = TestResult.execution_error(None, context="Custom context message")

        assert result.status == StatusEnum.ERROR
        assert result.details == ["Custom context message"]

    def test_execution_error_preserves_traceback(self):
        """Test that execution_error preserves the full traceback."""
        def inner_function():
            raise RuntimeError("Inner error")

        def outer_function():
            inner_function()

        try:
            outer_function()
        except RuntimeError as e:
            result = TestResult.execution_error(e)

        assert "inner_function" in result.details[1]
        assert "outer_function" in result.details[1]


class TestTestEventClass:
    """Tests for the TestEvent dataclass."""

    def test_test_event_creation_with_required_fields(self):
        """Test creating TestEvent with only required fields."""
        event = TestEvent(test_name="test_login")

        assert event.test_name == "test_login"
        assert event.category == "test"
        assert event.status == StatusEnum.RUNNING
        assert event.error == ""
        assert event.result is None

    def test_test_event_with_result(self):
        """Test creating TestEvent with a TestResult."""
        result = TestResult.success(details=["passed"])
        event = TestEvent(test_name="test_auth", result=result)

        assert event.result == result
        assert event.result.status == StatusEnum.SUCCESS

    def test_test_event_timestamp_auto_generated(self):
        """Test that TestEvent auto-generates timestamp."""
        event = TestEvent(test_name="test_auto_timestamp")

        # Timestamp should be in expected format
        assert event.timestamp is not None
        # Should be parseable
        parsed = datetime.strptime(event.timestamp, TIMESTAMP_FORMAT)
        assert parsed is not None

    def test_test_event_ulid_auto_generated(self):
        """Test that TestEvent auto-generates ULID."""
        event = TestEvent(test_name="test_auto_ulid")

        assert event.ulid is not None
        assert len(event.ulid) == 26  # ULID is 26 characters

    def test_test_event_ulids_are_unique(self):
        """Test that each TestEvent gets a unique ULID."""
        event1 = TestEvent(test_name="test1")
        event2 = TestEvent(test_name="test2")

        assert event1.ulid != event2.ulid

    def test_test_event_custom_status(self):
        """Test creating TestEvent with custom status."""
        event = TestEvent(
            test_name="test_custom_status",
            status=StatusEnum.SUCCESS
        )

        assert event.status == StatusEnum.SUCCESS

    def test_test_event_custom_error(self):
        """Test creating TestEvent with custom error message."""
        event = TestEvent(
            test_name="test_with_error",
            error="Timeout occurred"
        )

        assert event.error == "Timeout occurred"

    def test_test_event_all_custom_fields(self):
        """Test creating TestEvent with all fields customized."""
        result = TestResult.failed(details=["assertion failed"])
        event = TestEvent(
            test_name="full_custom_test",
            result=result,
            category="custom_category",
            timestamp="2024-06-01T12:00:00.000000",
            ulid="01HX1234567890ABCDEFGHIJ",
            status=StatusEnum.FAILED,
            error="Test failed"
        )

        assert event.test_name == "full_custom_test"
        assert event.result == result
        assert event.category == "custom_category"
        assert event.timestamp == "2024-06-01T12:00:00.000000"
        assert event.ulid == "01HX1234567890ABCDEFGHIJ"
        assert event.status == StatusEnum.FAILED
        assert event.error == "Test failed"


class TestErrorEventClass:
    """Tests for the ErrorEvent dataclass."""

    def test_error_event_creation_with_required_fields(self):
        """Test creating ErrorEvent with only required fields."""
        event = ErrorEvent(error_name="ConnectionError")

        assert event.error_name == "ConnectionError"
        assert event.category == "error"
        assert event.status == StatusEnum.NONE
        assert event.error == ""
        assert event.error_msg == ""

    def test_error_event_with_error_msg(self):
        """Test creating ErrorEvent with error_msg."""
        event = ErrorEvent(
            error_name="TimeoutError",
            error_msg="Connection timed out after 30 seconds"
        )

        assert event.error_name == "TimeoutError"
        assert event.error_msg == "Connection timed out after 30 seconds"

    def test_error_event_timestamp_auto_generated(self):
        """Test that ErrorEvent auto-generates timestamp."""
        event = ErrorEvent(error_name="TestError")

        assert event.timestamp is not None
        parsed = datetime.strptime(event.timestamp, TIMESTAMP_FORMAT)
        assert parsed is not None

    def test_error_event_ulid_auto_generated(self):
        """Test that ErrorEvent auto-generates ULID."""
        event = ErrorEvent(error_name="TestError")

        assert event.ulid is not None
        assert len(event.ulid) == 26

    def test_error_event_all_custom_fields(self):
        """Test creating ErrorEvent with all fields customized."""
        event = ErrorEvent(
            error_name="CustomError",
            category="custom_error_category",
            timestamp="2024-06-01T12:00:00.000000",
            ulid="01HX1234567890ABCDEFGHIJ",
            status=StatusEnum.ERROR,
            error="Base error field",
            error_msg="Detailed error message"
        )

        assert event.error_name == "CustomError"
        assert event.category == "custom_error_category"
        assert event.timestamp == "2024-06-01T12:00:00.000000"
        assert event.ulid == "01HX1234567890ABCDEFGHIJ"
        assert event.status == StatusEnum.ERROR
        assert event.error == "Base error field"
        assert event.error_msg == "Detailed error message"


class TestTransformDataToEventFunc:
    """Tests for the transform_data_to_event function."""

    def test_transform_test_event(self):
        """Test transforming data to TestEvent."""
        data = {
            "category": "test",
            "test_name": "test_login",
            "timestamp": "2024-01-15T10:30:00.000000",
            "status": StatusEnum.SUCCESS,
            "ulid": "01HM123ABC456DEF789GHI012",
            "error": "",
            "result": None
        }

        event = transform_data_to_event(data)

        assert isinstance(event, TestEvent)
        assert event.test_name == "test_login"
        assert event.category == "test"
        assert event.status == StatusEnum.SUCCESS

    def test_transform_test_event_with_result(self):
        """Test transforming data to TestEvent with TestResult."""
        data = {
            "category": "test",
            "test_name": "test_with_result",
            "timestamp": "2024-01-15T10:30:00.000000",
            "status": StatusEnum.SUCCESS,
            "ulid": "01HM123ABC456DEF789GHI012",
            "error": "",
            "result": {
                "status": StatusEnum.SUCCESS,
                "details": ["passed"]
            }
        }

        event = transform_data_to_event(data)

        assert isinstance(event, TestEvent)
        assert event.result is not None
        assert event.result.status == StatusEnum.SUCCESS
        assert event.result.details == ["passed"]

    def test_transform_error_event(self):
        """Test transforming data to ErrorEvent."""
        data = {
            "category": "error",
            "error_name": "ConnectionError",
            "timestamp": "2024-01-15T10:30:00.000000",
            "status": StatusEnum.NONE,
            "ulid": "01HM123ABC456DEF789GHI012",
            "error": "",
            "error_msg": "Connection refused"
        }

        event = transform_data_to_event(data)

        assert isinstance(event, ErrorEvent)
        assert event.error_name == "ConnectionError"
        assert event.error_msg == "Connection refused"

    def test_transform_unsupported_category_raises_error(self):
        """Test that unsupported category raises ValueError."""
        data = {
            "category": "action",
            "name": "click",
            "timestamp": "2024-01-15T10:30:00.000000",
            "status": StatusEnum.RUNNING,
            "ulid": "01HM123ABC456DEF789GHI012",
            "error": ""
        }

        with pytest.raises(ValueError) as exc_info:
            transform_data_to_event(data)

        assert "action" in str(exc_info.value)
        assert "not supported" in str(exc_info.value)

    def test_transform_unknown_category_raises_error(self):
        """Test that completely unknown category raises ValueError."""
        data = {
            "category": "unknown_category",
            "timestamp": "2024-01-15T10:30:00.000000",
            "status": StatusEnum.NONE,
            "ulid": "01HM123ABC456DEF789GHI012",
            "error": ""
        }

        with pytest.raises(ValueError) as exc_info:
            transform_data_to_event(data)

        assert "unknown_category" in str(exc_info.value)

    def test_transform_with_missing_category_raises_key_error(self):
        """Test that missing category raises KeyError."""
        data = {
            "test_name": "test_no_category",
            "timestamp": "2024-01-15T10:30:00.000000",
            "status": StatusEnum.RUNNING,
            "ulid": "01HM123ABC456DEF789GHI012",
            "error": ""
        }

        with pytest.raises(KeyError):
            transform_data_to_event(data)


class TestEdgeCasesEventModule:
    """Tests for edge cases and boundary conditions."""

    def test_test_result_with_empty_list_details(self):
        """Test TestResult with explicitly empty list."""
        result = TestResult.success(details=[])
        assert result.details == []

    def test_test_result_with_none_in_details_list(self):
        """Test TestResult with None value inside details list."""
        result = TestResult.failed(details=[None, "error"])
        assert result.details == [None, "error"]

    def test_test_result_with_large_details(self):
        """Test TestResult with large amount of details."""
        large_details = [f"detail_{i}" for i in range(1000)]
        result = TestResult.error(details=large_details)
        assert len(result.details) == 1000

    def test_test_event_with_empty_test_name(self):
        """Test TestEvent with empty string test_name."""
        event = TestEvent(test_name="")
        assert event.test_name == ""

    def test_error_event_with_empty_error_name(self):
        """Test ErrorEvent with empty string error_name."""
        event = ErrorEvent(error_name="")
        assert event.error_name == ""

    def test_event_equality(self):
        """Test that two events with same values are equal (attrs behavior)."""
        event1 = Event(
            category="test",
            timestamp="2024-01-15T10:30:00.000000",
            status=StatusEnum.SUCCESS,
            ulid="01HM123ABC456DEF789GHI012",
            error=""
        )
        event2 = Event(
            category="test",
            timestamp="2024-01-15T10:30:00.000000",
            status=StatusEnum.SUCCESS,
            ulid="01HM123ABC456DEF789GHI012",
            error=""
        )

        assert event1 == event2

    def test_test_result_equality(self):
        """Test that two TestResults with same values are equal."""
        result1 = TestResult.success(details=["test"])
        result2 = TestResult.success(details=["test"])

        assert result1 == result2

    def test_execution_error_with_nested_exception(self):
        """Test execution_error with exception that has __cause__."""
        try:
            try:
                raise ValueError("Original error")
            except ValueError as orig:
                raise RuntimeError("Wrapped error") from orig
        except RuntimeError as e:
            result = TestResult.execution_error(e)

        assert result.status == StatusEnum.ERROR
        assert "RuntimeError: Wrapped error" in result.details[0]
        # The chained exception should appear in the traceback
        assert "ValueError" in result.details[1]
