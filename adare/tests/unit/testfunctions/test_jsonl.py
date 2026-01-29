"""Unit tests for JSONL testfunctions."""

import pytest
import sys
import json
from pathlib import Path

# Add paths for imports
PROJECT_ROOT = Path(__file__).parent.parent.parent.parent
ADARELIB_ROOT = PROJECT_ROOT.parent / "adarelib"

# Add to sys.path if not already there
if str(ADARELIB_ROOT) not in sys.path:
    sys.path.insert(0, str(ADARELIB_ROOT))

# Import from adarelib.constants as required
from adarelib.constants import StatusEnum

# Import testfunctions dynamically
from adare.helperfunctions.module import import_module_from_pyfile

# Load JSONL testfunctions module
jsonl_module_path = PROJECT_ROOT / "appdata" / "testfunctions" / "jsonl" / "jsonl.py"
jsonl_module = import_module_from_pyfile(jsonl_module_path)

# Extract testfunctions from module
LineMatches = jsonl_module.LineMatches
LineMatchesParameter = jsonl_module.LineMatchesParameter
LineCount = jsonl_module.LineCount
LineCountParameter = jsonl_module.LineCountParameter
ValueInAnyLine = jsonl_module.ValueInAnyLine
ValueInAnyLineParameter = jsonl_module.ValueInAnyLineParameter

# Import test helpers
import importlib.util
helpers_path = Path(__file__).parent / "helpers.py"
spec = importlib.util.spec_from_file_location("helpers", helpers_path)
helpers = importlib.util.module_from_spec(spec)
spec.loader.exec_module(helpers)

assert_test_success = helpers.assert_test_success
assert_test_failed = helpers.assert_test_failed
assert_test_error = helpers.assert_test_error


# === Fixtures ===

@pytest.fixture
def create_jsonl_file(tmp_path):
    """Factory to create JSONL files (one JSON object per line)."""
    def _create(filename, lines_data):
        """
        Create a JSONL file.

        Args:
            filename: Name of file to create
            lines_data: List of dicts/objects to write as JSON lines
        """
        filepath = tmp_path / filename
        with open(filepath, 'w') as f:
            for data in lines_data:
                if isinstance(data, str):
                    # Allow raw string lines (for malformed JSON tests)
                    f.write(data + '\n')
                else:
                    # Write dict as JSON line
                    f.write(json.dumps(data) + '\n')
        return filepath
    return _create


# ============================================================================
# LineMatches Tests
# ============================================================================

class TestLineMatches:
    """Tests for LineMatches testfunction."""

    def test_line_matches_any_mode_success(self, create_jsonl_file):
        """Test successful match in 'any' mode."""
        jsonl_file = create_jsonl_file("test.jsonl", [
            {"name": "Alice", "age": 30, "city": "New York"},
            {"name": "Bob", "age": 25, "city": "London"},
            {"name": "Charlie", "age": 35, "city": "Paris"}
        ])

        test = LineMatches(
            name="test_any",
            parameter=LineMatchesParameter(
                dst=str(jsonl_file),
                conditions={"name": "Bob", "age": 25},
                match_mode="any"
            )
        )
        result = test.test()

        assert_test_success(result)
        assert "matching line(s)" in result.details[0]
        assert "mode: any" in result.details[0]

    def test_line_matches_any_mode_failure(self, create_jsonl_file):
        """Test failure in 'any' mode when no lines match."""
        jsonl_file = create_jsonl_file("test.jsonl", [
            {"name": "Alice", "age": 30},
            {"name": "Bob", "age": 25}
        ])

        test = LineMatches(
            name="test_any",
            parameter=LineMatchesParameter(
                dst=str(jsonl_file),
                conditions={"name": "Charlie", "age": 35},
                match_mode="any"
            )
        )
        result = test.test()

        assert_test_failed(result)
        assert "No lines matched" in result.details[0]

    def test_line_matches_all_mode_success(self, create_jsonl_file):
        """Test success in 'all' mode when all lines match."""
        jsonl_file = create_jsonl_file("test.jsonl", [
            {"status": "active", "verified": True},
            {"status": "active", "verified": True},
            {"status": "active", "verified": True}
        ])

        test = LineMatches(
            name="test_all",
            parameter=LineMatchesParameter(
                dst=str(jsonl_file),
                conditions={"status": "active", "verified": True},
                match_mode="all"
            )
        )
        result = test.test()

        assert_test_success(result)
        assert "All 3 lines matched" in result.details[0]
        assert "mode: all" in result.details[0]

    def test_line_matches_all_mode_failure(self, create_jsonl_file):
        """Test failure in 'all' mode when some lines don't match."""
        jsonl_file = create_jsonl_file("test.jsonl", [
            {"status": "active"},
            {"status": "inactive"},
            {"status": "active"}
        ])

        test = LineMatches(
            name="test_all",
            parameter=LineMatchesParameter(
                dst=str(jsonl_file),
                conditions={"status": "active"},
                match_mode="all"
            )
        )
        result = test.test()

        assert_test_failed(result)
        assert "Only 2/3 lines matched" in result.details[0]

    def test_line_matches_nested_value(self, create_jsonl_file):
        """Test matching nested values using dot notation."""
        jsonl_file = create_jsonl_file("test.jsonl", [
            {"user": {"name": "Alice", "profile": {"age": 30}}},
            {"user": {"name": "Bob", "profile": {"age": 25}}}
        ])

        test = LineMatches(
            name="test_nested",
            parameter=LineMatchesParameter(
                dst=str(jsonl_file),
                conditions={"user.profile.age": 30},
                match_mode="any"
            )
        )
        result = test.test()

        assert_test_success(result)

    def test_line_matches_wildcard_array(self, create_jsonl_file):
        """Test wildcard array access with [*] syntax."""
        jsonl_file = create_jsonl_file("test.jsonl", [
            {"users": [{"name": "Alice"}, {"name": "Bob"}]},
            {"users": [{"name": "Charlie"}, {"name": "David"}]}
        ])

        test = LineMatches(
            name="test_wildcard",
            parameter=LineMatchesParameter(
                dst=str(jsonl_file),
                conditions={"users[*].name": "Alice"},
                match_mode="any"
            )
        )
        result = test.test()

        assert_test_success(result)

    def test_line_matches_wildcard_object_keys(self, create_jsonl_file):
        """Test wildcard object keys with * syntax."""
        jsonl_file = create_jsonl_file("test.jsonl", [
            {"config": {"feature1": {"enabled": True}, "feature2": {"enabled": True}}},
            {"config": {"feature1": {"enabled": False}, "feature2": {"enabled": True}}}
        ])

        test = LineMatches(
            name="test_wildcard_keys",
            parameter=LineMatchesParameter(
                dst=str(jsonl_file),
                conditions={"config.*.enabled": True},
                match_mode="any"
            )
        )
        result = test.test()

        assert_test_success(result)

    def test_line_matches_regex_mode(self, create_jsonl_file):
        """Test regex matching with regex_match=True."""
        jsonl_file = create_jsonl_file("test.jsonl", [
            {"email": "alice@example.com"},
            {"email": "bob@test.org"},
            {"email": "invalid-email"}
        ])

        test = LineMatches(
            name="test_regex",
            parameter=LineMatchesParameter(
                dst=str(jsonl_file),
                conditions={"email": r".*@example\.com"},
                match_mode="any",
                regex_match=True
            )
        )
        result = test.test()

        assert_test_success(result)

    def test_line_matches_malformed_skip_true(self, create_jsonl_file):
        """Test skipping malformed JSON lines with skip_malformed=True."""
        jsonl_file = create_jsonl_file("test.jsonl", [
            {"name": "Alice"},
            "this is not valid JSON",
            {"name": "Bob"}
        ])

        test = LineMatches(
            name="test_malformed",
            parameter=LineMatchesParameter(
                dst=str(jsonl_file),
                conditions={"name": "Bob"},
                match_mode="any",
                skip_malformed=True
            )
        )
        result = test.test()

        assert_test_success(result)

    def test_line_matches_malformed_skip_false(self, create_jsonl_file):
        """Test failing on malformed JSON with skip_malformed=False."""
        jsonl_file = create_jsonl_file("test.jsonl", [
            {"name": "Alice"},
            "this is not valid JSON",
            {"name": "Bob"}
        ])

        test = LineMatches(
            name="test_malformed",
            parameter=LineMatchesParameter(
                dst=str(jsonl_file),
                conditions={"name": "Bob"},
                match_mode="any",
                skip_malformed=False
            )
        )
        result = test.test()

        assert_test_failed(result)
        assert "Malformed JSON" in result.details[0]

    def test_line_matches_empty_file(self, create_jsonl_file):
        """Test with empty JSONL file."""
        jsonl_file = create_jsonl_file("empty.jsonl", [])

        test = LineMatches(
            name="test_empty",
            parameter=LineMatchesParameter(
                dst=str(jsonl_file),
                conditions={"name": "Alice"},
                match_mode="any"
            )
        )
        result = test.test()

        assert_test_failed(result)
        assert "empty" in result.details[0]

    def test_line_matches_file_not_found(self, tmp_path):
        """Test with non-existent file."""
        test = LineMatches(
            name="test_not_found",
            parameter=LineMatchesParameter(
                dst=str(tmp_path / "nonexistent.jsonl"),
                conditions={"name": "Alice"},
                match_mode="any"
            )
        )
        result = test.test()

        assert_test_failed(result)
        assert "does not exist" in result.details[0]

    def test_line_matches_with_placeholder(self, create_jsonl_file, variable_metadata_simple):
        """Test matching with placeholder variables."""
        jsonl_file = create_jsonl_file("test.jsonl", [
            {"name": "Alice", "value": "value1"},
            {"name": "Bob", "value": "value2"}
        ])

        test = LineMatches(
            name="test_placeholder",
            parameter=LineMatchesParameter(
                dst=str(jsonl_file),
                conditions={"name": "Alice", "value": "{{VAR1}}"},
                match_mode="any"
            ),
            variable_metadata=variable_metadata_simple
        )
        result = test.test()

        assert_test_success(result)

    def test_line_matches_invalid_match_mode(self, create_jsonl_file):
        """Test with invalid match_mode value."""
        jsonl_file = create_jsonl_file("test.jsonl", [{"name": "Alice"}])

        test = LineMatches(
            name="test_invalid_mode",
            parameter=LineMatchesParameter(
                dst=str(jsonl_file),
                conditions={"name": "Alice"},
                match_mode="invalid"
            )
        )
        result = test.test()

        assert result.status == StatusEnum.ERROR
        assert "Invalid match_mode" in result.details[0]


# ============================================================================
# LineCount Tests
# ============================================================================

class TestLineCount:
    """Tests for LineCount testfunction."""

    def test_line_count_exact_match(self, create_jsonl_file):
        """Test exact count match."""
        jsonl_file = create_jsonl_file("test.jsonl", [
            {"status": "active"},
            {"status": "active"},
            {"status": "inactive"}
        ])

        test = LineCount(
            name="test_count",
            parameter=LineCountParameter(
                dst=str(jsonl_file),
                conditions={"status": "active"},
                expected_count=2
            )
        )
        result = test.test()

        assert_test_success(result)
        assert "Found 2 matching lines" in result.details[0]
        assert "expected exactly 2" in result.details[0]

    def test_line_count_exact_mismatch(self, create_jsonl_file):
        """Test failure when count doesn't match expected."""
        jsonl_file = create_jsonl_file("test.jsonl", [
            {"status": "active"},
            {"status": "active"},
            {"status": "active"}
        ])

        test = LineCount(
            name="test_count",
            parameter=LineCountParameter(
                dst=str(jsonl_file),
                conditions={"status": "active"},
                expected_count=2
            )
        )
        result = test.test()

        assert_test_failed(result)
        assert "Found 3 matching lines" in result.details[0]
        assert "Expected: 2" in result.details[1]

    def test_line_count_range_min_max(self, create_jsonl_file):
        """Test count with min/max range."""
        jsonl_file = create_jsonl_file("test.jsonl", [
            {"status": "active"},
            {"status": "active"},
            {"status": "active"}
        ])

        test = LineCount(
            name="test_count_range",
            parameter=LineCountParameter(
                dst=str(jsonl_file),
                conditions={"status": "active"},
                expected_count={"min": 2, "max": 5}
            )
        )
        result = test.test()

        assert_test_success(result)
        assert "Found 3 matching lines" in result.details[0]
        assert "expected 2-5" in result.details[0]

    def test_line_count_range_below_min(self, create_jsonl_file):
        """Test failure when count is below minimum."""
        jsonl_file = create_jsonl_file("test.jsonl", [
            {"status": "active"}
        ])

        test = LineCount(
            name="test_count_range",
            parameter=LineCountParameter(
                dst=str(jsonl_file),
                conditions={"status": "active"},
                expected_count={"min": 2, "max": 5}
            )
        )
        result = test.test()

        assert_test_failed(result)
        assert "Found 1 matching lines" in result.details[0]
        assert "Expected: 2-5" in result.details[1]

    def test_line_count_range_above_max(self, create_jsonl_file):
        """Test failure when count is above maximum."""
        jsonl_file = create_jsonl_file("test.jsonl", [
            {"status": "active"},
            {"status": "active"},
            {"status": "active"},
            {"status": "active"},
            {"status": "active"},
            {"status": "active"}
        ])

        test = LineCount(
            name="test_count_range",
            parameter=LineCountParameter(
                dst=str(jsonl_file),
                conditions={"status": "active"},
                expected_count={"min": 2, "max": 5}
            )
        )
        result = test.test()

        assert_test_failed(result)
        assert "Found 6 matching lines" in result.details[0]

    def test_line_count_no_conditions_all_lines(self, create_jsonl_file):
        """Test counting all lines when no conditions specified."""
        jsonl_file = create_jsonl_file("test.jsonl", [
            {"name": "Alice"},
            {"name": "Bob"},
            {"name": "Charlie"}
        ])

        test = LineCount(
            name="test_count_all",
            parameter=LineCountParameter(
                dst=str(jsonl_file),
                conditions=None,
                expected_count=3
            )
        )
        result = test.test()

        assert_test_success(result)
        assert "Found 3 matching lines" in result.details[0]

    def test_line_count_at_least_one_default(self, create_jsonl_file):
        """Test default behavior (expected_count=None means at least 1)."""
        jsonl_file = create_jsonl_file("test.jsonl", [
            {"status": "active"},
            {"status": "inactive"}
        ])

        test = LineCount(
            name="test_count_default",
            parameter=LineCountParameter(
                dst=str(jsonl_file),
                conditions={"status": "active"},
                expected_count=None
            )
        )
        result = test.test()

        assert_test_success(result)
        assert "Found 1 matching lines" in result.details[0]
        assert "expected at least 1" in result.details[0]

    def test_line_count_no_matching_lines(self, create_jsonl_file):
        """Test when no lines match conditions."""
        jsonl_file = create_jsonl_file("test.jsonl", [
            {"status": "inactive"},
            {"status": "inactive"}
        ])

        test = LineCount(
            name="test_no_match",
            parameter=LineCountParameter(
                dst=str(jsonl_file),
                conditions={"status": "active"},
                expected_count=None
            )
        )
        result = test.test()

        assert_test_failed(result)
        assert "Found 0 matching lines" in result.details[0]

    def test_line_count_with_nested_conditions(self, create_jsonl_file):
        """Test counting with nested conditions."""
        jsonl_file = create_jsonl_file("test.jsonl", [
            {"user": {"age": 30}},
            {"user": {"age": 25}},
            {"user": {"age": 30}}
        ])

        test = LineCount(
            name="test_nested",
            parameter=LineCountParameter(
                dst=str(jsonl_file),
                conditions={"user.age": 30},
                expected_count=2
            )
        )
        result = test.test()

        assert_test_success(result)

    def test_line_count_with_wildcards(self, create_jsonl_file):
        """Test counting with wildcard conditions."""
        jsonl_file = create_jsonl_file("test.jsonl", [
            {"items": [{"status": "done"}, {"status": "pending"}]},
            {"items": [{"status": "done"}, {"status": "done"}]},
            {"items": [{"status": "pending"}]}
        ])

        test = LineCount(
            name="test_wildcard",
            parameter=LineCountParameter(
                dst=str(jsonl_file),
                conditions={"items[*].status": "done"},
                expected_count=2
            )
        )
        result = test.test()

        assert_test_success(result)

    def test_line_count_skip_malformed(self, create_jsonl_file):
        """Test counting with malformed lines skipped."""
        jsonl_file = create_jsonl_file("test.jsonl", [
            {"status": "active"},
            "malformed json",
            {"status": "active"},
            "another bad line",
            {"status": "active"}
        ])

        test = LineCount(
            name="test_malformed",
            parameter=LineCountParameter(
                dst=str(jsonl_file),
                conditions={"status": "active"},
                expected_count=3,
                skip_malformed=True
            )
        )
        result = test.test()

        assert_test_success(result)

    def test_line_count_empty_file(self, create_jsonl_file):
        """Test with empty file."""
        jsonl_file = create_jsonl_file("empty.jsonl", [])

        test = LineCount(
            name="test_empty",
            parameter=LineCountParameter(
                dst=str(jsonl_file),
                conditions={"status": "active"},
                expected_count=0
            )
        )
        result = test.test()

        assert_test_failed(result)
        assert "empty" in result.details[0]


# ============================================================================
# ValueInAnyLine Tests
# ============================================================================

class TestValueInAnyLine:
    """Tests for ValueInAnyLine testfunction."""

    def test_value_in_any_line_found(self, create_jsonl_file):
        """Test successful value match in a line."""
        jsonl_file = create_jsonl_file("test.jsonl", [
            {"name": "Alice", "age": 30},
            {"name": "Bob", "age": 25},
            {"name": "Charlie", "age": 35}
        ])

        test = ValueInAnyLine(
            name="test_value",
            parameter=ValueInAnyLineParameter(
                dst=str(jsonl_file),
                key_path="name",
                expected_value="Bob"
            )
        )
        result = test.test()

        assert_test_success(result)
        assert "Found matching value in 1 line(s)" in result.details[0]
        assert 'line 2 with value "Bob"' in result.details[1]

    def test_value_in_any_line_not_found(self, create_jsonl_file):
        """Test failure when value not found."""
        jsonl_file = create_jsonl_file("test.jsonl", [
            {"name": "Alice", "age": 30},
            {"name": "Bob", "age": 25}
        ])

        test = ValueInAnyLine(
            name="test_value",
            parameter=ValueInAnyLineParameter(
                dst=str(jsonl_file),
                key_path="name",
                expected_value="Charlie"
            )
        )
        result = test.test()

        assert_test_failed(result)
        assert "No lines found" in result.details[0]
        assert "matching expected value" in result.details[0]

    def test_value_in_any_line_nested_path(self, create_jsonl_file):
        """Test with nested key path."""
        jsonl_file = create_jsonl_file("test.jsonl", [
            {"user": {"profile": {"email": "alice@test.com"}}},
            {"user": {"profile": {"email": "bob@test.com"}}}
        ])

        test = ValueInAnyLine(
            name="test_nested",
            parameter=ValueInAnyLineParameter(
                dst=str(jsonl_file),
                key_path="user.profile.email",
                expected_value="bob@test.com"
            )
        )
        result = test.test()

        assert_test_success(result)

    def test_value_in_any_line_wildcard_array(self, create_jsonl_file):
        """Test with wildcard array access."""
        jsonl_file = create_jsonl_file("test.jsonl", [
            {"tags": ["python", "java", "go"]},
            {"tags": ["rust", "cpp"]},
            {"tags": ["javascript", "python"]}
        ])

        test = ValueInAnyLine(
            name="test_wildcard",
            parameter=ValueInAnyLineParameter(
                dst=str(jsonl_file),
                key_path="tags[*]",
                expected_value="rust"
            )
        )
        result = test.test()

        assert_test_success(result)

    def test_value_in_any_line_wildcard_objects(self, create_jsonl_file):
        """Test with wildcard object key access."""
        jsonl_file = create_jsonl_file("test.jsonl", [
            {"config": {"db": {"host": "localhost"}, "cache": {"host": "redis"}}},
            {"config": {"db": {"host": "prod-db"}, "cache": {"host": "prod-cache"}}}
        ])

        test = ValueInAnyLine(
            name="test_wildcard_obj",
            parameter=ValueInAnyLineParameter(
                dst=str(jsonl_file),
                key_path="config.*.host",
                expected_value="localhost"
            )
        )
        result = test.test()

        assert_test_success(result)

    def test_value_in_any_line_regex_match(self, create_jsonl_file):
        """Test with regex matching."""
        jsonl_file = create_jsonl_file("test.jsonl", [
            {"id": "user-123"},
            {"id": "user-456"},
            {"id": "admin-789"}
        ])

        test = ValueInAnyLine(
            name="test_regex",
            parameter=ValueInAnyLineParameter(
                dst=str(jsonl_file),
                key_path="id",
                expected_value=r"admin-\d+",
                regex_match=True
            )
        )
        result = test.test()

        assert_test_success(result)

    def test_value_in_any_line_multiple_matches(self, create_jsonl_file):
        """Test when value appears in multiple lines."""
        jsonl_file = create_jsonl_file("test.jsonl", [
            {"status": "active"},
            {"status": "inactive"},
            {"status": "active"},
            {"status": "active"}
        ])

        test = ValueInAnyLine(
            name="test_multiple",
            parameter=ValueInAnyLineParameter(
                dst=str(jsonl_file),
                key_path="status",
                expected_value="active"
            )
        )
        result = test.test()

        assert_test_success(result)
        assert "Found matching value in 3 line(s)" in result.details[0]
        assert "Additional matches on lines" in result.details[2]

    def test_value_in_any_line_key_not_exists(self, create_jsonl_file):
        """Test when key path doesn't exist in any line."""
        jsonl_file = create_jsonl_file("test.jsonl", [
            {"name": "Alice"},
            {"name": "Bob"}
        ])

        test = ValueInAnyLine(
            name="test_no_key",
            parameter=ValueInAnyLineParameter(
                dst=str(jsonl_file),
                key_path="email",
                expected_value="test@example.com"
            )
        )
        result = test.test()

        assert_test_failed(result)
        assert 'Key path "email" not found in any line' in result.details[2]

    def test_value_in_any_line_with_placeholder(self, create_jsonl_file, variable_metadata_simple):
        """Test with placeholder variable."""
        jsonl_file = create_jsonl_file("test.jsonl", [
            {"name": "Alice", "value": "value1"},
            {"name": "Bob", "value": "value2"}
        ])

        test = ValueInAnyLine(
            name="test_placeholder",
            parameter=ValueInAnyLineParameter(
                dst=str(jsonl_file),
                key_path="name",
                expected_value="{{NAME_VAR}}"
            ),
            variable_metadata=variable_metadata_simple
        )
        result = test.test()

        assert_test_success(result)

    def test_value_in_any_line_skip_malformed(self, create_jsonl_file):
        """Test skipping malformed JSON lines."""
        jsonl_file = create_jsonl_file("test.jsonl", [
            {"name": "Alice"},
            "this is malformed",
            {"name": "Bob"},
            "another bad line"
        ])

        test = ValueInAnyLine(
            name="test_malformed",
            parameter=ValueInAnyLineParameter(
                dst=str(jsonl_file),
                key_path="name",
                expected_value="Bob",
                skip_malformed=True
            )
        )
        result = test.test()

        assert_test_success(result)

    def test_value_in_any_line_malformed_fail(self, create_jsonl_file):
        """Test failing on malformed JSON."""
        jsonl_file = create_jsonl_file("test.jsonl", [
            {"name": "Alice"},
            "malformed json"
        ])

        test = ValueInAnyLine(
            name="test_malformed",
            parameter=ValueInAnyLineParameter(
                dst=str(jsonl_file),
                key_path="name",
                expected_value="Alice",
                skip_malformed=False
            )
        )
        result = test.test()

        assert_test_failed(result)
        assert "Malformed JSON" in result.details[0]

    def test_value_in_any_line_empty_file(self, create_jsonl_file):
        """Test with empty file."""
        jsonl_file = create_jsonl_file("empty.jsonl", [])

        test = ValueInAnyLine(
            name="test_empty",
            parameter=ValueInAnyLineParameter(
                dst=str(jsonl_file),
                key_path="name",
                expected_value="Alice"
            )
        )
        result = test.test()

        assert_test_failed(result)
        assert "empty" in result.details[0]

    def test_value_in_any_line_file_not_found(self, tmp_path):
        """Test with non-existent file."""
        test = ValueInAnyLine(
            name="test_not_found",
            parameter=ValueInAnyLineParameter(
                dst=str(tmp_path / "nonexistent.jsonl"),
                key_path="name",
                expected_value="Alice"
            )
        )
        result = test.test()

        assert_test_failed(result)
        assert "does not exist" in result.details[0]

    def test_value_in_any_line_numeric_values(self, create_jsonl_file):
        """Test with numeric values."""
        jsonl_file = create_jsonl_file("test.jsonl", [
            {"count": 100},
            {"count": 200},
            {"count": 300}
        ])

        test = ValueInAnyLine(
            name="test_numeric",
            parameter=ValueInAnyLineParameter(
                dst=str(jsonl_file),
                key_path="count",
                expected_value=200
            )
        )
        result = test.test()

        assert_test_success(result)

    def test_value_in_any_line_boolean_values(self, create_jsonl_file):
        """Test with boolean values."""
        jsonl_file = create_jsonl_file("test.jsonl", [
            {"enabled": True},
            {"enabled": False},
            {"enabled": True}
        ])

        test = ValueInAnyLine(
            name="test_boolean",
            parameter=ValueInAnyLineParameter(
                dst=str(jsonl_file),
                key_path="enabled",
                expected_value=False
            )
        )
        result = test.test()

        assert_test_success(result)
