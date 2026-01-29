"""Comprehensive unit tests for JSON testfunctions."""

import pytest
import sys
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

# Load JSON testfunctions module
json_module_path = PROJECT_ROOT / "appdata" / "testfunctions" / "json" / "json.py"
json_module = import_module_from_pyfile(json_module_path)

# Extract testfunctions from module
ContainsKey = json_module.ContainsKey
ContainsKeyParameter = json_module.ContainsKeyParameter
ValueMatches = json_module.ValueMatches
ValueMatchesParameter = json_module.ValueMatchesParameter
ArrayContains = json_module.ArrayContains
ArrayContainsParameter = json_module.ArrayContainsParameter

# Import test helpers
import importlib.util
helpers_path = Path(__file__).parent / "helpers.py"
spec = importlib.util.spec_from_file_location("helpers", helpers_path)
helpers = importlib.util.module_from_spec(spec)
spec.loader.exec_module(helpers)

assert_test_success = helpers.assert_test_success
assert_test_failed = helpers.assert_test_failed
assert_test_error = helpers.assert_test_error


# ============================================================================
# ContainsKey Tests
# ============================================================================

class TestContainsKey:
    """Tests for ContainsKey testfunction."""

    def test_contains_key_success_simple(self, create_json_file):
        """Test successful key existence check with simple key."""
        json_file = create_json_file("test.json", {
            "name": "Alice",
            "age": 30,
            "city": "New York"
        })

        test = ContainsKey(
            name="test_contains_key",
            parameter=ContainsKeyParameter(
                dst=str(json_file),
                key_path="name"
            )
        )
        result = test.test()

        assert_test_success(result)
        assert "name" in result.details[0]
        assert "Alice" in result.details[0]

    def test_contains_key_success_nested(self, create_json_file):
        """Test successful nested key existence check with dot notation."""
        json_file = create_json_file("test.json", {
            "user": {
                "profile": {
                    "name": "Alice",
                    "age": 30
                }
            }
        })

        test = ContainsKey(
            name="test_contains_key",
            parameter=ContainsKeyParameter(
                dst=str(json_file),
                key_path="user.profile.name"
            )
        )
        result = test.test()

        assert_test_success(result)
        assert "user.profile.name" in result.details[0]
        assert "Alice" in result.details[0]

    def test_contains_key_success_deeply_nested(self, create_json_file):
        """Test successful deeply nested key path."""
        json_file = create_json_file("test.json", {
            "level1": {
                "level2": {
                    "level3": {
                        "level4": "deep_value"
                    }
                }
            }
        })

        test = ContainsKey(
            name="test_contains_key",
            parameter=ContainsKeyParameter(
                dst=str(json_file),
                key_path="level1.level2.level3.level4"
            )
        )
        result = test.test()

        assert_test_success(result)
        assert "deep_value" in result.details[0]

    def test_contains_key_failure_missing_key(self, create_json_file):
        """Test failure when key doesn't exist."""
        json_file = create_json_file("test.json", {
            "name": "Alice",
            "age": 30
        })

        test = ContainsKey(
            name="test_contains_key",
            parameter=ContainsKeyParameter(
                dst=str(json_file),
                key_path="city"
            )
        )
        result = test.test()

        assert_test_failed(result)
        assert "does not exist" in result.details[0]

    def test_contains_key_failure_missing_nested_key(self, create_json_file):
        """Test failure when nested key path doesn't exist."""
        json_file = create_json_file("test.json", {
            "user": {
                "profile": {
                    "name": "Alice"
                }
            }
        })

        test = ContainsKey(
            name="test_contains_key",
            parameter=ContainsKeyParameter(
                dst=str(json_file),
                key_path="user.profile.age"
            )
        )
        result = test.test()

        assert_test_failed(result)
        assert "does not exist" in result.details[0]

    def test_contains_key_failure_malformed_json(self, tmp_path):
        """Test failure with malformed JSON file."""
        json_file = tmp_path / "malformed.json"
        json_file.write_text("{invalid json content")

        test = ContainsKey(
            name="test_contains_key",
            parameter=ContainsKeyParameter(
                dst=str(json_file),
                key_path="name"
            )
        )
        result = test.test()

        assert_test_failed(result)
        assert "Invalid JSON" in result.details[0]

    def test_contains_key_failure_file_not_found(self, tmp_path):
        """Test failure when JSON file doesn't exist."""
        test = ContainsKey(
            name="test_contains_key",
            parameter=ContainsKeyParameter(
                dst=str(tmp_path / "nonexistent.json"),
                key_path="name"
            )
        )
        result = test.test()

        assert_test_failed(result)
        assert "not found" in result.details[0]

    def test_contains_key_success_with_null_value(self, create_json_file):
        """Test successful key check when value is null."""
        json_file = create_json_file("test.json", {
            "name": "Alice",
            "email": None
        })

        test = ContainsKey(
            name="test_contains_key",
            parameter=ContainsKeyParameter(
                dst=str(json_file),
                key_path="email"
            )
        )
        result = test.test()

        assert_test_success(result)
        assert "None" in result.details[0]


# ============================================================================
# ValueMatches Tests
# ============================================================================

class TestValueMatches:
    """Tests for ValueMatches testfunction."""

    def test_value_matches_success_string(self, create_json_file):
        """Test successful direct string value comparison."""
        json_file = create_json_file("test.json", {
            "name": "Alice",
            "age": 30
        })

        test = ValueMatches(
            name="test_value_matches",
            parameter=ValueMatchesParameter(
                dst=str(json_file),
                key_path="name",
                expected_value="Alice"
            )
        )
        result = test.test()

        assert_test_success(result)
        assert "Alice" in result.details[0]

    def test_value_matches_success_number(self, create_json_file):
        """Test successful numeric value comparison."""
        json_file = create_json_file("test.json", {
            "age": 30,
            "score": 95.5
        })

        test = ValueMatches(
            name="test_value_matches",
            parameter=ValueMatchesParameter(
                dst=str(json_file),
                key_path="age",
                expected_value=30
            )
        )
        result = test.test()

        assert_test_success(result)

    def test_value_matches_success_float(self, create_json_file):
        """Test successful float value comparison."""
        json_file = create_json_file("test.json", {
            "score": 95.5
        })

        test = ValueMatches(
            name="test_value_matches",
            parameter=ValueMatchesParameter(
                dst=str(json_file),
                key_path="score",
                expected_value=95.5
            )
        )
        result = test.test()

        assert_test_success(result)

    def test_value_matches_success_boolean_true(self, create_json_file):
        """Test successful boolean True value comparison."""
        json_file = create_json_file("test.json", {
            "active": True,
            "verified": False
        })

        test = ValueMatches(
            name="test_value_matches",
            parameter=ValueMatchesParameter(
                dst=str(json_file),
                key_path="active",
                expected_value=True
            )
        )
        result = test.test()

        assert_test_success(result)

    def test_value_matches_success_boolean_false(self, create_json_file):
        """Test successful boolean False value comparison."""
        json_file = create_json_file("test.json", {
            "active": False
        })

        test = ValueMatches(
            name="test_value_matches",
            parameter=ValueMatchesParameter(
                dst=str(json_file),
                key_path="active",
                expected_value=False
            )
        )
        result = test.test()

        assert_test_success(result)

    def test_value_matches_success_nested(self, create_json_file):
        """Test successful nested value comparison."""
        json_file = create_json_file("test.json", {
            "user": {
                "profile": {
                    "name": "Alice",
                    "age": 30
                }
            }
        })

        test = ValueMatches(
            name="test_value_matches",
            parameter=ValueMatchesParameter(
                dst=str(json_file),
                key_path="user.profile.name",
                expected_value="Alice"
            )
        )
        result = test.test()

        assert_test_success(result)

    def test_value_matches_success_regex_match(self, create_json_file):
        """Test successful regex matching with regex_match=True."""
        json_file = create_json_file("test.json", {
            "email": "alice@example.com",
            "phone": "123-4567"
        })

        test = ValueMatches(
            name="test_value_matches",
            parameter=ValueMatchesParameter(
                dst=str(json_file),
                key_path="email",
                expected_value=r".*@example\.com",
                regex_match=True
            )
        )
        result = test.test()

        assert_test_success(result)
        assert "matches regex" in result.details[0]

    def test_value_matches_failure_regex_no_match(self, create_json_file):
        """Test failure when regex doesn't match."""
        json_file = create_json_file("test.json", {
            "email": "alice@test.com"
        })

        test = ValueMatches(
            name="test_value_matches",
            parameter=ValueMatchesParameter(
                dst=str(json_file),
                key_path="email",
                expected_value=r".*@example\.com",
                regex_match=True
            )
        )
        result = test.test()

        assert_test_failed(result)
        assert "does not match regex" in result.details[0]

    def test_value_matches_success_wildcard_array_any_mode(self, create_json_file):
        """Test successful wildcard array matching with any mode."""
        json_file = create_json_file("test.json", {
            "users": [
                {"name": "Alice", "age": 30},
                {"name": "Bob", "age": 25},
                {"name": "Charlie", "age": 35}
            ]
        })

        test = ValueMatches(
            name="test_value_matches",
            parameter=ValueMatchesParameter(
                dst=str(json_file),
                key_path="users[*].age",
                expected_value=30,
                wildcard_mode="any"
            )
        )
        result = test.test()

        assert_test_success(result)
        assert "matched" in result.details[0]
        assert "mode: any" in result.details[0]

    def test_value_matches_success_wildcard_array_all_mode(self, create_json_file):
        """Test successful wildcard array matching with all mode."""
        json_file = create_json_file("test.json", {
            "items": [
                {"status": "active"},
                {"status": "active"},
                {"status": "active"}
            ]
        })

        test = ValueMatches(
            name="test_value_matches",
            parameter=ValueMatchesParameter(
                dst=str(json_file),
                key_path="items[*].status",
                expected_value="active",
                wildcard_mode="all"
            )
        )
        result = test.test()

        assert_test_success(result)
        assert "matched all" in result.details[0]
        assert "mode: all" in result.details[0]

    def test_value_matches_failure_wildcard_array_all_mode(self, create_json_file):
        """Test failure when not all array elements match in all mode."""
        json_file = create_json_file("test.json", {
            "items": [
                {"status": "active"},
                {"status": "inactive"},
                {"status": "active"}
            ]
        })

        test = ValueMatches(
            name="test_value_matches",
            parameter=ValueMatchesParameter(
                dst=str(json_file),
                key_path="items[*].status",
                expected_value="active",
                wildcard_mode="all"
            )
        )
        result = test.test()

        assert_test_failed(result)
        assert "mode: all" in result.details[0]
        assert "matched 2/3" in result.details[0]

    def test_value_matches_success_wildcard_object_keys(self, create_json_file):
        """Test successful wildcard matching for all object keys."""
        json_file = create_json_file("test.json", {
            "config": {
                "feature_a": {"enabled": True},
                "feature_b": {"enabled": True},
                "feature_c": {"enabled": True}
            }
        })

        test = ValueMatches(
            name="test_value_matches",
            parameter=ValueMatchesParameter(
                dst=str(json_file),
                key_path="config.*.enabled",
                expected_value=True,
                wildcard_mode="all"
            )
        )
        result = test.test()

        assert_test_success(result)
        assert "mode: all" in result.details[0]

    def test_value_matches_failure_wildcard_no_match_any_mode(self, create_json_file):
        """Test failure when wildcard matches no values in any mode."""
        json_file = create_json_file("test.json", {
            "users": [
                {"name": "Alice", "age": 30},
                {"name": "Bob", "age": 25}
            ]
        })

        test = ValueMatches(
            name="test_value_matches",
            parameter=ValueMatchesParameter(
                dst=str(json_file),
                key_path="users[*].age",
                expected_value=40,
                wildcard_mode="any"
            )
        )
        result = test.test()

        assert_test_failed(result)
        assert "matched 0/" in result.details[0]

    def test_value_matches_success_wildcard_object_any_mode(self, create_json_file):
        """Test successful wildcard object matching with any mode."""
        json_file = create_json_file("test.json", {
            "config": {
                "feature_a": {"enabled": False},
                "feature_b": {"enabled": True},
                "feature_c": {"enabled": False}
            }
        })

        test = ValueMatches(
            name="test_value_matches",
            parameter=ValueMatchesParameter(
                dst=str(json_file),
                key_path="config.*.enabled",
                expected_value=True,
                wildcard_mode="any"
            )
        )
        result = test.test()

        assert_test_success(result)
        assert "mode: any" in result.details[0]

    def test_value_matches_with_placeholder_simple(self, create_json_file, variable_metadata_simple):
        """Test value matching with simple placeholder."""
        json_file = create_json_file("test.json", {
            "result": "value1",
            "output": "value2"
        })

        test = ValueMatches(
            name="test_value_matches",
            parameter=ValueMatchesParameter(
                dst=str(json_file),
                key_path="result",
                expected_value="{{VAR1}}"
            ),
            variable_metadata=variable_metadata_simple
        )
        result = test.test()

        assert_test_success(result)

    def test_value_matches_failure_placeholder_mismatch(self, create_json_file, variable_metadata_simple):
        """Test failure when placeholder value doesn't match."""
        json_file = create_json_file("test.json", {
            "result": "wrong_value"
        })

        test = ValueMatches(
            name="test_value_matches",
            parameter=ValueMatchesParameter(
                dst=str(json_file),
                key_path="result",
                expected_value="{{VAR1}}"
            ),
            variable_metadata=variable_metadata_simple
        )
        result = test.test()

        assert_test_failed(result)

    def test_value_matches_failure_direct_comparison(self, create_json_file):
        """Test failure when direct value comparison doesn't match."""
        json_file = create_json_file("test.json", {
            "name": "Alice"
        })

        test = ValueMatches(
            name="test_value_matches",
            parameter=ValueMatchesParameter(
                dst=str(json_file),
                key_path="name",
                expected_value="Bob"
            )
        )
        result = test.test()

        assert_test_failed(result)
        assert "expected" in result.details[0]
        assert "Bob" in result.details[0]
        assert "Alice" in result.details[0]

    def test_value_matches_failure_key_not_found(self, create_json_file):
        """Test failure when key path doesn't exist."""
        json_file = create_json_file("test.json", {
            "name": "Alice"
        })

        test = ValueMatches(
            name="test_value_matches",
            parameter=ValueMatchesParameter(
                dst=str(json_file),
                key_path="age",
                expected_value=30
            )
        )
        result = test.test()

        assert_test_failed(result)
        assert "does not exist" in result.details[0]

    def test_value_matches_failure_malformed_json(self, tmp_path):
        """Test failure with malformed JSON file."""
        json_file = tmp_path / "malformed.json"
        json_file.write_text("{invalid: json}")

        test = ValueMatches(
            name="test_value_matches",
            parameter=ValueMatchesParameter(
                dst=str(json_file),
                key_path="name",
                expected_value="Alice"
            )
        )
        result = test.test()

        assert_test_failed(result)
        assert "Invalid JSON" in result.details[0]

    def test_value_matches_success_nested_wildcard(self, create_json_file):
        """Test successful nested wildcard path matching."""
        json_file = create_json_file("test.json", {
            "teams": [
                {"members": [{"role": "admin"}, {"role": "user"}]},
                {"members": [{"role": "admin"}, {"role": "admin"}]}
            ]
        })

        test = ValueMatches(
            name="test_value_matches",
            parameter=ValueMatchesParameter(
                dst=str(json_file),
                key_path="teams[*].members[*].role",
                expected_value="admin",
                wildcard_mode="any"
            )
        )
        result = test.test()

        assert_test_success(result)

    def test_value_matches_success_case_sensitive(self, create_json_file):
        """Test that value matching is case sensitive by default."""
        json_file = create_json_file("test.json", {
            "name": "Alice"
        })

        test = ValueMatches(
            name="test_value_matches",
            parameter=ValueMatchesParameter(
                dst=str(json_file),
                key_path="name",
                expected_value="alice"
            )
        )
        result = test.test()

        # Should fail due to case difference
        assert_test_failed(result)


# ============================================================================
# ArrayContains Tests
# ============================================================================

class TestArrayContains:
    """Tests for ArrayContains testfunction."""

    def test_array_contains_success_string(self, create_json_file):
        """Test successful string element membership."""
        json_file = create_json_file("test.json", {
            "names": ["Alice", "Bob", "Charlie"]
        })

        test = ArrayContains(
            name="test_array_contains",
            parameter=ArrayContainsParameter(
                dst=str(json_file),
                array_path="names",
                expected_element="Bob"
            )
        )
        result = test.test()

        assert_test_success(result)
        assert "contains expected element" in result.details[0]
        assert "Bob" in result.details[0]

    def test_array_contains_success_number(self, create_json_file):
        """Test successful numeric element membership."""
        json_file = create_json_file("test.json", {
            "scores": [85, 90, 95, 100]
        })

        test = ArrayContains(
            name="test_array_contains",
            parameter=ArrayContainsParameter(
                dst=str(json_file),
                array_path="scores",
                expected_element=95
            )
        )
        result = test.test()

        assert_test_success(result)

    def test_array_contains_success_boolean(self, create_json_file):
        """Test successful boolean element membership."""
        json_file = create_json_file("test.json", {
            "flags": [True, False, True]
        })

        test = ArrayContains(
            name="test_array_contains",
            parameter=ArrayContainsParameter(
                dst=str(json_file),
                array_path="flags",
                expected_element=False
            )
        )
        result = test.test()

        assert_test_success(result)

    def test_array_contains_success_nested_array(self, create_json_file):
        """Test successful nested array element membership."""
        json_file = create_json_file("test.json", {
            "data": {
                "results": {
                    "values": [10, 20, 30]
                }
            }
        })

        test = ArrayContains(
            name="test_array_contains",
            parameter=ArrayContainsParameter(
                dst=str(json_file),
                array_path="data.results.values",
                expected_element=20
            )
        )
        result = test.test()

        assert_test_success(result)

    def test_array_contains_success_complex_object(self, create_json_file):
        """Test successful complex object element membership."""
        json_file = create_json_file("test.json", {
            "users": [
                {"name": "Alice", "age": 30},
                {"name": "Bob", "age": 25}
            ]
        })

        test = ArrayContains(
            name="test_array_contains",
            parameter=ArrayContainsParameter(
                dst=str(json_file),
                array_path="users",
                expected_element={"name": "Alice", "age": 30}
            )
        )
        result = test.test()

        assert_test_success(result)

    def test_array_contains_success_nested_list(self, create_json_file):
        """Test successful nested list element membership."""
        json_file = create_json_file("test.json", {
            "matrix": [[1, 2], [3, 4], [5, 6]]
        })

        test = ArrayContains(
            name="test_array_contains",
            parameter=ArrayContainsParameter(
                dst=str(json_file),
                array_path="matrix",
                expected_element=[3, 4]
            )
        )
        result = test.test()

        assert_test_success(result)

    def test_array_contains_failure_element_not_found(self, create_json_file):
        """Test failure when element is not in array."""
        json_file = create_json_file("test.json", {
            "names": ["Alice", "Bob", "Charlie"]
        })

        test = ArrayContains(
            name="test_array_contains",
            parameter=ArrayContainsParameter(
                dst=str(json_file),
                array_path="names",
                expected_element="David"
            )
        )
        result = test.test()

        assert_test_failed(result)
        assert "does not contain" in result.details[0]

    def test_array_contains_failure_not_array(self, create_json_file):
        """Test failure when path points to non-array value."""
        json_file = create_json_file("test.json", {
            "name": "Alice"
        })

        test = ArrayContains(
            name="test_array_contains",
            parameter=ArrayContainsParameter(
                dst=str(json_file),
                array_path="name",
                expected_element="Alice"
            )
        )
        result = test.test()

        assert_test_failed(result)
        assert "not an array" in result.details[0]

    def test_array_contains_failure_array_path_not_found(self, create_json_file):
        """Test failure when array path doesn't exist."""
        json_file = create_json_file("test.json", {
            "names": ["Alice"]
        })

        test = ArrayContains(
            name="test_array_contains",
            parameter=ArrayContainsParameter(
                dst=str(json_file),
                array_path="values",
                expected_element="test"
            )
        )
        result = test.test()

        assert_test_failed(result)
        assert "does not exist" in result.details[0]

    def test_array_contains_with_placeholder_simple(self, create_json_file, variable_metadata_simple):
        """Test array contains with simple placeholder."""
        json_file = create_json_file("test.json", {
            "results": ["value1", "value2", "other"]
        })

        test = ArrayContains(
            name="test_array_contains",
            parameter=ArrayContainsParameter(
                dst=str(json_file),
                array_path="results",
                expected_element="{{VAR1}}"
            ),
            variable_metadata=variable_metadata_simple
        )
        result = test.test()

        assert_test_success(result)
        assert "matches placeholder" in result.details[0]

    def test_array_contains_failure_placeholder_mismatch(self, create_json_file, variable_metadata_simple):
        """Test failure when placeholder doesn't match any array element."""
        json_file = create_json_file("test.json", {
            "results": ["wrong1", "wrong2", "wrong3"]
        })

        test = ArrayContains(
            name="test_array_contains",
            parameter=ArrayContainsParameter(
                dst=str(json_file),
                array_path="results",
                expected_element="{{VAR1}}"
            ),
            variable_metadata=variable_metadata_simple
        )
        result = test.test()

        assert_test_failed(result)
        assert "no array element matches" in result.details[0]

    def test_array_contains_empty_array(self, create_json_file):
        """Test behavior with empty array."""
        json_file = create_json_file("test.json", {
            "items": []
        })

        test = ArrayContains(
            name="test_array_contains",
            parameter=ArrayContainsParameter(
                dst=str(json_file),
                array_path="items",
                expected_element="anything"
            )
        )
        result = test.test()

        assert_test_failed(result)
        assert "does not contain" in result.details[0]

    def test_array_contains_success_null_element(self, create_json_file):
        """Test successful null element membership."""
        json_file = create_json_file("test.json", {
            "values": ["a", None, "b"]
        })

        test = ArrayContains(
            name="test_array_contains",
            parameter=ArrayContainsParameter(
                dst=str(json_file),
                array_path="values",
                expected_element=None
            )
        )
        result = test.test()

        assert_test_success(result)

    def test_array_contains_failure_malformed_json(self, tmp_path):
        """Test failure with malformed JSON file."""
        json_file = tmp_path / "malformed.json"
        json_file.write_text("[invalid json")

        test = ArrayContains(
            name="test_array_contains",
            parameter=ArrayContainsParameter(
                dst=str(json_file),
                array_path="items",
                expected_element="test"
            )
        )
        result = test.test()

        assert_test_failed(result)
        assert "Invalid JSON" in result.details[0]

    def test_array_contains_failure_file_not_found(self, tmp_path):
        """Test failure when JSON file doesn't exist."""
        test = ArrayContains(
            name="test_array_contains",
            parameter=ArrayContainsParameter(
                dst=str(tmp_path / "nonexistent.json"),
                array_path="items",
                expected_element="test"
            )
        )
        result = test.test()

        assert_test_failed(result)
        assert "not found" in result.details[0]
