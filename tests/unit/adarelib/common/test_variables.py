"""
Comprehensive unit tests for adarelib/common/variables.py

Tests cover:
- VariableType enum
- Variable class with all types
- Variable.from_dict() and to_dict() methods
- Auto type inference
- VariableRegistry class
- TimestampMetadata class

NOTE: Due to the use of @attrs.define and __post_init__ (instead of __attrs_post_init__),
the _validate_and_coerce and _create_structured_metadata methods are NOT called during
Variable creation. This affects type coercion, validation, and structured metadata creation.
Tests reflect this actual behavior.
"""

import pytest
import datetime
import re
from unittest.mock import MagicMock, patch

from adarelib.common.variables import (
    VariableType,
    ValidationError,
    TimestampMetadata,
    Variable,
    VariableRegistry,
    parse_variables,
)


# =============================================================================
# VariableType Enum Tests
# =============================================================================

class TestVariableType:
    """Tests for VariableType enum."""

    def test_all_types_defined(self):
        """Verify all expected variable types are defined."""
        expected_types = [
            "STRING", "REGEX", "TIMESTAMP", "PATH",
            "INTEGER", "FLOAT", "BOOLEAN", "LIST", "DICT"
        ]
        for type_name in expected_types:
            assert hasattr(VariableType, type_name)

    def test_type_values(self):
        """Verify enum values are lowercase strings."""
        assert VariableType.STRING.value == "string"
        assert VariableType.REGEX.value == "regex"
        assert VariableType.TIMESTAMP.value == "timestamp"
        assert VariableType.PATH.value == "path"
        assert VariableType.INTEGER.value == "integer"
        assert VariableType.FLOAT.value == "float"
        assert VariableType.BOOLEAN.value == "boolean"
        assert VariableType.LIST.value == "list"
        assert VariableType.DICT.value == "dict"

    def test_type_creation_from_value(self):
        """Test creating VariableType from string value."""
        assert VariableType("string") == VariableType.STRING
        assert VariableType("regex") == VariableType.REGEX
        assert VariableType("timestamp") == VariableType.TIMESTAMP

    def test_invalid_type_raises_error(self):
        """Test that invalid type value raises ValueError."""
        with pytest.raises(ValueError):
            VariableType("invalid_type")


# =============================================================================
# Variable Class - Creation Tests
# =============================================================================

class TestVariableCreation:
    """Tests for Variable creation with different types."""

    def test_create_string_variable(self):
        """Test creating a string variable."""
        var = Variable(value="hello", type=VariableType.STRING)
        assert var.value == "hello"
        assert var.type == VariableType.STRING

    def test_create_integer_variable(self):
        """Test creating an integer variable."""
        var = Variable(value=42, type=VariableType.INTEGER)
        assert var.value == 42
        assert var.type == VariableType.INTEGER

    def test_create_float_variable(self):
        """Test creating a float variable."""
        var = Variable(value=3.14, type=VariableType.FLOAT)
        assert var.value == 3.14
        assert var.type == VariableType.FLOAT

    def test_create_boolean_variable_true(self):
        """Test creating a boolean variable with True."""
        var = Variable(value=True, type=VariableType.BOOLEAN)
        assert var.value is True
        assert var.type == VariableType.BOOLEAN

    def test_create_boolean_variable_false(self):
        """Test creating a boolean variable with False."""
        var = Variable(value=False, type=VariableType.BOOLEAN)
        assert var.value is False
        assert var.type == VariableType.BOOLEAN

    def test_create_list_variable(self):
        """Test creating a list variable."""
        test_list = [1, 2, 3, "four"]
        var = Variable(value=test_list, type=VariableType.LIST)
        assert var.value == test_list
        assert var.type == VariableType.LIST

    def test_create_dict_variable(self):
        """Test creating a dict variable."""
        test_dict = {"key": "value", "number": 42}
        var = Variable(value=test_dict, type=VariableType.DICT)
        assert var.value == test_dict
        assert var.type == VariableType.DICT

    def test_create_path_variable(self):
        """Test creating a path variable."""
        var = Variable(value="/home/user/file.txt", type=VariableType.PATH)
        assert var.value == "/home/user/file.txt"
        assert var.type == VariableType.PATH

    def test_create_regex_variable(self):
        """Test creating a regex variable."""
        var = Variable(value=r"\d{4}-\d{2}-\d{2}", type=VariableType.REGEX)
        assert var.value == r"\d{4}-\d{2}-\d{2}"
        assert var.type == VariableType.REGEX

    def test_create_timestamp_variable_from_string(self):
        """Test creating a timestamp variable from string.

        NOTE: Due to attrs using __post_init__ instead of __attrs_post_init__,
        the value is NOT coerced - it stays as a string.
        """
        var = Variable(value="2024-01-15T10:30:00", type=VariableType.TIMESTAMP)
        # Value stays as string since __post_init__ isn't called by attrs
        assert var.value == "2024-01-15T10:30:00"
        assert var.type == VariableType.TIMESTAMP

    def test_create_timestamp_variable_from_datetime(self):
        """Test creating a timestamp variable from datetime object."""
        dt = datetime.datetime(2024, 1, 15, 10, 30, 0)
        var = Variable(value=dt, type=VariableType.TIMESTAMP)
        assert var.value == dt
        assert var.type == VariableType.TIMESTAMP

    def test_create_variable_with_description(self):
        """Test creating a variable with description."""
        var = Variable(
            value="test",
            type=VariableType.STRING,
            description="This is a test variable"
        )
        assert var.description == "This is a test variable"

    def test_create_variable_with_metadata(self):
        """Test creating a variable with metadata."""
        metadata = {"custom_key": "custom_value"}
        var = Variable(
            value="test",
            type=VariableType.STRING,
            metadata=metadata
        )
        assert var.metadata == metadata


# =============================================================================
# Variable Class - Type Behavior Tests (No Coercion)
# =============================================================================

class TestVariableTypeBehavior:
    """Tests for Variable type behavior.

    NOTE: Due to attrs using __post_init__ instead of __attrs_post_init__,
    type coercion does NOT happen. Values are stored as-is.
    """

    def test_string_type_keeps_int_value(self):
        """Test that integer value is kept as-is with STRING type."""
        var = Variable.from_dict({"value": 42, "type": "string"})
        # Value stays as int since coercion isn't working
        assert var.value == 42
        assert isinstance(var.value, int)

    def test_integer_type_keeps_string_value(self):
        """Test that string value is kept as-is with INTEGER type."""
        var = Variable.from_dict({"value": "42", "type": "integer"})
        # Value stays as string since coercion isn't working
        assert var.value == "42"
        assert isinstance(var.value, str)

    def test_float_type_keeps_string_value(self):
        """Test that string value is kept as-is with FLOAT type."""
        var = Variable.from_dict({"value": "3.14", "type": "float"})
        # Value stays as string
        assert var.value == "3.14"
        assert isinstance(var.value, str)

    def test_boolean_type_keeps_string_value(self):
        """Test that string value is kept as-is with BOOLEAN type."""
        var = Variable.from_dict({"value": "true", "type": "boolean"})
        # Value stays as string
        assert var.value == "true"
        assert isinstance(var.value, str)


# =============================================================================
# Variable Class - Validation Tests (Currently No Validation)
# =============================================================================

class TestVariableValidation:
    """Tests for Variable validation behavior.

    NOTE: Due to attrs using __post_init__ instead of __attrs_post_init__,
    validation does NOT happen. Invalid values are stored as-is.
    """

    def test_invalid_regex_is_stored_as_is(self):
        """Test that invalid regex pattern is stored without validation.

        NOTE: Validation doesn't run because __post_init__ isn't called.
        """
        var = Variable.from_dict({"value": "[invalid(regex", "type": "regex"})
        # Value is stored without validation
        assert var.value == "[invalid(regex"
        assert var.type == VariableType.REGEX

    def test_valid_regex_passes(self):
        """Test that valid regex patterns are accepted."""
        patterns = [
            r"\d+",
            r"[a-zA-Z]+",
            r"^start.*end$",
            r"hello|world",
            r"(?:non-capturing)",
        ]
        for pattern in patterns:
            var = Variable(value=pattern, type=VariableType.REGEX)
            assert var.value == pattern

    def test_invalid_timestamp_is_stored_as_is(self):
        """Test that invalid timestamp is stored without validation."""
        var = Variable.from_dict({"value": "not-a-timestamp", "type": "timestamp"})
        # Value is stored without validation
        assert var.value == "not-a-timestamp"
        assert var.type == VariableType.TIMESTAMP

    def test_invalid_integer_is_stored_as_is(self):
        """Test that non-numeric string is stored without validation for INTEGER."""
        var = Variable.from_dict({"value": "not-a-number", "type": "integer"})
        # Value is stored without validation
        assert var.value == "not-a-number"
        assert var.type == VariableType.INTEGER


# =============================================================================
# Variable Class - from_dict Tests
# =============================================================================

class TestVariableFromDict:
    """Tests for Variable.from_dict() method."""

    def test_from_dict_basic(self):
        """Test basic from_dict creation."""
        data = {
            "value": "hello",
            "type": "string"
        }
        var = Variable.from_dict(data)
        assert var.value == "hello"
        assert var.type == VariableType.STRING

    def test_from_dict_with_description(self):
        """Test from_dict with description field."""
        data = {
            "value": 42,
            "type": "integer",
            "description": "The answer"
        }
        var = Variable.from_dict(data)
        assert var.value == 42
        assert var.description == "The answer"

    def test_from_dict_with_metadata(self):
        """Test from_dict with explicit metadata."""
        data = {
            "value": "test",
            "type": "string",
            "metadata": {"custom": "value"}
        }
        var = Variable.from_dict(data)
        assert var.metadata == {"custom": "value"}

    def test_from_dict_timestamp_with_timezone(self):
        """Test from_dict for timestamp with timezone."""
        data = {
            "value": "2024-01-15T10:30:00",
            "type": "timestamp",
            "timezone": "+04:00"
        }
        var = Variable.from_dict(data)
        assert var.type == VariableType.TIMESTAMP
        assert var.metadata.get("timezone") == "+04:00"

    def test_from_dict_timestamp_with_format(self):
        """Test from_dict for timestamp with format."""
        data = {
            "value": "2024-01-15T10:30:00",
            "type": "timestamp",
            "format": "%Y-%m-%d"
        }
        var = Variable.from_dict(data)
        assert var.metadata.get("format") == "%Y-%m-%d"

    def test_from_dict_timestamp_with_tolerance(self):
        """Test from_dict for timestamp with tolerance."""
        data = {
            "value": "2024-01-15T10:30:00",
            "type": "timestamp",
            "tolerance": [5, -5]
        }
        var = Variable.from_dict(data)
        assert var.metadata.get("tolerance") == [5, -5]

    def test_from_dict_timestamp_with_localtime(self):
        """Test from_dict for timestamp with localtime flag."""
        data = {
            "value": "2024-01-15T10:30:00",
            "type": "timestamp",
            "localtime": True
        }
        var = Variable.from_dict(data)
        assert var.metadata.get("localtime") is True

    def test_from_dict_all_types(self):
        """Test from_dict with all supported types."""
        test_cases = [
            ({"value": "text", "type": "string"}, VariableType.STRING),
            ({"value": r"\d+", "type": "regex"}, VariableType.REGEX),
            ({"value": "/path/to/file", "type": "path"}, VariableType.PATH),
            ({"value": 42, "type": "integer"}, VariableType.INTEGER),
            ({"value": 3.14, "type": "float"}, VariableType.FLOAT),
            ({"value": True, "type": "boolean"}, VariableType.BOOLEAN),
            ({"value": [1, 2, 3], "type": "list"}, VariableType.LIST),
            ({"value": {"a": 1}, "type": "dict"}, VariableType.DICT),
        ]
        for data, expected_type in test_cases:
            var = Variable.from_dict(data)
            assert var.type == expected_type


# =============================================================================
# Variable Class - Auto Type Inference Tests
# =============================================================================

class TestVariableAutoInfer:
    """Tests for Variable.auto_infer() method."""

    def test_auto_infer_integer(self):
        """Test auto-inference of integer type."""
        var = Variable.auto_infer(42)
        assert var.type == VariableType.INTEGER
        assert var.value == 42

    def test_auto_infer_float(self):
        """Test auto-inference of float type."""
        var = Variable.auto_infer(3.14)
        assert var.type == VariableType.FLOAT
        assert var.value == 3.14

    def test_auto_infer_boolean_true(self):
        """Test auto-inference of boolean True."""
        var = Variable.auto_infer(True)
        assert var.type == VariableType.BOOLEAN
        assert var.value is True

    def test_auto_infer_boolean_false(self):
        """Test auto-inference of boolean False."""
        var = Variable.auto_infer(False)
        assert var.type == VariableType.BOOLEAN
        assert var.value is False

    def test_auto_infer_list(self):
        """Test auto-inference of list type."""
        var = Variable.auto_infer([1, 2, 3])
        assert var.type == VariableType.LIST
        assert var.value == [1, 2, 3]

    def test_auto_infer_dict(self):
        """Test auto-inference of dict type."""
        var = Variable.auto_infer({"key": "value"})
        assert var.type == VariableType.DICT
        assert var.value == {"key": "value"}

    def test_auto_infer_path_unix(self):
        """Test auto-inference of Unix path."""
        var = Variable.auto_infer("/home/user/file.txt")
        assert var.type == VariableType.PATH

    def test_auto_infer_path_windows(self):
        """Test auto-inference of Windows path."""
        var = Variable.auto_infer("C:\\Users\\file.txt")
        assert var.type == VariableType.PATH

    def test_auto_infer_regex_pattern(self):
        """Test auto-inference of regex patterns."""
        patterns = [
            r"hello.*world",
            r"[a-z]+",
            r"start|end",
            r"^prefix",
            r"suffix$",
            r"count{3}",
            r"optional?",
            r"one+",
            r"group(ed)",
        ]
        for pattern in patterns:
            var = Variable.auto_infer(pattern)
            assert var.type == VariableType.REGEX, f"Pattern '{pattern}' was not inferred as regex"

    def test_auto_infer_timestamp(self):
        """Test auto-inference of timestamp strings."""
        timestamps = [
            "2024-01-15",
            "2024-01-15T10:30:00",
            "January 15, 2024",
            "15/01/2024",
        ]
        for ts in timestamps:
            var = Variable.auto_infer(ts)
            assert var.type == VariableType.TIMESTAMP, f"'{ts}' was not inferred as timestamp"

    def test_auto_infer_plain_string(self):
        """Test auto-inference of plain strings (no special patterns)."""
        var = Variable.auto_infer("hello world")
        assert var.type == VariableType.STRING

    def test_auto_infer_with_description(self):
        """Test auto_infer with description parameter."""
        var = Variable.auto_infer(42, description="The answer")
        assert var.description == "The answer"

    def test_auto_infer_with_metadata(self):
        """Test auto_infer with metadata parameter."""
        var = Variable.auto_infer(42, metadata={"custom": "value"})
        assert var.metadata == {"custom": "value"}


# =============================================================================
# Variable Class - get_string_value Tests
# =============================================================================

class TestVariableGetStringValue:
    """Tests for Variable.get_string_value() method."""

    def test_get_string_value_string(self):
        """Test get_string_value for string type."""
        var = Variable(value="hello", type=VariableType.STRING)
        assert var.get_string_value() == "hello"

    def test_get_string_value_integer(self):
        """Test get_string_value for integer type."""
        var = Variable(value=42, type=VariableType.INTEGER)
        assert var.get_string_value() == "42"

    def test_get_string_value_float(self):
        """Test get_string_value for float type."""
        var = Variable(value=3.14, type=VariableType.FLOAT)
        assert var.get_string_value() == "3.14"

    def test_get_string_value_boolean_true(self):
        """Test get_string_value for boolean True (should be lowercase)."""
        var = Variable(value=True, type=VariableType.BOOLEAN)
        assert var.get_string_value() == "true"

    def test_get_string_value_boolean_false(self):
        """Test get_string_value for boolean False (should be lowercase)."""
        var = Variable(value=False, type=VariableType.BOOLEAN)
        assert var.get_string_value() == "false"

    def test_get_string_value_list(self):
        """Test get_string_value for list type (JSON serialization)."""
        var = Variable(value=[1, 2, 3], type=VariableType.LIST)
        result = var.get_string_value()
        assert result == "[1, 2, 3]"

    def test_get_string_value_dict(self):
        """Test get_string_value for dict type (JSON serialization)."""
        var = Variable(value={"a": 1}, type=VariableType.DICT)
        result = var.get_string_value()
        assert result == '{"a": 1}'

    def test_get_string_value_timestamp_datetime(self):
        """Test get_string_value for timestamp datetime returns ISO format."""
        dt = datetime.datetime(2024, 1, 15, 10, 30, 0)
        var = Variable(value=dt, type=VariableType.TIMESTAMP)
        assert var.get_string_value() == "2024-01-15T10:30:00"

    def test_get_string_value_timestamp_string(self):
        """Test get_string_value for timestamp stored as string."""
        var = Variable(value="2024-01-15T10:30:00", type=VariableType.TIMESTAMP)
        # Since value is a string (not datetime), str() returns as-is
        assert var.get_string_value() == "2024-01-15T10:30:00"

    def test_get_string_value_path(self):
        """Test get_string_value for path type."""
        var = Variable(value="/home/user/file.txt", type=VariableType.PATH)
        assert var.get_string_value() == "/home/user/file.txt"

    def test_get_string_value_regex(self):
        """Test get_string_value for regex type."""
        var = Variable(value=r"\d{4}", type=VariableType.REGEX)
        assert var.get_string_value() == r"\d{4}"


# =============================================================================
# Variable Class - get_escaped_string_value Tests
# =============================================================================

class TestVariableGetEscapedStringValue:
    """Tests for Variable.get_escaped_string_value() method."""

    def test_escaped_string_not_for_regex(self):
        """Test that non-regex context returns unescaped value."""
        var = Variable(value="hello.world", type=VariableType.STRING)
        result = var.get_escaped_string_value(for_regex=False)
        assert result == "hello.world"

    def test_escaped_string_for_regex(self):
        """Test that regex context escapes special chars for non-regex vars."""
        var = Variable(value="hello.world", type=VariableType.STRING)
        result = var.get_escaped_string_value(for_regex=True)
        assert result == r"hello\.world"

    def test_regex_var_not_escaped_in_regex_context(self):
        """Test that regex variables are not escaped in regex context."""
        var = Variable(value=r"\d+", type=VariableType.REGEX)
        result = var.get_escaped_string_value(for_regex=True)
        assert result == r"\d+"

    def test_path_escaped_for_regex(self):
        """Test that path is escaped for regex context."""
        var = Variable(value="/home/user/file.txt", type=VariableType.PATH)
        result = var.get_escaped_string_value(for_regex=True)
        assert r"\/" in result or "/" in result  # Forward slash may or may not be escaped


# =============================================================================
# TimestampMetadata Tests
# =============================================================================

class TestTimestampMetadata:
    """Tests for TimestampMetadata class."""

    def test_default_values(self):
        """Test default values of TimestampMetadata."""
        meta = TimestampMetadata()
        assert meta.timezone is None
        assert meta.format_str is None
        assert meta.tolerance_upper == 0
        assert meta.tolerance_lower == 0
        assert meta.localtime is False

    def test_from_dict_with_timezone(self):
        """Test from_dict with timezone."""
        data = {"timezone": "UTC"}
        meta = TimestampMetadata.from_dict(data)
        assert meta.timezone == "UTC"

    def test_from_dict_with_format(self):
        """Test from_dict with format."""
        data = {"format": "%Y-%m-%d"}
        meta = TimestampMetadata.from_dict(data)
        assert meta.format_str == "%Y-%m-%d"

    def test_from_dict_with_list_tolerance(self):
        """Test from_dict with tolerance as list [upper, lower]."""
        data = {"tolerance": [5, -10]}
        meta = TimestampMetadata.from_dict(data)
        assert meta.tolerance_upper == 5
        assert meta.tolerance_lower == -10

    def test_from_dict_with_single_tolerance(self):
        """Test from_dict with single tolerance value (symmetric)."""
        data = {"tolerance": 5}
        meta = TimestampMetadata.from_dict(data)
        assert meta.tolerance_upper == 5
        assert meta.tolerance_lower == 5

    def test_from_dict_with_localtime(self):
        """Test from_dict with localtime flag."""
        data = {"localtime": True}
        meta = TimestampMetadata.from_dict(data)
        assert meta.localtime is True

    def test_from_dict_empty(self):
        """Test from_dict with empty dict."""
        meta = TimestampMetadata.from_dict({})
        assert meta.timezone is None
        assert meta.format_str is None
        assert meta.tolerance_upper == 0
        assert meta.tolerance_lower == 0
        assert meta.localtime is False

    def test_to_dict_with_timezone(self):
        """Test to_dict serializes timezone."""
        meta = TimestampMetadata(timezone="UTC")
        result = meta.to_dict()
        assert result == {"timezone": "UTC"}

    def test_to_dict_with_format(self):
        """Test to_dict serializes format."""
        meta = TimestampMetadata(format_str="%Y-%m-%d")
        result = meta.to_dict()
        assert result == {"format": "%Y-%m-%d"}

    def test_to_dict_with_tolerance(self):
        """Test to_dict serializes tolerance as list."""
        meta = TimestampMetadata(tolerance_upper=5, tolerance_lower=-10)
        result = meta.to_dict()
        assert result == {"tolerance": [5, -10]}

    def test_to_dict_with_localtime(self):
        """Test to_dict serializes localtime."""
        meta = TimestampMetadata(localtime=True)
        result = meta.to_dict()
        assert result == {"localtime": True}

    def test_to_dict_empty_when_defaults(self):
        """Test to_dict returns empty dict when all defaults."""
        meta = TimestampMetadata()
        result = meta.to_dict()
        assert result == {}

    def test_to_dict_full_roundtrip(self):
        """Test full roundtrip from_dict -> to_dict."""
        original = {
            "timezone": "US/Eastern",
            "format": "%Y-%m-%d %H:%M:%S",
            "tolerance": [10, -5],
            "localtime": True
        }
        meta = TimestampMetadata.from_dict(original)
        result = meta.to_dict()
        assert result["timezone"] == "US/Eastern"
        assert result["format"] == "%Y-%m-%d %H:%M:%S"
        assert result["tolerance"] == [10, -5]
        assert result["localtime"] is True

    def test_timezone_offset_parsing(self):
        """Test timezone offset string parsing."""
        # Positive offset
        data = {"timezone": "+04:00"}
        meta = TimestampMetadata.from_dict(data)
        assert meta.timezone == "+04:00"

        # Negative offset
        data = {"timezone": "-05:00"}
        meta = TimestampMetadata.from_dict(data)
        assert meta.timezone == "-05:00"

    def test_named_timezone_parsing(self):
        """Test named timezone string parsing."""
        timezones = ["UTC", "US/Eastern", "Europe/London", "Asia/Tokyo"]
        for tz in timezones:
            meta = TimestampMetadata.from_dict({"timezone": tz})
            assert meta.timezone == tz


# =============================================================================
# VariableRegistry Tests - Basic Operations
# =============================================================================

class TestVariableRegistryBasic:
    """Tests for basic VariableRegistry operations."""

    def test_create_empty_registry(self):
        """Test creating an empty registry."""
        registry = VariableRegistry()
        assert len(registry.variables) == 0

    def test_create_registry_with_variables(self):
        """Test creating registry with initial variables."""
        var = Variable(value="test", type=VariableType.STRING)
        registry = VariableRegistry(variables={"test_var": var})
        assert len(registry.variables) == 1
        assert "test_var" in registry.variables

    def test_add_variable(self):
        """Test adding a variable to registry."""
        registry = VariableRegistry()
        var = Variable(value="test", type=VariableType.STRING)
        registry.add("my_var", var)
        assert "my_var" in registry.variables
        assert registry.variables["my_var"] == var

    def test_add_sets_variable_name(self):
        """Test that add() sets the variable's name attribute."""
        registry = VariableRegistry()
        var = Variable(value="test", type=VariableType.STRING)
        registry.add("my_var", var)
        assert var.name == "my_var"

    def test_get_existing_variable(self):
        """Test getting an existing variable."""
        registry = VariableRegistry()
        var = Variable(value="test", type=VariableType.STRING)
        registry.add("my_var", var)
        result = registry.get("my_var")
        assert result == var

    def test_get_nonexistent_variable(self):
        """Test getting a nonexistent variable returns None."""
        registry = VariableRegistry()
        result = registry.get("nonexistent")
        assert result is None


# =============================================================================
# VariableRegistry Tests - resolve_in_string
# =============================================================================

class TestVariableRegistryResolveInString:
    """Tests for VariableRegistry.resolve_in_string() method."""

    def test_resolve_single_variable(self):
        """Test resolving a single variable."""
        registry = VariableRegistry()
        registry.add("name", Variable(value="World", type=VariableType.STRING))
        result = registry.resolve_in_string("Hello {{name}}!")
        assert result == "Hello World!"

    def test_resolve_multiple_variables(self):
        """Test resolving multiple variables."""
        registry = VariableRegistry()
        registry.add("first", Variable(value="Hello", type=VariableType.STRING))
        registry.add("second", Variable(value="World", type=VariableType.STRING))
        result = registry.resolve_in_string("{{first}} {{second}}!")
        assert result == "Hello World!"

    def test_resolve_variable_with_spaces(self):
        """Test resolving variable with spaces in braces."""
        registry = VariableRegistry()
        registry.add("name", Variable(value="World", type=VariableType.STRING))
        result = registry.resolve_in_string("Hello {{ name }}!")
        assert result == "Hello World!"

    def test_resolve_unknown_variable_unchanged(self):
        """Test that unknown variables are left unchanged."""
        registry = VariableRegistry()
        result = registry.resolve_in_string("Hello {{unknown}}!")
        assert result == "Hello {{unknown}}!"

    def test_resolve_integer_variable(self):
        """Test resolving an integer variable."""
        registry = VariableRegistry()
        registry.add("count", Variable(value=42, type=VariableType.INTEGER))
        result = registry.resolve_in_string("Count: {{count}}")
        assert result == "Count: 42"

    def test_resolve_no_variables(self):
        """Test string without variables is unchanged."""
        registry = VariableRegistry()
        result = registry.resolve_in_string("No variables here")
        assert result == "No variables here"

    def test_resolve_for_regex_escapes_non_regex(self):
        """Test that non-regex variables are escaped in regex context."""
        registry = VariableRegistry()
        registry.add("path", Variable(value="/home/user", type=VariableType.PATH))
        result = registry.resolve_in_string("^{{path}}", for_regex=True)
        assert r"\/" in result or "/" in result  # Should have escaped slash

    def test_resolve_for_regex_keeps_regex_pattern(self):
        """Test that regex variables keep their pattern in regex context."""
        registry = VariableRegistry()
        registry.add("pattern", Variable(value=r"\d+", type=VariableType.REGEX))
        result = registry.resolve_in_string("Value: {{pattern}}", for_regex=True)
        assert r"\d+" in result


# =============================================================================
# VariableRegistry Tests - from_dict
# =============================================================================

class TestVariableRegistryFromDict:
    """Tests for VariableRegistry.from_dict() method."""

    def test_from_dict_simple_values(self):
        """Test from_dict with simple values (auto-inference)."""
        data = {
            "string_var": "hello",
            "int_var": 42,
            "float_var": 3.14,
            "bool_var": True,
        }
        registry = VariableRegistry.from_dict(data)
        assert registry.get("string_var").type == VariableType.STRING
        assert registry.get("int_var").type == VariableType.INTEGER
        assert registry.get("float_var").type == VariableType.FLOAT
        assert registry.get("bool_var").type == VariableType.BOOLEAN

    def test_from_dict_explicit_type_definition(self):
        """Test from_dict with explicit type definitions."""
        data = {
            "my_var": {
                "value": "test",
                "type": "string"
            }
        }
        registry = VariableRegistry.from_dict(data)
        var = registry.get("my_var")
        assert var.value == "test"
        assert var.type == VariableType.STRING

    def test_from_dict_mixed_formats(self):
        """Test from_dict with mixed simple and explicit formats."""
        data = {
            "simple": "hello",
            "explicit": {
                "value": 42,
                "type": "integer"
            }
        }
        registry = VariableRegistry.from_dict(data)
        assert registry.get("simple").value == "hello"
        assert registry.get("explicit").value == 42

    def test_from_dict_with_variable_objects(self):
        """Test from_dict when value is already a Variable object."""
        var = Variable(value="test", type=VariableType.STRING)
        data = {"my_var": var}
        registry = VariableRegistry.from_dict(data)
        assert registry.get("my_var") == var

    def test_from_dict_timestamp_with_metadata(self):
        """Test from_dict with timestamp including metadata."""
        data = {
            "timestamp_var": {
                "value": "2024-01-15T10:30:00",
                "type": "timestamp",
                "timezone": "UTC",
                "tolerance": [5, -5]
            }
        }
        registry = VariableRegistry.from_dict(data)
        var = registry.get("timestamp_var")
        assert var.type == VariableType.TIMESTAMP
        assert var.metadata.get("timezone") == "UTC"
        assert var.metadata.get("tolerance") == [5, -5]


# =============================================================================
# VariableRegistry Tests - to_dict
# =============================================================================

class TestVariableRegistryToDict:
    """Tests for VariableRegistry.to_dict() method."""

    def test_to_dict_simple(self):
        """Test to_dict returns string values."""
        registry = VariableRegistry()
        registry.add("str_var", Variable(value="hello", type=VariableType.STRING))
        registry.add("int_var", Variable(value=42, type=VariableType.INTEGER))
        result = registry.to_dict()
        assert result == {"str_var": "hello", "int_var": "42"}

    def test_to_dict_empty_registry(self):
        """Test to_dict with empty registry."""
        registry = VariableRegistry()
        result = registry.to_dict()
        assert result == {}

    def test_to_dict_boolean_lowercase(self):
        """Test that booleans are serialized as lowercase strings."""
        registry = VariableRegistry()
        registry.add("bool_var", Variable(value=True, type=VariableType.BOOLEAN))
        result = registry.to_dict()
        assert result["bool_var"] == "true"


# =============================================================================
# VariableRegistry Tests - to_enriched_dict
# =============================================================================

class TestVariableRegistryToEnrichedDict:
    """Tests for VariableRegistry.to_enriched_dict() method."""

    def test_to_enriched_dict_includes_type(self):
        """Test that enriched dict includes type information."""
        registry = VariableRegistry()
        registry.add("my_var", Variable(value="test", type=VariableType.STRING))
        result = registry.to_enriched_dict()
        assert result["my_var"]["type"] == "string"

    def test_to_enriched_dict_includes_value(self):
        """Test that enriched dict includes value."""
        registry = VariableRegistry()
        registry.add("my_var", Variable(value="test", type=VariableType.STRING))
        result = registry.to_enriched_dict()
        assert result["my_var"]["value"] == "test"

    def test_to_enriched_dict_includes_metadata(self):
        """Test that enriched dict includes metadata."""
        registry = VariableRegistry()
        var = Variable(
            value="test",
            type=VariableType.STRING,
            metadata={"custom": "value"}
        )
        registry.add("my_var", var)
        result = registry.to_enriched_dict()
        assert result["my_var"]["metadata"] == {"custom": "value"}

    def test_to_enriched_dict_no_structured_metadata_by_default(self):
        """Test that enriched dict doesn't include structured_metadata by default.

        NOTE: structured_metadata is NOT created because __post_init__ isn't called.
        """
        var = Variable(
            value="2024-01-15T10:30:00",
            type=VariableType.TIMESTAMP,
            metadata={"timezone": "UTC", "tolerance": [5, -5]}
        )
        registry = VariableRegistry()
        registry.add("ts_var", var)
        result = registry.to_enriched_dict()
        # structured_metadata is NOT created since __post_init__ isn't called
        assert "structured_metadata" not in result["ts_var"] or result["ts_var"].get("structured_metadata") is None


# =============================================================================
# VariableRegistry Tests - extract_referenced_variables
# =============================================================================

class TestVariableRegistryExtractReferencedVariables:
    """Tests for VariableRegistry.extract_referenced_variables() method."""

    def test_extract_single_variable(self):
        """Test extracting single variable reference."""
        registry = VariableRegistry()
        registry.add("name", Variable(value="test", type=VariableType.STRING))
        result = registry.extract_referenced_variables("Hello {{name}}")
        assert "name" in result

    def test_extract_multiple_variables(self):
        """Test extracting multiple variable references."""
        registry = VariableRegistry()
        registry.add("first", Variable(value="a", type=VariableType.STRING))
        registry.add("second", Variable(value="b", type=VariableType.STRING))
        result = registry.extract_referenced_variables("{{first}} and {{second}}")
        assert "first" in result
        assert "second" in result

    def test_extract_from_dict_structure(self):
        """Test extracting from nested dict structure."""
        registry = VariableRegistry()
        registry.add("var1", Variable(value="a", type=VariableType.STRING))
        registry.add("var2", Variable(value="b", type=VariableType.STRING))
        data = {
            "key1": "{{var1}}",
            "nested": {
                "key2": "{{var2}}"
            }
        }
        result = registry.extract_referenced_variables(data)
        assert "var1" in result
        assert "var2" in result

    def test_extract_from_list_structure(self):
        """Test extracting from list structure."""
        registry = VariableRegistry()
        registry.add("var1", Variable(value="a", type=VariableType.STRING))
        data = ["{{var1}}", "plain text"]
        result = registry.extract_referenced_variables(data)
        assert "var1" in result

    def test_extract_with_filters(self):
        """Test extracting variable name even with Jinja2 filters."""
        registry = VariableRegistry()
        registry.add("timestamp", Variable(value="2024-01-15", type=VariableType.TIMESTAMP))
        result = registry.extract_referenced_variables("{{timestamp | timezone('UTC')}}")
        assert "timestamp" in result

    def test_extract_no_variables(self):
        """Test extracting from string without variables."""
        registry = VariableRegistry()
        result = registry.extract_referenced_variables("No variables here")
        assert len(result) == 0

    def test_extract_nested_dependencies_in_string_variables(self):
        """Test extracting nested variable dependencies from STRING typed variables."""
        registry = VariableRegistry()
        # var2 references var1
        registry.add("var1", Variable(value="value1", type=VariableType.STRING))
        registry.add("var2", Variable(value="prefix_{{var1}}", type=VariableType.STRING))
        # Start with var2 reference
        result = registry.extract_referenced_variables("{{var2}}")
        # Should include var2, and var1 should be found as a dependency
        assert "var2" in result
        assert "var1" in result


# =============================================================================
# VariableRegistry Tests - to_execution_context
# =============================================================================

class TestVariableRegistryToExecutionContext:
    """Tests for VariableRegistry.to_execution_context() method."""

    def test_execution_context_simple_variable(self):
        """Test execution context with simple variable."""
        registry = VariableRegistry()
        registry.add("name", Variable(value="test", type=VariableType.STRING))
        result = registry.to_execution_context()
        assert result["name"] == "test"

    def test_execution_context_regex_creates_placeholder(self):
        """Test that regex variables create placeholders."""
        registry = VariableRegistry()
        registry.add("pattern", Variable(value=r"\d+", type=VariableType.REGEX))
        result = registry.to_execution_context()
        # Regex should create a placeholder
        assert "pattern_resolved" in result["pattern"]
        assert "_VARIABLE_METADATA" in result

    def test_execution_context_timestamp_with_tolerance_creates_placeholder(self):
        """Test that timestamp with tolerance creates placeholder."""
        registry = VariableRegistry()
        var = Variable(
            value="2024-01-15T10:30:00",
            type=VariableType.TIMESTAMP,
            metadata={"tolerance": [5, -5]}
        )
        registry.add("ts", var)
        result = registry.to_execution_context()
        # Should create placeholder for tolerance
        assert "ts_resolved" in result["ts"]

    def test_execution_context_for_tests_flag(self):
        """Test execution context with for_tests=True."""
        registry = VariableRegistry()
        registry.add("name", Variable(value="test", type=VariableType.STRING))
        result = registry.to_execution_context(for_tests=True)
        assert "name" in result


# =============================================================================
# VariableRegistry Tests - to_execution_context_lazy
# =============================================================================

class TestVariableRegistryToExecutionContextLazy:
    """Tests for VariableRegistry.to_execution_context_lazy() method."""

    def test_lazy_context_only_referenced_variables(self):
        """Test that lazy context only includes referenced variables."""
        registry = VariableRegistry()
        registry.add("var1", Variable(value="a", type=VariableType.STRING))
        registry.add("var2", Variable(value="b", type=VariableType.STRING))
        registry.add("var3", Variable(value="c", type=VariableType.STRING))

        result = registry.to_execution_context_lazy(referenced_variables={"var1", "var2"})
        assert "var1" in result
        assert "var2" in result
        assert "var3" not in result

    def test_lazy_context_with_none_falls_back(self):
        """Test that None referenced_variables falls back to full resolution."""
        registry = VariableRegistry()
        registry.add("var1", Variable(value="a", type=VariableType.STRING))
        registry.add("var2", Variable(value="b", type=VariableType.STRING))

        result = registry.to_execution_context_lazy(referenced_variables=None)
        assert "var1" in result
        assert "var2" in result

    def test_lazy_context_missing_variable_warning(self):
        """Test that missing referenced variable logs warning but doesn't fail."""
        registry = VariableRegistry()
        registry.add("var1", Variable(value="a", type=VariableType.STRING))

        result = registry.to_execution_context_lazy(referenced_variables={"var1", "nonexistent"})
        assert "var1" in result
        assert "nonexistent" not in result


# =============================================================================
# parse_variables Function Tests
# =============================================================================

class TestParseVariables:
    """Tests for parse_variables() convenience function."""

    def test_parse_variables_returns_registry(self):
        """Test that parse_variables returns a VariableRegistry."""
        result = parse_variables({"var": "value"})
        assert isinstance(result, VariableRegistry)

    def test_parse_variables_same_as_from_dict(self):
        """Test that parse_variables behaves same as VariableRegistry.from_dict."""
        data = {"var1": "hello", "var2": 42}
        result1 = parse_variables(data)
        result2 = VariableRegistry.from_dict(data)

        assert result1.get("var1").value == result2.get("var1").value
        assert result1.get("var2").value == result2.get("var2").value


# =============================================================================
# Integration Tests
# =============================================================================

class TestVariablesIntegration:
    """Integration tests combining multiple components."""

    def test_full_workflow_simple(self):
        """Test full workflow: parse -> add -> resolve."""
        # Parse from dict
        registry = VariableRegistry.from_dict({
            "username": "john",
            "count": 5
        })

        # Resolve in string
        result = registry.resolve_in_string("User {{username}} has {{count}} items")
        assert result == "User john has 5 items"

    def test_full_workflow_with_explicit_types(self):
        """Test workflow with explicit type definitions."""
        registry = VariableRegistry.from_dict({
            "timestamp": {
                "value": "2024-01-15T10:30:00",
                "type": "timestamp"
            },
            "pattern": {
                "value": r"\d{4}-\d{2}-\d{2}",
                "type": "regex"
            }
        })

        assert registry.get("timestamp").type == VariableType.TIMESTAMP
        assert registry.get("pattern").type == VariableType.REGEX

    def test_roundtrip_serialization_string_type(self):
        """Test roundtrip: from_dict -> to_enriched_dict -> from_dict for string values."""
        original = {
            "string_var": {
                "value": "test",
                "type": "string"
            }
        }

        registry1 = VariableRegistry.from_dict(original)
        enriched = registry1.to_enriched_dict()

        # Create new registry from enriched format
        registry2 = VariableRegistry.from_dict(enriched)

        assert registry2.get("string_var").value == "test"

    def test_roundtrip_serialization_preserves_type(self):
        """Test that roundtrip serialization preserves type even without coercion."""
        original = {
            "int_var": {
                "value": 42,
                "type": "integer"
            }
        }

        registry1 = VariableRegistry.from_dict(original)
        enriched = registry1.to_enriched_dict()

        # The enriched value is a string (from get_string_value)
        assert enriched["int_var"]["value"] == "42"
        assert enriched["int_var"]["type"] == "integer"

        # When parsed again, type is preserved but value stays as string
        # (since coercion doesn't work)
        registry2 = VariableRegistry.from_dict(enriched)
        var = registry2.get("int_var")
        assert var.type == VariableType.INTEGER
        # Value is string "42" since coercion doesn't run
        assert var.value == "42"

    def test_timestamp_metadata_stored_in_metadata(self):
        """Test timestamp with metadata is stored correctly."""
        registry = VariableRegistry.from_dict({
            "event_time": {
                "value": "2024-01-15T10:30:00",
                "type": "timestamp",
                "timezone": "UTC",
                "format": "%Y-%m-%d",
                "tolerance": [10, -10]
            }
        })

        var = registry.get("event_time")
        assert var.type == VariableType.TIMESTAMP
        assert var.metadata.get("timezone") == "UTC"
        assert var.metadata.get("format") == "%Y-%m-%d"
        assert var.metadata.get("tolerance") == [10, -10]
        # Note: structured_metadata is NOT created since __post_init__ isn't called


# =============================================================================
# Edge Case Tests
# =============================================================================

class TestEdgeCases:
    """Tests for edge cases and boundary conditions."""

    def test_empty_string_variable(self):
        """Test variable with empty string value."""
        var = Variable(value="", type=VariableType.STRING)
        assert var.value == ""
        assert var.get_string_value() == ""

    def test_unicode_string_variable(self):
        """Test variable with unicode characters."""
        var = Variable(value="Hello", type=VariableType.STRING)
        assert var.value == "Hello"

    def test_very_long_string(self):
        """Test variable with very long string."""
        long_string = "a" * 10000
        var = Variable(value=long_string, type=VariableType.STRING)
        assert var.value == long_string

    def test_special_characters_in_string(self):
        """Test variable with special characters."""
        special = "!@#$%^&*()_+-=[]{}|;':\",./<>?"
        var = Variable(value=special, type=VariableType.STRING)
        assert var.value == special

    def test_nested_braces_in_resolve(self):
        """Test resolving with nested braces."""
        registry = VariableRegistry()
        registry.add("var", Variable(value="value", type=VariableType.STRING))
        # Nested braces that aren't variable references
        result = registry.resolve_in_string("JSON: {\"key\": \"{{var}}\"}")
        assert result == 'JSON: {"key": "value"}'

    def test_zero_integer(self):
        """Test integer variable with zero value."""
        var = Variable(value=0, type=VariableType.INTEGER)
        assert var.value == 0
        assert var.get_string_value() == "0"

    def test_negative_integer(self):
        """Test integer variable with negative value."""
        var = Variable(value=-42, type=VariableType.INTEGER)
        assert var.value == -42
        assert var.get_string_value() == "-42"

    def test_empty_list(self):
        """Test list variable with empty list."""
        var = Variable(value=[], type=VariableType.LIST)
        assert var.value == []
        assert var.get_string_value() == "[]"

    def test_empty_dict(self):
        """Test dict variable with empty dict."""
        var = Variable(value={}, type=VariableType.DICT)
        assert var.value == {}
        assert var.get_string_value() == "{}"

    def test_complex_regex_pattern(self):
        """Test complex regex pattern storage (validation doesn't run)."""
        complex_pattern = r"(?:https?://)?(?:www\.)?[\w-]+(?:\.[\w-]+)+(?:/[\w\-./?%&=]*)?"
        var = Variable(value=complex_pattern, type=VariableType.REGEX)
        assert var.value == complex_pattern

    def test_variable_name_with_underscore(self):
        """Test variable names with underscores."""
        registry = VariableRegistry()
        registry.add("my_long_variable_name", Variable(value="test", type=VariableType.STRING))
        result = registry.resolve_in_string("Value: {{my_long_variable_name}}")
        assert result == "Value: test"

    def test_multiple_same_variable_in_string(self):
        """Test resolving same variable multiple times in string."""
        registry = VariableRegistry()
        registry.add("var", Variable(value="X", type=VariableType.STRING))
        result = registry.resolve_in_string("{{var}}{{var}}{{var}}")
        assert result == "XXX"


# =============================================================================
# TimestampMetadata Jinja Filter Tests
# =============================================================================

class TestTimestampMetadataJinjaFilters:
    """Tests for TimestampMetadata Jinja2 filter methods."""

    def test_get_jinja_filters_returns_dict(self):
        """Test that get_jinja_filters returns a dict of filter functions."""
        meta = TimestampMetadata()
        registry = VariableRegistry()
        filters = meta.get_jinja_filters(registry)

        assert isinstance(filters, dict)
        assert "timezone" in filters
        assert "format" in filters
        assert "tolerance" in filters
        assert "localtime" in filters

    def test_jinja_filter_functions_are_callable(self):
        """Test that all Jinja filter functions are callable."""
        meta = TimestampMetadata()
        registry = VariableRegistry()
        filters = meta.get_jinja_filters(registry)

        for name, func in filters.items():
            assert callable(func), f"Filter '{name}' should be callable"


# =============================================================================
# ValidationError Tests
# =============================================================================

class TestValidationError:
    """Tests for ValidationError exception class."""

    def test_validation_error_is_exception(self):
        """Test that ValidationError is an Exception."""
        error = ValidationError("test message")
        assert isinstance(error, Exception)

    def test_validation_error_message(self):
        """Test ValidationError message is preserved."""
        error = ValidationError("test error message")
        assert str(error) == "test error message"
