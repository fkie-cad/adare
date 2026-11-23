"""Comprehensive unit tests for JSON testfunctions."""

import json
import pytest
import sys
from pathlib import Path

pytestmark = pytest.mark.unit

# Add paths for imports
PROJECT_ROOT = Path(__file__).parent.parent.parent.parent
ADARELIB_ROOT = PROJECT_ROOT.parent / "adarelib"

# Add to sys.path if not already there
if str(ADARELIB_ROOT) not in sys.path:
    sys.path.insert(0, str(ADARELIB_ROOT))

# Import from adarelib.constants as required
from adarelib.constants import StatusEnum

# Import testfunctions dynamically
from adarelib.helper.module import import_module_from_pyfile

# Load JSON testfunctions module
json_module_path = PROJECT_ROOT / "appdata" / "testfunctions" / "json" / "json.py"
json_tf_module = import_module_from_pyfile(json_module_path)

# Extract testfunctions from module (decorator-based)
ContainsKey = json_tf_module.contains_key._test_class
ContainsKeyParameter = json_tf_module.contains_key._parameter_class
ValueMatches = json_tf_module.value_matches._test_class
ValueMatchesParameter = json_tf_module.value_matches._parameter_class
ArrayContains = json_tf_module.array_contains._test_class
ArrayContainsParameter = json_tf_module.array_contains._parameter_class
ValueCount = json_tf_module.value_count._test_class
ValueCountParameter = json_tf_module.value_count._parameter_class

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
        json_file = create_json_file("test.json", {"name": "Alice", "age": 30, "city": "New York"})

        test = ContainsKey(
            name="test_contains_key", parameter=ContainsKeyParameter(dst=str(json_file), key_path="name")
        )
        result = test.test()

        assert_test_success(result)
        assert "name" in result.details[0]
        assert "Alice" in result.details[0]

    def test_contains_key_success_nested(self, create_json_file):
        """Test successful nested key existence check with dot notation."""
        json_file = create_json_file("test.json", {"user": {"profile": {"name": "Alice", "age": 30}}})

        test = ContainsKey(
            name="test_contains_key", parameter=ContainsKeyParameter(dst=str(json_file), key_path="user.profile.name")
        )
        result = test.test()

        assert_test_success(result)
        assert "user.profile.name" in result.details[0]
        assert "Alice" in result.details[0]

    def test_contains_key_success_deeply_nested(self, create_json_file):
        """Test successful deeply nested key path."""
        json_file = create_json_file("test.json", {"level1": {"level2": {"level3": {"level4": "deep_value"}}}})

        test = ContainsKey(
            name="test_contains_key",
            parameter=ContainsKeyParameter(dst=str(json_file), key_path="level1.level2.level3.level4"),
        )
        result = test.test()

        assert_test_success(result)
        assert "deep_value" in result.details[0]

    def test_contains_key_failure_missing_key(self, create_json_file):
        """Test failure when key doesn't exist."""
        json_file = create_json_file("test.json", {"name": "Alice", "age": 30})

        test = ContainsKey(
            name="test_contains_key", parameter=ContainsKeyParameter(dst=str(json_file), key_path="city")
        )
        result = test.test()

        assert_test_failed(result)
        assert "does not exist" in result.details[0]

    def test_contains_key_failure_missing_nested_key(self, create_json_file):
        """Test failure when nested key path doesn't exist."""
        json_file = create_json_file("test.json", {"user": {"profile": {"name": "Alice"}}})

        test = ContainsKey(
            name="test_contains_key", parameter=ContainsKeyParameter(dst=str(json_file), key_path="user.profile.age")
        )
        result = test.test()

        assert_test_failed(result)
        assert "does not exist" in result.details[0]

    def test_contains_key_error_malformed_json(self, tmp_path):
        """Test failure with malformed JSON file."""
        json_file = tmp_path / "malformed.json"
        json_file.write_text("{invalid json content")

        test = ContainsKey(
            name="test_contains_key", parameter=ContainsKeyParameter(dst=str(json_file), key_path="name")
        )
        result = test.test()

        assert_test_error(result)
        assert "Invalid JSON" in result.details[0]

    def test_contains_key_error_file_not_found(self, tmp_path):
        """Test error when JSON file doesn't exist."""
        test = ContainsKey(
            name="test_contains_key",
            parameter=ContainsKeyParameter(dst=str(tmp_path / "nonexistent.json"), key_path="name"),
        )
        result = test.test()

        assert_test_error(result)
        assert "does not exist" in result.details[0]

    def test_contains_key_success_with_null_value(self, create_json_file):
        """Test successful key check when value is null."""
        json_file = create_json_file("test.json", {"name": "Alice", "email": None})

        test = ContainsKey(
            name="test_contains_key", parameter=ContainsKeyParameter(dst=str(json_file), key_path="email")
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
        json_file = create_json_file("test.json", {"name": "Alice", "age": 30})

        test = ValueMatches(
            name="test_value_matches",
            parameter=ValueMatchesParameter(dst=str(json_file), key_path="name", expected_value="Alice"),
        )
        result = test.test()

        assert_test_success(result)
        assert "Alice" in result.details[0]

    def test_value_matches_success_number(self, create_json_file):
        """Test successful numeric value comparison."""
        json_file = create_json_file("test.json", {"age": 30, "score": 95.5})

        test = ValueMatches(
            name="test_value_matches",
            parameter=ValueMatchesParameter(dst=str(json_file), key_path="age", expected_value=30),
        )
        result = test.test()

        assert_test_success(result)

    def test_value_matches_success_float(self, create_json_file):
        """Test successful float value comparison."""
        json_file = create_json_file("test.json", {"score": 95.5})

        test = ValueMatches(
            name="test_value_matches",
            parameter=ValueMatchesParameter(dst=str(json_file), key_path="score", expected_value=95.5),
        )
        result = test.test()

        assert_test_success(result)

    def test_value_matches_success_boolean_true(self, create_json_file):
        """Test successful boolean True value comparison."""
        json_file = create_json_file("test.json", {"active": True, "verified": False})

        test = ValueMatches(
            name="test_value_matches",
            parameter=ValueMatchesParameter(dst=str(json_file), key_path="active", expected_value=True),
        )
        result = test.test()

        assert_test_success(result)

    def test_value_matches_success_boolean_false(self, create_json_file):
        """Test successful boolean False value comparison."""
        json_file = create_json_file("test.json", {"active": False})

        test = ValueMatches(
            name="test_value_matches",
            parameter=ValueMatchesParameter(dst=str(json_file), key_path="active", expected_value=False),
        )
        result = test.test()

        assert_test_success(result)

    def test_value_matches_success_nested(self, create_json_file):
        """Test successful nested value comparison."""
        json_file = create_json_file("test.json", {"user": {"profile": {"name": "Alice", "age": 30}}})

        test = ValueMatches(
            name="test_value_matches",
            parameter=ValueMatchesParameter(dst=str(json_file), key_path="user.profile.name", expected_value="Alice"),
        )
        result = test.test()

        assert_test_success(result)

    def test_value_matches_success_regex_match(self, create_json_file):
        """Test successful regex matching with regex_match=True."""
        json_file = create_json_file("test.json", {"email": "alice@example.com", "phone": "123-4567"})

        test = ValueMatches(
            name="test_value_matches",
            parameter=ValueMatchesParameter(
                dst=str(json_file), key_path="email", expected_value=r".*@example\.com", regex_match=True
            ),
        )
        result = test.test()

        assert_test_success(result)
        assert "matches regex" in result.details[0]

    def test_value_matches_failure_regex_no_match(self, create_json_file):
        """Test failure when regex doesn't match."""
        json_file = create_json_file("test.json", {"email": "alice@test.com"})

        test = ValueMatches(
            name="test_value_matches",
            parameter=ValueMatchesParameter(
                dst=str(json_file), key_path="email", expected_value=r".*@example\.com", regex_match=True
            ),
        )
        result = test.test()

        assert_test_failed(result)
        assert "does not match regex" in result.details[0]

    def test_value_matches_success_wildcard_array_any_mode(self, create_json_file):
        """Test successful wildcard array matching with any mode."""
        json_file = create_json_file(
            "test.json",
            {"users": [{"name": "Alice", "age": 30}, {"name": "Bob", "age": 25}, {"name": "Charlie", "age": 35}]},
        )

        test = ValueMatches(
            name="test_value_matches",
            parameter=ValueMatchesParameter(
                dst=str(json_file), key_path="users[*].age", expected_value=30, wildcard_mode="any"
            ),
        )
        result = test.test()

        assert_test_success(result)
        assert "matched" in result.details[0]
        assert "mode: any" in result.details[0]

    def test_value_matches_success_wildcard_array_all_mode(self, create_json_file):
        """Test successful wildcard array matching with all mode."""
        json_file = create_json_file(
            "test.json", {"items": [{"status": "active"}, {"status": "active"}, {"status": "active"}]}
        )

        test = ValueMatches(
            name="test_value_matches",
            parameter=ValueMatchesParameter(
                dst=str(json_file), key_path="items[*].status", expected_value="active", wildcard_mode="all"
            ),
        )
        result = test.test()

        assert_test_success(result)
        assert "matched all" in result.details[0]
        assert "mode: all" in result.details[0]

    def test_value_matches_failure_wildcard_array_all_mode(self, create_json_file):
        """Test failure when not all array elements match in all mode."""
        json_file = create_json_file(
            "test.json", {"items": [{"status": "active"}, {"status": "inactive"}, {"status": "active"}]}
        )

        test = ValueMatches(
            name="test_value_matches",
            parameter=ValueMatchesParameter(
                dst=str(json_file), key_path="items[*].status", expected_value="active", wildcard_mode="all"
            ),
        )
        result = test.test()

        assert_test_failed(result)
        assert "mode: all" in result.details[0]
        assert "matched 2/3" in result.details[0]

    def test_value_matches_success_wildcard_object_keys(self, create_json_file):
        """Test successful wildcard matching for all object keys."""
        json_file = create_json_file(
            "test.json",
            {
                "config": {
                    "feature_a": {"enabled": True},
                    "feature_b": {"enabled": True},
                    "feature_c": {"enabled": True},
                }
            },
        )

        test = ValueMatches(
            name="test_value_matches",
            parameter=ValueMatchesParameter(
                dst=str(json_file), key_path="config.*.enabled", expected_value=True, wildcard_mode="all"
            ),
        )
        result = test.test()

        assert_test_success(result)
        assert "mode: all" in result.details[0]

    def test_value_matches_failure_wildcard_no_match_any_mode(self, create_json_file):
        """Test failure when wildcard matches no values in any mode."""
        json_file = create_json_file("test.json", {"users": [{"name": "Alice", "age": 30}, {"name": "Bob", "age": 25}]})

        test = ValueMatches(
            name="test_value_matches",
            parameter=ValueMatchesParameter(
                dst=str(json_file), key_path="users[*].age", expected_value=40, wildcard_mode="any"
            ),
        )
        result = test.test()

        assert_test_failed(result)
        assert "matched 0/" in result.details[0]

    def test_value_matches_success_wildcard_object_any_mode(self, create_json_file):
        """Test successful wildcard object matching with any mode."""
        json_file = create_json_file(
            "test.json",
            {
                "config": {
                    "feature_a": {"enabled": False},
                    "feature_b": {"enabled": True},
                    "feature_c": {"enabled": False},
                }
            },
        )

        test = ValueMatches(
            name="test_value_matches",
            parameter=ValueMatchesParameter(
                dst=str(json_file), key_path="config.*.enabled", expected_value=True, wildcard_mode="any"
            ),
        )
        result = test.test()

        assert_test_success(result)
        assert "mode: any" in result.details[0]

    def test_value_matches_with_placeholder_simple(self, create_json_file, variable_metadata_simple):
        """Test value matching with simple placeholder."""
        json_file = create_json_file("test.json", {"result": "value1", "output": "value2"})

        test = ValueMatches(
            name="test_value_matches",
            parameter=ValueMatchesParameter(dst=str(json_file), key_path="result", expected_value="{{VAR1}}"),
            variable_metadata=variable_metadata_simple,
        )
        result = test.test()

        assert_test_success(result)

    def test_value_matches_failure_placeholder_mismatch(self, create_json_file, variable_metadata_simple):
        """Test failure when placeholder value doesn't match."""
        json_file = create_json_file("test.json", {"result": "wrong_value"})

        test = ValueMatches(
            name="test_value_matches",
            parameter=ValueMatchesParameter(dst=str(json_file), key_path="result", expected_value="{{VAR1}}"),
            variable_metadata=variable_metadata_simple,
        )
        result = test.test()

        assert_test_failed(result)

    def test_value_matches_failure_direct_comparison(self, create_json_file):
        """Test failure when direct value comparison doesn't match."""
        json_file = create_json_file("test.json", {"name": "Alice"})

        test = ValueMatches(
            name="test_value_matches",
            parameter=ValueMatchesParameter(dst=str(json_file), key_path="name", expected_value="Bob"),
        )
        result = test.test()

        assert_test_failed(result)
        assert "expected" in result.details[0]
        assert "Bob" in result.details[0]
        assert "Alice" in result.details[0]

    def test_value_matches_failure_key_not_found(self, create_json_file):
        """Test failure when key path doesn't exist."""
        json_file = create_json_file("test.json", {"name": "Alice"})

        test = ValueMatches(
            name="test_value_matches",
            parameter=ValueMatchesParameter(dst=str(json_file), key_path="age", expected_value=30),
        )
        result = test.test()

        assert_test_failed(result)
        assert "does not exist" in result.details[0]

    def test_value_matches_error_malformed_json(self, tmp_path):
        """Test failure with malformed JSON file."""
        json_file = tmp_path / "malformed.json"
        json_file.write_text("{invalid: json}")

        test = ValueMatches(
            name="test_value_matches",
            parameter=ValueMatchesParameter(dst=str(json_file), key_path="name", expected_value="Alice"),
        )
        result = test.test()

        assert_test_error(result)
        assert "Invalid JSON" in result.details[0]

    def test_value_matches_success_nested_wildcard(self, create_json_file):
        """Test successful nested wildcard path matching."""
        json_file = create_json_file(
            "test.json",
            {
                "teams": [
                    {"members": [{"role": "admin"}, {"role": "user"}]},
                    {"members": [{"role": "admin"}, {"role": "admin"}]},
                ]
            },
        )

        test = ValueMatches(
            name="test_value_matches",
            parameter=ValueMatchesParameter(
                dst=str(json_file), key_path="teams[*].members[*].role", expected_value="admin", wildcard_mode="any"
            ),
        )
        result = test.test()

        assert_test_success(result)

    def test_value_matches_success_case_sensitive(self, create_json_file):
        """Test that value matching is case sensitive by default."""
        json_file = create_json_file("test.json", {"name": "Alice"})

        test = ValueMatches(
            name="test_value_matches",
            parameter=ValueMatchesParameter(dst=str(json_file), key_path="name", expected_value="alice"),
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
        json_file = create_json_file("test.json", {"names": ["Alice", "Bob", "Charlie"]})

        test = ArrayContains(
            name="test_array_contains",
            parameter=ArrayContainsParameter(dst=str(json_file), array_path="names", expected_value="Bob"),
        )
        result = test.test()

        assert_test_success(result)
        assert "matches" in result.details[0]
        assert "Bob" in result.details[0]

    def test_array_contains_success_number(self, create_json_file):
        """Test successful numeric element membership."""
        json_file = create_json_file("test.json", {"scores": [85, 90, 95, 100]})

        test = ArrayContains(
            name="test_array_contains",
            parameter=ArrayContainsParameter(dst=str(json_file), array_path="scores", expected_value=95),
        )
        result = test.test()

        assert_test_success(result)

    def test_array_contains_success_boolean(self, create_json_file):
        """Test successful boolean element membership."""
        json_file = create_json_file("test.json", {"flags": [True, False, True]})

        test = ArrayContains(
            name="test_array_contains",
            parameter=ArrayContainsParameter(dst=str(json_file), array_path="flags", expected_value=False),
        )
        result = test.test()

        assert_test_success(result)

    def test_array_contains_success_nested_array(self, create_json_file):
        """Test successful nested array element membership."""
        json_file = create_json_file("test.json", {"data": {"results": {"values": [10, 20, 30]}}})

        test = ArrayContains(
            name="test_array_contains",
            parameter=ArrayContainsParameter(dst=str(json_file), array_path="data.results.values", expected_value=20),
        )
        result = test.test()

        assert_test_success(result)

    def test_array_contains_success_complex_object(self, create_json_file):
        """Test successful complex object element membership."""
        json_file = create_json_file("test.json", {"users": [{"name": "Alice", "age": 30}, {"name": "Bob", "age": 25}]})

        test = ArrayContains(
            name="test_array_contains",
            parameter=ArrayContainsParameter(
                dst=str(json_file), array_path="users", expected_value={"name": "Alice", "age": 30}
            ),
        )
        result = test.test()

        assert_test_success(result)

    def test_array_contains_success_nested_list(self, create_json_file):
        """Test successful nested list element membership."""
        json_file = create_json_file("test.json", {"matrix": [[1, 2], [3, 4], [5, 6]]})

        test = ArrayContains(
            name="test_array_contains",
            parameter=ArrayContainsParameter(dst=str(json_file), array_path="matrix", expected_value=[3, 4]),
        )
        result = test.test()

        assert_test_success(result)

    def test_array_contains_failure_element_not_found(self, create_json_file):
        """Test failure when element is not in array."""
        json_file = create_json_file("test.json", {"names": ["Alice", "Bob", "Charlie"]})

        test = ArrayContains(
            name="test_array_contains",
            parameter=ArrayContainsParameter(dst=str(json_file), array_path="names", expected_value="David"),
        )
        result = test.test()

        assert_test_failed(result)
        assert "has no element matching" in result.details[0]

    def test_array_contains_failure_not_array(self, create_json_file):
        """Test failure when path points to non-array value."""
        json_file = create_json_file("test.json", {"name": "Alice"})

        test = ArrayContains(
            name="test_array_contains",
            parameter=ArrayContainsParameter(dst=str(json_file), array_path="name", expected_value="Alice"),
        )
        result = test.test()

        assert_test_failed(result)
        assert "not an array" in result.details[0]

    def test_array_contains_failure_array_path_not_found(self, create_json_file):
        """Test failure when array path doesn't exist."""
        json_file = create_json_file("test.json", {"names": ["Alice"]})

        test = ArrayContains(
            name="test_array_contains",
            parameter=ArrayContainsParameter(dst=str(json_file), array_path="values", expected_value="test"),
        )
        result = test.test()

        assert_test_failed(result)
        assert "does not exist" in result.details[0]

    def test_array_contains_with_placeholder_simple(self, create_json_file, variable_metadata_simple):
        """Test array contains with simple placeholder."""
        json_file = create_json_file("test.json", {"results": ["value1", "value2", "other"]})

        test = ArrayContains(
            name="test_array_contains",
            parameter=ArrayContainsParameter(dst=str(json_file), array_path="results", expected_value="{{VAR1}}"),
            variable_metadata=variable_metadata_simple,
        )
        result = test.test()

        assert_test_success(result)
        assert "matches" in result.details[0]

    def test_array_contains_failure_placeholder_mismatch(self, create_json_file, variable_metadata_simple):
        """Test failure when placeholder doesn't match any array element."""
        json_file = create_json_file("test.json", {"results": ["wrong1", "wrong2", "wrong3"]})

        test = ArrayContains(
            name="test_array_contains",
            parameter=ArrayContainsParameter(dst=str(json_file), array_path="results", expected_value="{{VAR1}}"),
            variable_metadata=variable_metadata_simple,
        )
        result = test.test()

        assert_test_failed(result)
        assert "has no element matching" in result.details[0]

    def test_array_contains_empty_array(self, create_json_file):
        """Test behavior with empty array."""
        json_file = create_json_file("test.json", {"items": []})

        test = ArrayContains(
            name="test_array_contains",
            parameter=ArrayContainsParameter(dst=str(json_file), array_path="items", expected_value="anything"),
        )
        result = test.test()

        assert_test_failed(result)
        assert "has no element matching" in result.details[0]

    def test_array_contains_success_null_element(self, create_json_file):
        """Test successful null element membership."""
        json_file = create_json_file("test.json", {"values": ["a", None, "b"]})

        test = ArrayContains(
            name="test_array_contains",
            parameter=ArrayContainsParameter(dst=str(json_file), array_path="values", expected_value=None),
        )
        result = test.test()

        assert_test_success(result)

    def test_array_contains_error_malformed_json(self, tmp_path):
        """Test failure with malformed JSON file."""
        json_file = tmp_path / "malformed.json"
        json_file.write_text("[invalid json")

        test = ArrayContains(
            name="test_array_contains",
            parameter=ArrayContainsParameter(dst=str(json_file), array_path="items", expected_value="test"),
        )
        result = test.test()

        assert_test_error(result)
        assert "Invalid JSON" in result.details[0]

    def test_array_contains_error_file_not_found(self, tmp_path):
        """Test error when JSON file doesn't exist."""
        test = ArrayContains(
            name="test_array_contains",
            parameter=ArrayContainsParameter(
                dst=str(tmp_path / "nonexistent.json"), array_path="items", expected_value="test"
            ),
        )
        result = test.test()

        assert_test_error(result)
        assert "does not exist" in result.details[0]


# ============================================================================
# Key path syntax: numeric indexes, top-level arrays, quoted keys
# ============================================================================

PATH_DATA = {
    "items": [{"name": "first"}, {"name": "middle"}, {"name": "last"}],
    "a.b": {"c": 1},
    "list[x]": "bracketed",
}


@pytest.mark.parametrize(
    ("key_path", "expected"),
    [
        ("items[0].name", "first"),
        ("items[-1].name", "last"),
        ("['a.b'].c", 1),
        ('["a.b"].c', 1),
        ("list[x]", "bracketed"),
    ],
)
def test_value_matches_path_syntax(create_json_file, key_path, expected):
    json_file = create_json_file("paths.json", PATH_DATA)

    result = ValueMatches(
        name="t", parameter=ValueMatchesParameter(dst=str(json_file), key_path=key_path, expected_value=expected)
    ).test()

    assert_test_success(result)


def test_value_matches_index_out_of_range_fails(create_json_file):
    json_file = create_json_file("paths.json", PATH_DATA)

    result = ValueMatches(
        name="t", parameter=ValueMatchesParameter(dst=str(json_file), key_path="items[3].name", expected_value="x")
    ).test()

    assert_test_failed(result)


@pytest.mark.parametrize(("key_path", "expected"), [("[1].id", 2), ("[*].id", 3), ("[-1].tags[0]", "z")])
def test_value_matches_top_level_array(create_json_file, key_path, expected):
    json_file = create_json_file("top.json", [{"id": 1}, {"id": 2}, {"id": 3, "tags": ["z"]}])

    result = ValueMatches(
        name="t", parameter=ValueMatchesParameter(dst=str(json_file), key_path=key_path, expected_value=expected)
    ).test()

    assert_test_success(result)


def test_contains_key_quoted_key(create_json_file):
    json_file = create_json_file("paths.json", PATH_DATA)

    result = ContainsKey(name="t", parameter=ContainsKeyParameter(dst=str(json_file), key_path="['a.b']")).test()

    assert_test_success(result)


# ============================================================================
# ValueCount Tests
# ============================================================================

COUNT_DATA = {
    "groups": [
        {"items": [{"tag": "archived"}, {"tag": "new"}]},
        {"items": [{"tag": "archived"}, {"tag": "archived-old"}, {"other": None}]},
    ],
    "tags": ["a", "b", "a"],
    "empty": None,
}


def _count(path, **params):
    return ValueCount(name="t", parameter=ValueCountParameter(dst=str(path), **params)).test()


class TestValueCount:
    """Tests for ValueCount testfunction."""

    @pytest.mark.parametrize(
        ("key_path", "count"),
        [
            ("groups[*].items[*].tag", 4),
            ("groups[*].items[*]", 5),
            ("tags", 1),  # an array is one value
            ("tags[*]", 3),
            ("empty", 1),  # null counts
            ("missing", 0),
            ("groups[5].items", 0),
        ],
    )
    def test_counts_resolved_values(self, create_json_file, key_path, count):
        result = _count(create_json_file("c.json", COUNT_DATA), key_path=key_path, expected_count=count)

        assert_test_success(result)
        assert f"{count} value(s)" in result.details[0]

    def test_absent_key_with_zero_count(self, create_json_file):
        path = create_json_file("c.json", COUNT_DATA)

        assert_test_success(_count(path, key_path="settings.secret", expected_count=0))
        assert_test_failed(_count(path, key_path="tags", expected_count=0))

    def test_counts_matching_values(self, create_json_file):
        path = create_json_file("c.json", COUNT_DATA)

        assert_test_success(
            _count(path, key_path="groups[*].items[*].tag", expected_value="archived", expected_count=2)
        )
        # a path selecting one array compares its elements
        assert_test_success(_count(path, key_path="tags", expected_value="a", expected_count=2))
        assert_test_success(_count(path, key_path="tags", expected_value="c", expected_count=0))

    def test_regex_match(self, create_json_file):
        path = create_json_file("c.json", COUNT_DATA)

        result = _count(
            path, key_path="groups[*].items[*].tag", expected_value="^archived", regex_match=True, expected_count=3
        )

        assert_test_success(result)

    @pytest.mark.parametrize(
        ("comparison_type", "expected_count", "passes"),
        [
            ("greater", 3, True),
            ("greater", 4, False),
            ("less", 5, True),
            ("greater_equal", 4, True),
            ("less_equal", 3, False),
            ("equals", 5, False),
        ],
    )
    def test_comparison_types(self, create_json_file, comparison_type, expected_count, passes):
        path = create_json_file("c.json", COUNT_DATA)

        result = _count(
            path, key_path="groups[*].items[*].tag", expected_count=expected_count, comparison_type=comparison_type
        )

        (assert_test_success if passes else assert_test_failed)(result)

    @pytest.mark.parametrize(
        "params",
        [
            {"expected_count": -1},
            {"expected_count": "two"},
            {"expected_count": True},
            {"expected_count": 1, "comparison_type": "roughly"},
            {"expected_count": 1, "expected_value": "[unclosed", "regex_match": True},
        ],
    )
    def test_bad_parameters_are_errors(self, create_json_file, params):
        result = _count(create_json_file("c.json", COUNT_DATA), key_path="tags", **params)

        assert_test_error(result)

    def test_missing_file_is_error(self, tmp_path):
        result = _count(tmp_path / "missing.json", key_path="a", expected_count=0)

        assert_test_error(result)
        assert "does not exist" in result.details[0]

    def test_invalid_json_is_error(self, tmp_path):
        path = tmp_path / "bad.json"
        path.write_text('{"a": 1,')

        result = _count(path, key_path="a", expected_count=0)

        assert_test_error(result)
        assert "Invalid JSON" in result.details[0]

    def test_glob_without_match_is_error(self, tmp_path):
        assert_test_error(_count(tmp_path / "none*.json", key_path="a", expected_count=0))

    def test_lz4_compressed_json(self, tmp_path):
        from adarelib.testset import lz4

        data = json.dumps(COUNT_DATA).encode()
        n = len(data)
        rest, ext = n - 15, b""
        while rest >= 255:
            ext += b"\xff"
            rest -= 255
        # block-with-header format: magic, u32 size, one LZ4 block of literals only
        block = b"\xf0" + ext + bytes([rest]) + data
        path = tmp_path / "store.jsonlz4"
        path.write_bytes(lz4.BLOCK_HEADER_MAGIC + n.to_bytes(4, "little") + block)

        result = _count(f"{path}!", key_path="tags[*]", expected_value="a", expected_count=2)

        assert_test_success(result)


# --- round 2: value_decode, values_compare with other_dst --------------------------------


def _r2_write(path, data):
    path.write_text(json.dumps(data), encoding='utf-8')
    return str(path)


def _r2_run(function, **params):
    testfunction = getattr(json_tf_module, function)
    return testfunction._test_class(name='t', parameter=testfunction._parameter_class(**params)).test()


@pytest.fixture
def r2_files(tmp_path):
    before = _r2_write(tmp_path / 'before.json', {'count': 3, 'saved': '2026-03-01T10:00:00Z', 'blob': 'eyJpZCI6IDd9'})
    after = _r2_write(tmp_path / 'after.json', {'count': 5, 'saved': '2026-03-01T10:05:00Z', 'blob': 'eyJpZCI6IDl9'})
    return before, after


def test_values_compare_other_dst(r2_files, tmp_path):
    before, after = r2_files
    run = _r2_run
    assert (
        run(
            'values_compare',
            dst=after,
            key_path='count',
            other_key_path='count',
            other_dst=before,
            comparison_type='greater',
        ).status
        == StatusEnum.SUCCESS
    )
    assert (
        run(
            'values_compare',
            dst=after,
            key_path='saved',
            other_key_path='saved',
            other_dst=before,
            comparison_type='less',
        ).status
        == StatusEnum.FAILED
    )
    assert (
        run('values_compare', dst=after, key_path='count', other_key_path='count', other_dst=before, offset=2).status
        == StatusEnum.SUCCESS
    )
    missing = run(
        'values_compare', dst=after, key_path='count', other_key_path='count', other_dst=str(tmp_path / 'gone.json')
    )
    assert missing.status == StatusEnum.ERROR and 'does not exist' in missing.details[0]


def test_values_compare_other_dst_archive_member(r2_files, tmp_path):
    import zipfile as _zipfile

    before, after = r2_files
    archive = tmp_path / 'backup.zip'
    with _zipfile.ZipFile(archive, 'w') as zf:
        zf.write(before, 'state/before.json')
    result = _r2_run(
        'values_compare',
        dst=after,
        key_path='count',
        other_key_path='count',
        other_dst=f'{archive}!/state/before.json',
        comparison_type='greater',
    )
    assert result.status == StatusEnum.SUCCESS, result.details


def test_value_decode(r2_files):
    _, after = r2_files
    ok = _r2_run(
        'value_matches',
        dst=after,
        key_path='blob',
        expected_value=9,
        value_decode=['base64', 'json'],
        decoded_key_path='id',
    )
    assert ok.status == StatusEnum.SUCCESS, ok.details
    ordered = _r2_run(
        'values_compare',
        dst=after,
        key_path='blob',
        other_key_path='count',
        value_decode=['base64', 'json'],
        decoded_key_path='id',
    )
    assert ordered.status == StatusEnum.ERROR  # the count is no base64: decoding both sides fails
    bad = _r2_run('value_matches', dst=after, key_path='count', expected_value=5, value_decode='base64')
    assert bad.status == StatusEnum.ERROR and "'base64'" in bad.details[0]
    unknown = _r2_run('value_matches', dst=after, key_path='count', expected_value=5, value_decode='rot13')
    assert unknown.status == StatusEnum.ERROR
    no_path = _r2_run('value_matches', dst=after, key_path='blob', expected_value=9, value_decode='json')
    assert no_path.status == StatusEnum.ERROR
    plain = _r2_run('value_matches', dst=after, key_path='count', expected_value=5)
    assert plain.status == StatusEnum.SUCCESS
