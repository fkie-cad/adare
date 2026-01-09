"""
Comprehensive unit tests for adarelib.testset.basictest module.

Tests:
- Placeholder detection (has_placeholders, get_placeholders)
- get_placeholder_metadata
- has_tolerance_metadata
- compare_with_placeholder for regex, string, timestamp types
- resolve_globfilepath with different match modes
- Parameter dataclass
- Helper functions (resolve_var_in_match_regex, resolve_var_in_match_string, resolve_yamlobj_in_dict)
"""
import pytest
import re
import tempfile
import os
from pathlib import Path
from typing import Optional, Dict, Any
from unittest.mock import MagicMock, patch
import attrs
import datetime

from adarelib.testset.basictest import (
    BasicTest,
    Parameter,
    resolve_var_in_match_regex,
    resolve_var_in_match_string,
    resolve_yamlobj_in_dict,
)
from adarelib.testset.yaml.customtags import YamlCustomTag, YamlString, YamlRegexString


# === Test Helper Classes ===

@attrs.define
class SampleParameter(Parameter):
    """Minimal testable parameter subclass."""
    filepath: str = ""
    expected_content: str = ""


@attrs.define
class ConcreteBasicTest(BasicTest):
    """Minimal testable subclass of BasicTest for unit testing."""
    testname = "concrete_test"  # ClassVar, not instance attr
    testdescription = "A concrete test implementation for testing"  # ClassVar

    def test(self):
        """Implementation of abstract test method."""
        return {"success": True, "message": "Test passed"}


# === Fixtures ===

@pytest.fixture
def basic_test_instance():
    """Create a basic test instance with no metadata."""
    return ConcreteBasicTest(
        name="test_instance",
        parameter=SampleParameter(),
        description="Test description",
        variable_metadata=None
    )


@pytest.fixture
def basic_test_with_metadata():
    """Create a basic test instance with variable metadata."""
    metadata = {
        "TIMESTAMP_VAR": {
            "type": "timestamp",
            "raw_value": "2024-01-15T10:30:00",
            "resolved_value": "2024-01-15T10:30:00",
            "tolerance": [5, -5]
        },
        "REGEX_VAR": {
            "type": "regex",
            "raw_value": r"\d{4}-\d{2}-\d{2}",
            "resolved_value": r"\d{4}-\d{2}-\d{2}"
        },
        "STRING_VAR": {
            "type": "string",
            "raw_value": "expected_value",
            "resolved_value": "expected_value"
        }
    }
    return ConcreteBasicTest(
        name="test_with_metadata",
        parameter=SampleParameter(),
        description="Test with metadata",
        variable_metadata=metadata
    )


@pytest.fixture
def temp_dir_with_files(tmp_path):
    """Create a temp directory with some test files."""
    # Create some files for glob testing
    (tmp_path / "file1.txt").write_text("content1")
    (tmp_path / "file2.txt").write_text("content2")
    (tmp_path / "data.json").write_text("{}")
    return tmp_path


# === Tests for Parameter Dataclass ===

class TestParameterDataclass:
    """Tests for the Parameter dataclass."""

    def test_parameter_creation(self):
        """Test basic Parameter instantiation."""
        param = Parameter()
        assert param is not None

    def test_parameter_subclass(self):
        """Test subclassing Parameter."""
        param = SampleParameter(filepath="/test/path", expected_content="test")
        assert param.filepath == "/test/path"
        assert param.expected_content == "test"


# === Tests for Placeholder Methods ===

class TestHasPlaceholders:
    """Tests for has_placeholders method."""

    def test_no_placeholders(self, basic_test_instance):
        """Test text with no placeholders."""
        assert basic_test_instance.has_placeholders("simple text") is False

    def test_single_placeholder(self, basic_test_instance):
        """Test text with single placeholder."""
        assert basic_test_instance.has_placeholders("text with {{ VAR }}") is True

    def test_multiple_placeholders(self, basic_test_instance):
        """Test text with multiple placeholders."""
        text = "{{ VAR1 }} and {{ VAR2 }}"
        assert basic_test_instance.has_placeholders(text) is True

    def test_incomplete_placeholder_opening(self, basic_test_instance):
        """Test text with only opening braces."""
        assert basic_test_instance.has_placeholders("text {{ only open") is False

    def test_incomplete_placeholder_closing(self, basic_test_instance):
        """Test text with only closing braces."""
        assert basic_test_instance.has_placeholders("text }} only close") is False

    def test_single_braces(self, basic_test_instance):
        """Test text with single braces (not placeholders)."""
        assert basic_test_instance.has_placeholders("text { not } placeholder") is False

    def test_empty_placeholder(self, basic_test_instance):
        """Test empty placeholder."""
        assert basic_test_instance.has_placeholders("text {{}} empty") is True


class TestGetPlaceholders:
    """Tests for get_placeholders method."""

    def test_no_placeholders(self, basic_test_instance):
        """Test extracting from text with no placeholders."""
        result = basic_test_instance.get_placeholders("simple text")
        assert result == []

    def test_single_placeholder(self, basic_test_instance):
        """Test extracting single placeholder."""
        result = basic_test_instance.get_placeholders("text {{ VAR }}")
        assert result == ["VAR"]

    def test_multiple_placeholders(self, basic_test_instance):
        """Test extracting multiple placeholders."""
        text = "{{ VAR1 }} and {{ VAR2 }} and {{ VAR3 }}"
        result = basic_test_instance.get_placeholders(text)
        assert result == ["VAR1", "VAR2", "VAR3"]

    def test_placeholder_with_spaces(self, basic_test_instance):
        """Test placeholders with varying whitespace."""
        text = "{{VAR1}} and {{  VAR2  }} and {{ VAR3}}"
        result = basic_test_instance.get_placeholders(text)
        assert result == ["VAR1", "VAR2", "VAR3"]

    def test_duplicate_placeholders(self, basic_test_instance):
        """Test text with duplicate placeholders."""
        text = "{{ VAR }} and {{ VAR }} again"
        result = basic_test_instance.get_placeholders(text)
        assert result == ["VAR", "VAR"]


# === Tests for Metadata Methods ===

class TestGetPlaceholderMetadata:
    """Tests for get_placeholder_metadata method."""

    def test_no_metadata(self, basic_test_instance):
        """Test getting metadata when no variable_metadata exists."""
        result = basic_test_instance.get_placeholder_metadata("ANY_VAR")
        assert result == {}

    def test_nonexistent_placeholder(self, basic_test_with_metadata):
        """Test getting metadata for a placeholder that doesn't exist."""
        result = basic_test_with_metadata.get_placeholder_metadata("NONEXISTENT")
        assert result == {}

    def test_existing_placeholder(self, basic_test_with_metadata):
        """Test getting metadata for an existing placeholder."""
        result = basic_test_with_metadata.get_placeholder_metadata("STRING_VAR")
        assert result["type"] == "string"
        assert result["resolved_value"] == "expected_value"


class TestHasToleranceMetadata:
    """Tests for has_tolerance_metadata method."""

    def test_no_metadata(self, basic_test_instance):
        """Test tolerance check when no metadata exists."""
        assert basic_test_instance.has_tolerance_metadata("ANY_VAR") is False

    def test_placeholder_without_tolerance(self, basic_test_with_metadata):
        """Test placeholder that has no tolerance defined."""
        assert basic_test_with_metadata.has_tolerance_metadata("STRING_VAR") is False

    def test_placeholder_with_tolerance(self, basic_test_with_metadata):
        """Test placeholder that has tolerance defined."""
        assert basic_test_with_metadata.has_tolerance_metadata("TIMESTAMP_VAR") is True


# === Tests for compare_with_placeholder ===

class TestCompareWithPlaceholder:
    """Tests for compare_with_placeholder method."""

    def test_regex_match_success(self, basic_test_with_metadata):
        """Test regex placeholder matching correctly."""
        success, msg = basic_test_with_metadata.compare_with_placeholder(
            "REGEX_VAR", "2024-01-15"
        )
        assert success is True
        assert "Regex match" in msg

    def test_regex_match_failure(self, basic_test_with_metadata):
        """Test regex placeholder not matching."""
        success, msg = basic_test_with_metadata.compare_with_placeholder(
            "REGEX_VAR", "not-a-date"
        )
        assert success is False
        assert "no match" in msg

    def test_string_exact_match(self, basic_test_with_metadata):
        """Test string placeholder exact match."""
        success, msg = basic_test_with_metadata.compare_with_placeholder(
            "STRING_VAR", "expected_value"
        )
        assert success is True
        assert "match" in msg

    def test_string_no_match(self, basic_test_with_metadata):
        """Test string placeholder not matching."""
        success, msg = basic_test_with_metadata.compare_with_placeholder(
            "STRING_VAR", "different_value"
        )
        assert success is False
        assert "no match" in msg

    def test_nonexistent_placeholder_defaults_to_string(self, basic_test_with_metadata):
        """Test that nonexistent placeholder uses string comparison."""
        success, msg = basic_test_with_metadata.compare_with_placeholder(
            "NONEXISTENT", ""
        )
        # Should do exact string comparison with empty expected value
        assert success is True
        assert "comparison" in msg.lower()

    def test_invalid_regex_pattern(self, basic_test_with_metadata):
        """Test handling of invalid regex pattern."""
        # Create metadata with invalid regex
        basic_test_with_metadata.variable_metadata["INVALID_REGEX"] = {
            "type": "regex",
            "raw_value": "[invalid(regex",
            "resolved_value": "[invalid(regex"
        }
        success, msg = basic_test_with_metadata.compare_with_placeholder(
            "INVALID_REGEX", "any value"
        )
        assert success is False
        assert "Regex error" in msg


class TestCompareTimestampWithTolerance:
    """Tests for timestamp comparison with tolerance."""

    def test_timestamp_within_tolerance(self):
        """Test timestamp within tolerance range."""
        metadata = {
            "TIMESTAMP": {
                "type": "timestamp",
                "raw_value": "1705314600",  # 2024-01-15 10:30:00 UTC
                "resolved_value": "1705314600",
                "tolerance": [5, -5]
            }
        }
        test = ConcreteBasicTest(
            name="timestamp_test",
            parameter=SampleParameter(),
            description="Test",
            variable_metadata=metadata
        )
        # Test with value 2 seconds different (within 5 second tolerance)
        success, msg = test.compare_with_placeholder("TIMESTAMP", "1705314602")
        assert success is True
        assert "Within tolerance" in msg

    def test_timestamp_outside_tolerance(self):
        """Test timestamp outside tolerance range."""
        metadata = {
            "TIMESTAMP": {
                "type": "timestamp",
                "raw_value": "1705314600",  # 2024-01-15 10:30:00 UTC
                "resolved_value": "1705314600",
                "tolerance": [5, -5]
            }
        }
        test = ConcreteBasicTest(
            name="timestamp_test",
            parameter=SampleParameter(),
            description="Test",
            variable_metadata=metadata
        )
        # Test with value 10 seconds different (outside 5 second tolerance)
        success, msg = test.compare_with_placeholder("TIMESTAMP", "1705314610")
        assert success is False
        assert "Outside tolerance" in msg

    def test_timestamp_no_tolerance_exact_match(self):
        """Test timestamp without tolerance doing exact comparison."""
        metadata = {
            "TIMESTAMP": {
                "type": "timestamp",
                "raw_value": "2024-01-15T10:30:00",
                "resolved_value": "2024-01-15T10:30:00"
                # No tolerance specified
            }
        }
        test = ConcreteBasicTest(
            name="timestamp_test",
            parameter=SampleParameter(),
            description="Test",
            variable_metadata=metadata
        )
        success, msg = test.compare_with_placeholder("TIMESTAMP", "2024-01-15T10:30:00")
        assert success is True


# === Tests for resolve_globfilepath ===

class TestResolveGlobfilepath:
    """Tests for resolve_globfilepath method."""

    def test_simple_path_no_glob(self, basic_test_instance, tmp_path):
        """Test simple file path without glob patterns."""
        test_file = tmp_path / "test.txt"
        test_file.write_text("test content")

        result, error = basic_test_instance.resolve_globfilepath(str(test_file))
        assert error == ""
        assert result == str(test_file)

    def test_nonexistent_simple_path(self, basic_test_instance, tmp_path):
        """Test non-existent simple path - should return path directly."""
        nonexistent = str(tmp_path / "nonexistent.txt")
        result, error = basic_test_instance.resolve_globfilepath(nonexistent)
        # Simple paths without glob patterns return directly (allows testing file-not-found scenarios)
        assert result == nonexistent
        assert error == ""

    def test_glob_single_match(self, basic_test_instance, temp_dir_with_files):
        """Test glob pattern with single match."""
        pattern = str(temp_dir_with_files / "*.json")
        result, error = basic_test_instance.resolve_globfilepath(pattern)
        assert error == ""
        assert result.endswith("data.json")

    def test_glob_multiple_matches_single_mode(self, basic_test_instance, temp_dir_with_files):
        """Test glob pattern with multiple matches in single mode."""
        pattern = str(temp_dir_with_files / "*.txt")
        result, error = basic_test_instance.resolve_globfilepath(pattern, match_mode="single")
        assert "2 files found" in error
        assert result == ""

    def test_glob_no_matches_single_mode(self, basic_test_instance, temp_dir_with_files):
        """Test glob pattern with no matches in single mode."""
        pattern = str(temp_dir_with_files / "*.nonexistent")
        result, error = basic_test_instance.resolve_globfilepath(pattern, match_mode="single")
        assert "no files match" in error
        assert result == ""

    def test_glob_any_mode_multiple_matches(self, basic_test_instance, temp_dir_with_files):
        """Test glob pattern with multiple matches in any mode."""
        pattern = str(temp_dir_with_files / "*.txt")
        result, error = basic_test_instance.resolve_globfilepath(pattern, match_mode="any")
        assert error == ""
        assert "file1.txt" in result or "file2.txt" in result  # Returns first match

    def test_glob_any_mode_no_matches(self, basic_test_instance, temp_dir_with_files):
        """Test glob pattern with no matches in any mode."""
        pattern = str(temp_dir_with_files / "*.nonexistent")
        result, error = basic_test_instance.resolve_globfilepath(pattern, match_mode="any")
        assert error == ""
        assert result == ""

    def test_return_list_single_match(self, basic_test_instance, temp_dir_with_files):
        """Test return_list parameter with single match."""
        pattern = str(temp_dir_with_files / "*.json")
        result, error = basic_test_instance.resolve_globfilepath(
            pattern, match_mode="single", return_list=True
        )
        assert error == ""
        assert isinstance(result, list)
        assert len(result) == 1

    def test_return_list_any_mode(self, basic_test_instance, temp_dir_with_files):
        """Test return_list parameter in any mode."""
        pattern = str(temp_dir_with_files / "*.txt")
        result, error = basic_test_instance.resolve_globfilepath(
            pattern, match_mode="any", return_list=True
        )
        assert error == ""
        assert isinstance(result, list)
        assert len(result) == 2

    def test_return_list_no_matches(self, basic_test_instance, temp_dir_with_files):
        """Test return_list parameter with no matches."""
        pattern = str(temp_dir_with_files / "*.nonexistent")
        result, error = basic_test_instance.resolve_globfilepath(
            pattern, match_mode="single", return_list=True
        )
        assert isinstance(result, list)
        assert len(result) == 0

    def test_glob_with_question_mark(self, basic_test_instance, temp_dir_with_files):
        """Test glob pattern with ? wildcard."""
        pattern = str(temp_dir_with_files / "file?.txt")
        result, error = basic_test_instance.resolve_globfilepath(
            pattern, match_mode="any", return_list=True
        )
        assert error == ""
        assert len(result) == 2

    def test_glob_with_brackets(self, basic_test_instance, temp_dir_with_files):
        """Test glob pattern with brackets."""
        pattern = str(temp_dir_with_files / "file[12].txt")
        result, error = basic_test_instance.resolve_globfilepath(
            pattern, match_mode="any", return_list=True
        )
        assert error == ""
        assert len(result) == 2


# === Tests for Helper Functions ===

class TestResolveVarInMatchRegex:
    """Tests for resolve_var_in_match_regex function."""

    def test_variable_found(self):
        """Test variable resolution when variable exists."""
        variables = {"username": "john.doe"}
        match = re.search(r'\{\{(\w+)\}\}', "{{username}}")
        result = resolve_var_in_match_regex(match, variables)
        assert result == re.escape("john.doe")

    def test_variable_not_found(self):
        """Test variable resolution when variable doesn't exist."""
        variables = {"other": "value"}
        match = re.search(r'\{\{(\w+)\}\}', "{{username}}")
        result = resolve_var_in_match_regex(match, variables)
        assert result == ""

    def test_special_regex_chars_escaped(self):
        """Test that special regex characters are escaped."""
        variables = {"path": "/home/user.*+?"}
        match = re.search(r'\{\{(\w+)\}\}', "{{path}}")
        result = resolve_var_in_match_regex(match, variables)
        # The result should have escaped regex characters
        assert "\\." in result
        assert "\\*" in result
        assert "\\+" in result
        assert "\\?" in result


class TestResolveVarInMatchString:
    """Tests for resolve_var_in_match_string function."""

    def test_variable_found(self):
        """Test variable resolution when variable exists."""
        variables = {"username": "john.doe"}
        match = re.search(r'\{\{(\w+)\}\}', "{{username}}")
        result = resolve_var_in_match_string(match, variables)
        assert result == "john.doe"

    def test_variable_not_found(self):
        """Test variable resolution when variable doesn't exist."""
        variables = {"other": "value"}
        match = re.search(r'\{\{(\w+)\}\}', "{{username}}")
        result = resolve_var_in_match_string(match, variables)
        assert result == ""

    def test_special_chars_not_escaped(self):
        """Test that special characters are NOT escaped (unlike regex variant)."""
        variables = {"path": "/home/user.*+?"}
        match = re.search(r'\{\{(\w+)\}\}', "{{path}}")
        result = resolve_var_in_match_string(match, variables)
        # The result should NOT have escaped characters
        assert result == "/home/user.*+?"


class TestResolveYamlobjInDict:
    """Tests for resolve_yamlobj_in_dict function."""

    def test_empty_dict(self):
        """Test with empty dictionary."""
        result = resolve_yamlobj_in_dict({})
        assert result == {}

    def test_dict_without_yaml_objects(self):
        """Test dictionary without YamlCustomTag objects."""
        input_dict = {"key1": "value1", "key2": 123, "key3": True}
        result = resolve_yamlobj_in_dict(input_dict)
        assert result == input_dict

    def test_dict_with_yaml_string_object(self):
        """Test dictionary containing YamlString object."""
        yaml_string = YamlString("test value")
        input_dict = {"key1": yaml_string, "key2": "normal"}
        result = resolve_yamlobj_in_dict(input_dict)
        assert "!s test value" in result["key1"]
        assert result["key2"] == "normal"

    def test_nested_dict_with_yaml_objects(self):
        """Test nested dictionary with YamlCustomTag objects."""
        yaml_string = YamlString("nested value")
        input_dict = {
            "outer": {
                "inner": yaml_string,
                "normal": "value"
            }
        }
        result = resolve_yamlobj_in_dict(input_dict)
        assert "!s nested value" in result["outer"]["inner"]
        assert result["outer"]["normal"] == "value"

    def test_list_with_yaml_objects(self):
        """Test dictionary with list containing YamlCustomTag objects."""
        yaml_string = YamlString("list value")
        input_dict = {
            "items": [yaml_string, "normal_item", YamlString("another")]
        }
        result = resolve_yamlobj_in_dict(input_dict)
        assert len(result["items"]) == 3
        assert "!s list value" in result["items"][0]
        assert result["items"][1] == "normal_item"
        assert "!s another" in result["items"][2]


# === Tests for BasicTest Class Attributes ===

class TestBasicTestClassAttributes:
    """Tests for BasicTest class-level attributes."""

    def test_class_variables(self):
        """Test class variable defaults."""
        assert BasicTest.testname == ""
        assert BasicTest.testdescription == ""
        assert BasicTest.execute_on_host is False

    def test_subclass_can_override_class_vars(self):
        """Test that subclasses can override class variables."""
        assert ConcreteBasicTest.testname == "concrete_test"
        assert ConcreteBasicTest.testdescription == "A concrete test implementation for testing"


# === Tests for _handle_placeholders_comparison ===

class TestHandlePlaceholdersComparison:
    """Tests for _handle_placeholders_comparison method."""

    def test_single_placeholder_match(self, basic_test_with_metadata):
        """Test comparison with single placeholder that matches."""
        actual = "prefix expected_value suffix"
        template = "prefix {{ STRING_VAR }} suffix"
        success, msg = basic_test_with_metadata._handle_placeholders_comparison(
            actual, template
        )
        assert success is True
        assert "All placeholders valid" in msg

    def test_single_placeholder_no_match(self, basic_test_with_metadata):
        """Test comparison with single placeholder that doesn't match."""
        actual = "prefix wrong_value suffix"
        template = "prefix {{ STRING_VAR }} suffix"
        success, msg = basic_test_with_metadata._handle_placeholders_comparison(
            actual, template
        )
        assert success is False
        assert "no match" in msg.lower()

    def test_prefix_mismatch(self, basic_test_with_metadata):
        """Test comparison when prefix doesn't match."""
        actual = "wrong_prefix expected_value suffix"
        template = "prefix {{ STRING_VAR }} suffix"
        success, msg = basic_test_with_metadata._handle_placeholders_comparison(
            actual, template
        )
        assert success is False
        assert "doesn't match" in msg

    def test_unconverted_jinja2_template(self, basic_test_with_metadata):
        """Test detection of unconverted Jinja2 templates with pipes."""
        actual = "some content"
        template = "{{ VAR | filter }}"  # Contains pipe which indicates Jinja2 filter
        success, msg = basic_test_with_metadata._handle_placeholders_comparison(
            actual, template
        )
        assert success is False
        assert "unconverted Jinja2 template" in msg


# === Tests for _parse_timestamp_with_format ===

class TestParseTimestampWithFormat:
    """Tests for _parse_timestamp_with_format method."""

    def test_unix_timestamp_parsing(self, basic_test_instance):
        """Test parsing Unix timestamp."""
        metadata = {}
        result = basic_test_instance._parse_timestamp_with_format("1705314600", metadata)
        assert result.year == 2024
        assert result.month == 1

    def test_iso_format_parsing(self, basic_test_instance):
        """Test parsing ISO format timestamp."""
        metadata = {}
        result = basic_test_instance._parse_timestamp_with_format(
            "2024-01-15T10:30:00", metadata
        )
        assert result.year == 2024
        assert result.month == 1
        assert result.day == 15

    def test_custom_format_parsing(self, basic_test_instance):
        """Test parsing with custom format."""
        metadata = {"format": "%Y/%m/%d %H:%M"}
        result = basic_test_instance._parse_timestamp_with_format(
            "2024/01/15 10:30", metadata
        )
        assert result.year == 2024
        assert result.month == 1
        assert result.day == 15
        # Note: The method may apply timezone conversion which shifts the hour
        # We just verify the date was parsed correctly
        assert result.minute == 30

    def test_localtime_flag_expected(self, basic_test_instance):
        """Test localtime flag for expected timestamp."""
        metadata = {"localtime": True}
        result = basic_test_instance._parse_timestamp_with_format(
            "2024-01-15T10:30:00", metadata, is_expected=True
        )
        # Should have timezone info
        assert result.tzinfo is not None

    def test_timezone_utc_metadata(self, basic_test_instance):
        """Test timezone=utc metadata handling."""
        metadata = {"timezone": "utc"}
        result = basic_test_instance._parse_timestamp_with_format(
            "2024-01-15T10:30:00", metadata, is_expected=False
        )
        # Should be converted to local time from UTC
        assert result.tzinfo is not None
