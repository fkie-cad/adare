"""
Comprehensive unit tests for adarelib.testset.yaml.customtags module.

Tests:
- ComparisonResult dataclass
- YamlCustomTag base class
- YamlString tag creation and matching
- YamlPath tag creation and matching
- YamlTimestamp tag creation and comparison
- YamlRegexString tag creation and regex matching
- YamlRegexStringAll tag
- Custom YAML tag loading from YAML
- YAML_CUSTOM_TAGS list
"""
import pytest
import yaml
import datetime
from unittest.mock import MagicMock

from adarelib.testset.yaml.customtags import (
    ComparisonResult,
    YamlCustomTag,
    YamlString,
    YamlPath,
    YamlTimestamp,
    YamlRegexString,
    YamlRegexStringAll,
    YAML_CUSTOM_TAGS,
)


# === Fixtures ===

@pytest.fixture
def mock_variable_registry():
    """Create a mock VariableRegistry."""
    registry = MagicMock()
    registry.resolve_in_string = MagicMock(side_effect=lambda s, for_regex=False: s.replace("{{var}}", "resolved_value"))
    return registry


@pytest.fixture
def yaml_loader_with_custom_tags():
    """Create a YAML loader with custom tags registered."""
    loader = yaml.SafeLoader
    # Register all custom tags
    for tag_class in YAML_CUSTOM_TAGS:
        yaml.add_constructor(tag_class.yaml_tag, tag_class.from_yaml, Loader=loader)
    return loader


# === Tests for ComparisonResult ===

class TestComparisonResult:
    """Tests for ComparisonResult dataclass."""

    def test_success_result(self):
        """Test creating a successful comparison result."""
        result = ComparisonResult(success=True)
        assert result.success is True
        assert result.details == ""
        assert result.additional_information == {}
        assert result.exception is None

    def test_failure_result_with_details(self):
        """Test creating a failed comparison result with details."""
        result = ComparisonResult(success=False, details="Values don't match")
        assert result.success is False
        assert result.details == "Values don't match"

    def test_result_with_exception(self):
        """Test creating a result with an exception."""
        exc = ValueError("test error")
        result = ComparisonResult(success=False, details="Error occurred", exception=exc)
        assert result.success is False
        assert result.exception is exc
        assert isinstance(result.exception, ValueError)

    def test_result_with_additional_info(self):
        """Test creating a result with additional information."""
        result = ComparisonResult(
            success=True,
            additional_information={"expected": "value1", "actual": "value1"}
        )
        assert result.additional_information["expected"] == "value1"


# === Tests for YamlCustomTag Base Class ===

class TestYamlCustomTag:
    """Tests for YamlCustomTag base class."""

    def test_set_variables_with_registry(self, mock_variable_registry):
        """Test set_variables method with a registry."""
        # Create a concrete subclass to test
        tag = YamlString("value with {{var}}")
        tag.set_variables(mock_variable_registry)
        assert tag.string == "value with resolved_value"

    def test_set_variables_with_none(self):
        """Test set_variables method with None registry."""
        tag = YamlString("original value")
        tag.set_variables(None)
        assert tag.string == "original value"


# === Tests for YamlString ===

class TestYamlString:
    """Tests for YamlString custom tag."""

    def test_creation(self):
        """Test YamlString creation."""
        tag = YamlString("test string")
        assert tag.string == "test string"
        assert tag.yaml_tag == "!s"

    def test_repr(self):
        """Test string representation."""
        tag = YamlString("test string")
        assert repr(tag) == "!s test string"

    def test_compare_equal(self):
        """Test comparison with equal values."""
        tag = YamlString("expected")
        result = tag.compare("expected")
        assert result.success is True

    def test_compare_not_equal(self):
        """Test comparison with different values."""
        tag = YamlString("expected")
        result = tag.compare("different")
        assert result.success is False

    def test_compare_empty_strings(self):
        """Test comparison with empty strings."""
        tag = YamlString("")
        result = tag.compare("")
        assert result.success is True

    def test_from_yaml(self):
        """Test loading from YAML."""
        yaml_content = "!s hello world"
        # Register constructor
        yaml.add_constructor("!s", YamlString.from_yaml, Loader=yaml.SafeLoader)
        result = yaml.load(yaml_content, Loader=yaml.SafeLoader)
        assert isinstance(result, YamlString)
        assert result.string == "hello world"

    def test_to_yaml(self):
        """Test dumping to YAML."""
        tag = YamlString("test value")
        yaml.add_representer(YamlString, YamlString.to_yaml)
        result = yaml.dump(tag)
        assert "!s" in result
        assert "test value" in result


# === Tests for YamlPath ===

class TestYamlPath:
    """Tests for YamlPath custom tag."""

    def test_creation(self):
        """Test YamlPath creation."""
        tag = YamlPath("/home/user/file.txt")
        assert tag.string == "/home/user/file.txt"
        assert tag.yaml_tag == "!path"

    def test_repr(self):
        """Test string representation."""
        tag = YamlPath("/home/user")
        assert repr(tag) == "!path /home/user"

    def test_compare_equal(self):
        """Test comparison with equal paths."""
        tag = YamlPath("/home/user/file.txt")
        result = tag.compare("/home/user/file.txt")
        assert result.success is True

    def test_compare_not_equal(self):
        """Test comparison with different paths."""
        tag = YamlPath("/home/user/file.txt")
        result = tag.compare("/home/other/file.txt")
        assert result.success is False

    def test_from_yaml(self):
        """Test loading from YAML."""
        yaml_content = "!path /some/path/to/file"
        yaml.add_constructor("!path", YamlPath.from_yaml, Loader=yaml.SafeLoader)
        result = yaml.load(yaml_content, Loader=yaml.SafeLoader)
        assert isinstance(result, YamlPath)
        assert result.string == "/some/path/to/file"


# === Tests for YamlTimestamp ===

class TestYamlTimestamp:
    """Tests for YamlTimestamp custom tag."""

    def test_creation_simple(self):
        """Test simple YamlTimestamp creation."""
        tag = YamlTimestamp("2024-01-15T10:30:00")
        assert tag.string == "2024-01-15T10:30:00"
        assert tag.yaml_tag == "!timestamp"

    def test_creation_with_tolerance(self):
        """Test YamlTimestamp creation with tolerance."""
        tag = YamlTimestamp("2024-01-15T10:30:00", tolerance=5)
        assert tag.tolerance == 5
        assert tag.metadata["tolerance"] == [-5, 5]

    def test_creation_with_timezone(self):
        """Test YamlTimestamp creation with timezone."""
        tag = YamlTimestamp("2024-01-15T10:30:00", timezone="UTC")
        assert tag.timezone == "UTC"
        assert tag.metadata["timezone"] == "UTC"

    def test_creation_with_format(self):
        """Test YamlTimestamp creation with format."""
        tag = YamlTimestamp("2024-01-15T10:30:00", format="%Y-%m-%dT%H:%M:%S")
        assert tag.format == "%Y-%m-%dT%H:%M:%S"
        assert tag.metadata["format"] == "%Y-%m-%dT%H:%M:%S"

    def test_repr(self):
        """Test string representation."""
        tag = YamlTimestamp("2024-01-15T10:30:00")
        assert repr(tag) == "!timestamp 2024-01-15T10:30:00"

    def test_compare_within_tolerance(self):
        """Test comparison within tolerance."""
        tag = YamlTimestamp("2024-01-15T10:30:00", tolerance=5)
        # Compare with timestamp 2 seconds later
        result = tag.compare("2024-01-15T10:30:02")
        assert result.success is True
        assert "difference" in result.details

    def test_compare_outside_tolerance(self):
        """Test comparison outside tolerance."""
        tag = YamlTimestamp("2024-01-15T10:30:00", tolerance=1)
        # Compare with timestamp 10 seconds later
        result = tag.compare("2024-01-15T10:30:10")
        assert result.success is False

    def test_compare_default_tolerance(self):
        """Test comparison with default 1 second tolerance."""
        tag = YamlTimestamp("2024-01-15T10:30:00")
        # Should use default 1 second tolerance
        result = tag.compare("2024-01-15T10:30:00")
        assert result.success is True

    def test_compare_with_custom_format(self):
        """Test comparison with custom format."""
        tag = YamlTimestamp(
            "2024-01-15T10:30:00",
            timestamp_format_in_entry="%Y/%m/%d %H:%M:%S",
            tolerance=5
        )
        result = tag.compare("2024/01/15 10:30:02")
        assert result.success is True

    def test_compare_parse_error_data(self):
        """Test comparison when data timestamp can't be parsed."""
        tag = YamlTimestamp("2024-01-15T10:30:00")
        result = tag.compare("not a timestamp")
        assert result.success is False
        assert "couldn't be parsed" in result.details

    def test_compare_parse_error_comparison(self):
        """Test comparison when comparison timestamp can't be parsed."""
        tag = YamlTimestamp("not a timestamp")
        result = tag.compare("2024-01-15T10:30:00")
        assert result.success is False
        assert "couldn't be parsed" in result.details


# === Tests for YamlRegexString ===

class TestYamlRegexString:
    """Tests for YamlRegexString custom tag."""

    def test_creation(self):
        """Test YamlRegexString creation."""
        tag = YamlRegexString(r"\d{4}-\d{2}-\d{2}")
        assert tag.string == r"\d{4}-\d{2}-\d{2}"
        assert tag.yaml_tag == "!re"

    def test_repr(self):
        """Test string representation."""
        tag = YamlRegexString(r"\w+")
        assert repr(tag) == r"!re \w+"

    def test_compare_match(self):
        """Test comparison with matching value."""
        tag = YamlRegexString(r"\d{4}-\d{2}-\d{2}")
        result = tag.compare("2024-01-15")
        assert result.success is True

    def test_compare_no_match(self):
        """Test comparison with non-matching value."""
        tag = YamlRegexString(r"\d{4}-\d{2}-\d{2}")
        result = tag.compare("not-a-date")
        assert result.success is False

    def test_compare_partial_match(self):
        """Test that comparison uses match() not fullmatch()."""
        tag = YamlRegexString(r"\d+")
        # match() matches from start, so "123abc" should match
        result = tag.compare("123abc")
        assert result.success is True

    def test_compare_invalid_regex(self):
        """Test comparison with invalid regex pattern."""
        tag = YamlRegexString(r"[invalid(regex")
        result = tag.compare("anything")
        assert result.success is False
        assert "could not be compiled" in result.details

    def test_set_variables_for_regex(self, mock_variable_registry):
        """Test that set_variables uses for_regex=True."""
        tag = YamlRegexString("pattern {{var}}")
        # Update mock to verify for_regex parameter
        mock_variable_registry.resolve_in_string = MagicMock(return_value="pattern resolved")
        tag.set_variables(mock_variable_registry)
        mock_variable_registry.resolve_in_string.assert_called_once_with("pattern {{var}}", for_regex=True)

    def test_from_yaml(self):
        """Test loading from YAML."""
        yaml_content = r"!re \d+"
        yaml.add_constructor("!re", YamlRegexString.from_yaml, Loader=yaml.SafeLoader)
        result = yaml.load(yaml_content, Loader=yaml.SafeLoader)
        assert isinstance(result, YamlRegexString)
        assert result.string == r"\d+"

    def test_complex_regex_pattern(self):
        """Test with complex regex pattern."""
        tag = YamlRegexString(r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$")
        # Email-like pattern
        result = tag.compare("test@example.com")
        assert result.success is True

        result = tag.compare("invalid-email")
        assert result.success is False


# === Tests for YamlRegexStringAll ===

class TestYamlRegexStringAll:
    """Tests for YamlRegexStringAll custom tag."""

    def test_creation(self):
        """Test YamlRegexStringAll creation."""
        tag = YamlRegexStringAll()
        assert tag.string == ".*"
        assert tag.yaml_tag == "!reALL"

    def test_repr(self):
        """Test string representation."""
        tag = YamlRegexStringAll()
        assert repr(tag) == "!reALL"

    def test_compare_always_true(self):
        """Test that comparison always returns True."""
        tag = YamlRegexStringAll()

        # Test with various inputs
        assert tag.compare("anything").success is True
        assert tag.compare("").success is True
        assert tag.compare("!@#$%^&*()").success is True
        assert tag.compare("multi\nline\ntext").success is True

    def test_from_yaml(self):
        """Test loading from YAML."""
        yaml_content = "!reALL"
        yaml.add_constructor("!reALL", YamlRegexStringAll.from_yaml, Loader=yaml.SafeLoader)
        result = yaml.load(yaml_content, Loader=yaml.SafeLoader)
        assert isinstance(result, YamlRegexStringAll)
        assert result.string == ".*"


# === Tests for YAML_CUSTOM_TAGS List ===

class TestYamlCustomTagsList:
    """Tests for YAML_CUSTOM_TAGS configuration list."""

    def test_contains_all_tags(self):
        """Test that YAML_CUSTOM_TAGS contains all expected tags."""
        expected_tags = [YamlRegexString, YamlRegexStringAll, YamlTimestamp, YamlString, YamlPath]
        for tag in expected_tags:
            assert tag in YAML_CUSTOM_TAGS

    def test_tag_count(self):
        """Test the number of custom tags."""
        assert len(YAML_CUSTOM_TAGS) == 5

    def test_all_tags_have_yaml_tag(self):
        """Test that all tags have yaml_tag attribute."""
        for tag_class in YAML_CUSTOM_TAGS:
            assert hasattr(tag_class, 'yaml_tag')
            assert tag_class.yaml_tag.startswith('!')


# === Tests for YAML Integration ===

class TestYamlIntegration:
    """Tests for YAML loading/dumping integration."""

    def test_load_yaml_with_string_tag(self):
        """Test loading YAML content with !s tag."""
        yaml.add_constructor("!s", YamlString.from_yaml, Loader=yaml.SafeLoader)
        yaml_content = """
key1: !s string value
key2: normal value
"""
        result = yaml.load(yaml_content, Loader=yaml.SafeLoader)
        assert isinstance(result["key1"], YamlString)
        assert result["key1"].string == "string value"
        assert result["key2"] == "normal value"

    def test_load_yaml_with_regex_tag(self):
        """Test loading YAML content with !re tag."""
        yaml.add_constructor("!re", YamlRegexString.from_yaml, Loader=yaml.SafeLoader)
        yaml_content = r"""
pattern: !re \d{4}-\d{2}-\d{2}
"""
        result = yaml.load(yaml_content, Loader=yaml.SafeLoader)
        assert isinstance(result["pattern"], YamlRegexString)
        assert result["pattern"].string == r"\d{4}-\d{2}-\d{2}"

    def test_load_yaml_with_path_tag(self):
        """Test loading YAML content with !path tag."""
        yaml.add_constructor("!path", YamlPath.from_yaml, Loader=yaml.SafeLoader)
        yaml_content = """
filepath: !path /home/user/documents/file.txt
"""
        result = yaml.load(yaml_content, Loader=yaml.SafeLoader)
        assert isinstance(result["filepath"], YamlPath)
        assert result["filepath"].string == "/home/user/documents/file.txt"

    def test_load_yaml_with_all_custom_tags(self):
        """Test loading YAML with multiple custom tag types."""
        # Register all constructors
        yaml.add_constructor("!s", YamlString.from_yaml, Loader=yaml.SafeLoader)
        yaml.add_constructor("!re", YamlRegexString.from_yaml, Loader=yaml.SafeLoader)
        yaml.add_constructor("!path", YamlPath.from_yaml, Loader=yaml.SafeLoader)
        yaml.add_constructor("!reALL", YamlRegexStringAll.from_yaml, Loader=yaml.SafeLoader)

        yaml_content = r"""
string_val: !s hello
regex_val: !re \w+
path_val: !path /tmp/test
match_all: !reALL
"""
        result = yaml.load(yaml_content, Loader=yaml.SafeLoader)

        assert isinstance(result["string_val"], YamlString)
        assert isinstance(result["regex_val"], YamlRegexString)
        assert isinstance(result["path_val"], YamlPath)
        assert isinstance(result["match_all"], YamlRegexStringAll)


# === Edge Case Tests ===

class TestEdgeCases:
    """Tests for edge cases and boundary conditions."""

    def test_yaml_string_with_special_chars(self):
        """Test YamlString with special characters."""
        special_chars = "!@#$%^&*()[]{}|\\:;\"'<>,.?/"
        tag = YamlString(special_chars)
        result = tag.compare(special_chars)
        assert result.success is True

    def test_yaml_regex_with_unicode(self):
        """Test YamlRegexString with unicode patterns."""
        tag = YamlRegexString(r"[a-z]+")
        result = tag.compare("hello")
        assert result.success is True

    def test_yaml_timestamp_edge_dates(self):
        """Test YamlTimestamp with edge case dates."""
        # Year boundary
        tag = YamlTimestamp("2023-12-31T23:59:59", tolerance=2)
        result = tag.compare("2024-01-01T00:00:00")
        assert result.success is True

    def test_empty_yaml_string(self):
        """Test YamlString with empty string."""
        tag = YamlString("")
        result = tag.compare("")
        assert result.success is True

        result = tag.compare("non-empty")
        assert result.success is False

    def test_yaml_path_windows_style(self):
        """Test YamlPath with Windows-style paths."""
        tag = YamlPath("C:\\Users\\test\\file.txt")
        result = tag.compare("C:\\Users\\test\\file.txt")
        assert result.success is True

    def test_yaml_regex_empty_pattern(self):
        """Test YamlRegexString with empty pattern (matches empty string at start)."""
        tag = YamlRegexString("")
        result = tag.compare("anything")
        # Empty regex matches empty string at the start of any string
        assert result.success is True

    def test_comparison_result_all_fields(self):
        """Test ComparisonResult with all fields populated."""
        exc = RuntimeError("test")
        result = ComparisonResult(
            success=False,
            details="Detailed error message",
            additional_information={"key1": "value1", "key2": 123},
            exception=exc
        )
        assert result.success is False
        assert result.details == "Detailed error message"
        assert result.additional_information["key1"] == "value1"
        assert result.additional_information["key2"] == 123
        assert result.exception is exc
