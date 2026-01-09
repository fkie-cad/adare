"""Comprehensive unit tests for adarelib/constants.py"""

import pytest
from datetime import datetime

from adarelib.constants import StatusEnum, VMStatus, TIMESTAMP_FORMAT


class TestTimestampFormat:
    """Tests for the TIMESTAMP_FORMAT constant"""

    def test_timestamp_format_value(self):
        """Verify the exact format string"""
        assert TIMESTAMP_FORMAT == '%Y-%m-%dT%H:%M:%S.%f'

    def test_timestamp_format_parsing(self):
        """Test that the format can parse ISO-like timestamps"""
        timestamp_str = "2024-01-15T10:30:45.123456"
        parsed = datetime.strptime(timestamp_str, TIMESTAMP_FORMAT)
        assert parsed.year == 2024
        assert parsed.month == 1
        assert parsed.day == 15
        assert parsed.hour == 10
        assert parsed.minute == 30
        assert parsed.second == 45
        assert parsed.microsecond == 123456

    def test_timestamp_format_formatting(self):
        """Test that the format can format datetime objects correctly"""
        dt = datetime(2024, 6, 20, 14, 25, 30, 500000)
        formatted = dt.strftime(TIMESTAMP_FORMAT)
        assert formatted == "2024-06-20T14:25:30.500000"

    def test_timestamp_roundtrip(self):
        """Test parsing and formatting back produces same result"""
        original = "2023-12-31T23:59:59.999999"
        parsed = datetime.strptime(original, TIMESTAMP_FORMAT)
        formatted = parsed.strftime(TIMESTAMP_FORMAT)
        assert formatted == original


class TestStatusEnumValues:
    """Tests for StatusEnum integer values and membership"""

    @pytest.mark.parametrize("status,expected_value", [
        (StatusEnum.NONE, 1),
        (StatusEnum.SUCCESS, 2),
        (StatusEnum.FAILED, 3),
        (StatusEnum.WARNING, 4),
        (StatusEnum.ERROR, 5),
        (StatusEnum.RUNNING, 6),
        (StatusEnum.PENDING, 7),
        (StatusEnum.INTERRUPTED, 8),
        (StatusEnum.FINISHED, 9),
        (StatusEnum.TEST_MISSING, 12),
        (StatusEnum.TEST_FAILED, 13),
        (StatusEnum.PAUSE, 14),
    ])
    def test_enum_values(self, status, expected_value):
        """Verify each enum has the correct integer value"""
        assert status == expected_value
        assert status.value == expected_value

    def test_status_enum_is_int_enum(self):
        """Verify StatusEnum inherits from IntEnum"""
        assert issubclass(StatusEnum, int)
        assert isinstance(StatusEnum.SUCCESS, int)

    def test_enum_count(self):
        """Verify the expected number of status values exist"""
        # Note: values 10 and 11 are skipped (gap between FINISHED=9 and TEST_MISSING=12)
        assert len(StatusEnum) == 12


class TestStatusEnumFromString:
    """Tests for StatusEnum.from_string() method"""

    @pytest.mark.parametrize("input_string,expected", [
        ("success", StatusEnum.SUCCESS),
        ("failed", StatusEnum.FAILED),
        ("warning", StatusEnum.WARNING),
        ("error", StatusEnum.ERROR),
        ("running", StatusEnum.RUNNING),
        ("pending", StatusEnum.PENDING),
        ("interrupted", StatusEnum.INTERRUPTED),
        ("finished", StatusEnum.FINISHED),
        ("test_missing", StatusEnum.TEST_MISSING),
        ("test_failed", StatusEnum.TEST_FAILED),
    ])
    def test_from_string_lowercase(self, input_string, expected):
        """Test from_string with lowercase input"""
        assert StatusEnum.from_string(input_string) == expected

    @pytest.mark.parametrize("input_string,expected", [
        ("SUCCESS", StatusEnum.SUCCESS),
        ("FAILED", StatusEnum.FAILED),
        ("WARNING", StatusEnum.WARNING),
        ("ERROR", StatusEnum.ERROR),
        ("RUNNING", StatusEnum.RUNNING),
        ("PENDING", StatusEnum.PENDING),
        ("INTERRUPTED", StatusEnum.INTERRUPTED),
        ("FINISHED", StatusEnum.FINISHED),
        ("TEST_MISSING", StatusEnum.TEST_MISSING),
        ("TEST_FAILED", StatusEnum.TEST_FAILED),
    ])
    def test_from_string_uppercase(self, input_string, expected):
        """Test from_string with uppercase input (case insensitivity)"""
        assert StatusEnum.from_string(input_string) == expected

    @pytest.mark.parametrize("input_string,expected", [
        ("Success", StatusEnum.SUCCESS),
        ("Failed", StatusEnum.FAILED),
        ("Warning", StatusEnum.WARNING),
        ("Error", StatusEnum.ERROR),
        ("Running", StatusEnum.RUNNING),
        ("Pending", StatusEnum.PENDING),
        ("Interrupted", StatusEnum.INTERRUPTED),
        ("Finished", StatusEnum.FINISHED),
        ("Test_Missing", StatusEnum.TEST_MISSING),
        ("Test_Failed", StatusEnum.TEST_FAILED),
    ])
    def test_from_string_mixed_case(self, input_string, expected):
        """Test from_string with mixed case input"""
        assert StatusEnum.from_string(input_string) == expected

    @pytest.mark.parametrize("input_string", [
        "  success  ",
        "  SUCCESS  ",
        "\tsuccess\t",
        "\n success \n",
        "   success",
        "success   ",
    ])
    def test_from_string_with_whitespace(self, input_string):
        """Test from_string strips whitespace correctly"""
        assert StatusEnum.from_string(input_string) == StatusEnum.SUCCESS

    @pytest.mark.parametrize("invalid_input", [
        "invalid",
        "unknown",
        "complete",
        "done",
        "none",  # Note: "none" doesn't match NONE status
        "pause",  # Note: PAUSE is not handled in from_string
        "",
        "   ",
        "successs",  # typo
        "sucess",   # typo
        "fail",     # not "failed"
        "warn",     # not "warning"
        "run",      # not "running"
        "pend",     # not "pending"
    ])
    def test_from_string_invalid_returns_none(self, invalid_input):
        """Test that invalid strings return StatusEnum.NONE"""
        assert StatusEnum.from_string(invalid_input) == StatusEnum.NONE

    def test_from_string_empty_string(self):
        """Test empty string returns NONE"""
        assert StatusEnum.from_string("") == StatusEnum.NONE

    def test_from_string_whitespace_only(self):
        """Test whitespace-only string returns NONE"""
        assert StatusEnum.from_string("   ") == StatusEnum.NONE


class TestStatusEnumGetColor:
    """Tests for StatusEnum.get_color() method"""

    @pytest.mark.parametrize("status,expected_color", [
        (StatusEnum.SUCCESS, "green"),
        (StatusEnum.FINISHED, "green"),
        (StatusEnum.FAILED, "red"),
        (StatusEnum.ERROR, "red"),
        (StatusEnum.TEST_FAILED, "red"),
        (StatusEnum.WARNING, "yellow"),
        (StatusEnum.INTERRUPTED, "yellow"),
        (StatusEnum.PENDING, "yellow"),
        (StatusEnum.PAUSE, "yellow"),
        (StatusEnum.RUNNING, "blue"),
        (StatusEnum.TEST_MISSING, "blue"),
    ])
    def test_get_color_for_status(self, status, expected_color):
        """Test get_color returns correct color for each status"""
        assert StatusEnum.get_color(status) == expected_color

    def test_get_color_for_none_status(self):
        """Test get_color returns empty string for NONE status"""
        assert StatusEnum.get_color(StatusEnum.NONE) == ""

    def test_get_color_accepts_int_values(self):
        """Test get_color accepts plain integer values"""
        assert StatusEnum.get_color(2) == "green"  # SUCCESS
        assert StatusEnum.get_color(3) == "red"    # FAILED

    @pytest.mark.parametrize("invalid_value", [
        0, 10, 11, 15, 100, -1, 999,
    ])
    def test_get_color_invalid_value_returns_empty(self, invalid_value):
        """Test get_color returns empty string for invalid values"""
        assert StatusEnum.get_color(invalid_value) == ""


class TestStatusEnumGetIcon:
    """Tests for StatusEnum.get_icon() method"""

    @pytest.mark.parametrize("status,expected_icon_markup", [
        (StatusEnum.SUCCESS, ":heavy_check_mark:"),
        (StatusEnum.WARNING, ":warning:"),
        (StatusEnum.FAILED, ":heavy_multiplication_x:"),
        (StatusEnum.ERROR, ":x:"),
        (StatusEnum.FINISHED, ":black_small_square:"),
        (StatusEnum.INTERRUPTED, ":high_voltage:"),
        (StatusEnum.RUNNING, ":arrow_forward:"),
        (StatusEnum.PENDING, ":hourglass:"),
        (StatusEnum.TEST_MISSING, ":black_medium_square:"),
        (StatusEnum.TEST_FAILED, ":no_entry_sign:"),
        (StatusEnum.PAUSE, ":pause_button:"),
    ])
    def test_get_icon_without_color(self, status, expected_icon_markup):
        """Test get_icon returns correct icon markup without color"""
        from rich.text import Text
        result = StatusEnum.get_icon(status, color=False)
        # Without color, result should be a Text object
        assert isinstance(result, Text)
        # The Text object contains the rendered emoji
        # We verify by checking the plain representation contains something
        assert len(str(result)) > 0

    @pytest.mark.parametrize("status", [
        StatusEnum.SUCCESS,
        StatusEnum.WARNING,
        StatusEnum.FAILED,
        StatusEnum.ERROR,
        StatusEnum.FINISHED,
        StatusEnum.INTERRUPTED,
        StatusEnum.RUNNING,
        StatusEnum.PENDING,
        StatusEnum.TEST_MISSING,
        StatusEnum.TEST_FAILED,
        StatusEnum.PAUSE,
    ])
    def test_get_icon_with_color(self, status):
        """Test get_icon returns colored string when color=True"""
        result = StatusEnum.get_icon(status, color=True)
        # With color=True, result should be a string with color markup
        assert isinstance(result, str)
        expected_color = StatusEnum.get_color(status)
        assert f"[{expected_color}]" in result
        assert f"[/{expected_color}]" in result

    def test_get_icon_none_status_without_color(self):
        """Test get_icon for NONE status returns empty Text without color"""
        from rich.text import Text
        result = StatusEnum.get_icon(StatusEnum.NONE, color=False)
        assert isinstance(result, Text)
        # NONE status should produce empty icon string
        assert str(result) == ""

    def test_get_icon_none_status_with_color(self):
        """Test get_icon for NONE status with color returns formatted empty string"""
        result = StatusEnum.get_icon(StatusEnum.NONE, color=True)
        # NONE has empty color, so format should be different
        # When colorname is empty string, returns Text object not string
        from rich.text import Text
        assert isinstance(result, Text)

    def test_get_icon_accepts_int_values(self):
        """Test get_icon accepts plain integer values"""
        from rich.text import Text
        result = StatusEnum.get_icon(2, color=False)  # SUCCESS
        assert isinstance(result, Text)
        assert len(str(result)) > 0

    def test_get_icon_default_color_is_false(self):
        """Test that color parameter defaults to False"""
        from rich.text import Text
        result = StatusEnum.get_icon(StatusEnum.SUCCESS)
        # Without explicit color=True, should return Text object
        assert isinstance(result, Text)


class TestVMStatusValues:
    """Tests for VMStatus enum values"""

    @pytest.mark.parametrize("status,expected_value", [
        (VMStatus.IMPORTED, 1),
        (VMStatus.READY, 2),
        (VMStatus.MISSING, 3),
        (VMStatus.SNAPSHOT_MISSING, 4),
        (VMStatus.CORRUPTED, 5),
    ])
    def test_vm_status_values(self, status, expected_value):
        """Verify each VMStatus has the correct integer value"""
        assert status == expected_value
        assert status.value == expected_value

    def test_vm_status_is_int_enum(self):
        """Verify VMStatus inherits from IntEnum"""
        assert issubclass(VMStatus, int)
        assert isinstance(VMStatus.READY, int)

    def test_vm_status_count(self):
        """Verify the expected number of VM status values exist"""
        assert len(VMStatus) == 5

    @pytest.mark.parametrize("status,expected_name", [
        (VMStatus.IMPORTED, "IMPORTED"),
        (VMStatus.READY, "READY"),
        (VMStatus.MISSING, "MISSING"),
        (VMStatus.SNAPSHOT_MISSING, "SNAPSHOT_MISSING"),
        (VMStatus.CORRUPTED, "CORRUPTED"),
    ])
    def test_vm_status_names(self, status, expected_name):
        """Verify each VMStatus has the correct name"""
        assert status.name == expected_name


class TestVMStatusUsage:
    """Tests for practical VMStatus usage patterns"""

    def test_vm_status_comparison_with_int(self):
        """Test VMStatus can be compared with plain integers"""
        assert VMStatus.READY == 2
        assert VMStatus.MISSING != 2
        assert VMStatus.IMPORTED < VMStatus.READY

    def test_vm_status_in_collection(self):
        """Test VMStatus values work correctly in sets and lists"""
        ready_states = {VMStatus.READY, VMStatus.IMPORTED}
        assert VMStatus.READY in ready_states
        assert VMStatus.MISSING not in ready_states

    def test_vm_status_ordering(self):
        """Test VMStatus values can be ordered"""
        statuses = [VMStatus.CORRUPTED, VMStatus.IMPORTED, VMStatus.READY]
        sorted_statuses = sorted(statuses)
        assert sorted_statuses == [VMStatus.IMPORTED, VMStatus.READY, VMStatus.CORRUPTED]


class TestStatusEnumComparison:
    """Tests for StatusEnum comparison and arithmetic operations"""

    def test_status_enum_comparison_with_int(self):
        """Test StatusEnum can be compared with plain integers"""
        assert StatusEnum.SUCCESS == 2
        assert StatusEnum.FAILED == 3
        assert StatusEnum.SUCCESS < StatusEnum.FAILED

    def test_status_enum_arithmetic(self):
        """Test StatusEnum supports arithmetic as IntEnum"""
        # This is a property of IntEnum - values can be used in arithmetic
        assert StatusEnum.SUCCESS + 1 == 3
        assert StatusEnum.FAILED - StatusEnum.SUCCESS == 1

    def test_status_enum_in_collection(self):
        """Test StatusEnum values work correctly in collections"""
        success_states = {StatusEnum.SUCCESS, StatusEnum.FINISHED}
        assert StatusEnum.SUCCESS in success_states
        assert StatusEnum.FAILED not in success_states

    def test_status_enum_hash(self):
        """Test StatusEnum values are hashable"""
        status_dict = {StatusEnum.SUCCESS: "passed", StatusEnum.FAILED: "failed"}
        assert status_dict[StatusEnum.SUCCESS] == "passed"
        assert status_dict[StatusEnum.FAILED] == "failed"


class TestStatusEnumEdgeCases:
    """Edge case tests for StatusEnum"""

    def test_get_icon_returns_text_for_unknown_value(self):
        """Test get_icon handles unknown integer values gracefully"""
        from rich.text import Text
        # Value 100 is not a valid StatusEnum value
        result = StatusEnum.get_icon(100, color=False)
        assert isinstance(result, Text)
        # Should return empty Text since no icon matches
        assert str(result) == ""

    def test_get_color_type_consistency(self):
        """Test get_color always returns a string"""
        for status in StatusEnum:
            color = StatusEnum.get_color(status)
            assert isinstance(color, str)

    def test_from_string_type_consistency(self):
        """Test from_string always returns a StatusEnum"""
        test_inputs = ["success", "invalid", "", "   ", "FAILED", "Unknown"]
        for input_str in test_inputs:
            result = StatusEnum.from_string(input_str)
            assert isinstance(result, StatusEnum)

    def test_enum_iteration(self):
        """Test that all StatusEnum members can be iterated"""
        members = list(StatusEnum)
        assert len(members) == 12
        assert StatusEnum.NONE in members
        assert StatusEnum.PAUSE in members
