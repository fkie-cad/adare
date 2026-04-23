"""Tests for BasicTest, resolve_var_in_match, and resolve_yamlobj_in_dict."""

import pytest

pytestmark = pytest.mark.unit

import re

import attrs

from adarelib.testset.basictest import (
    BasicTest,
    Parameter,
    resolve_var_in_match,
    resolve_yamlobj_in_dict,
)
from adarelib.testset.yaml.customtags import YamlString

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

@attrs.define
class DummyParam(Parameter):
    pass


def _make_test(variable_metadata=None, name="test1", description="test desc"):
    """Create a minimal BasicTest instance for testing."""
    return BasicTest(
        name=name,
        parameter=DummyParam(),
        description=description,
        variable_metadata=variable_metadata,
    )


def _make_regex_match(text: str, variables_pattern: str = r'\{\{\s*(\w+)\s*\}\}'):
    """Return the first regex match object from *text* using the given pattern."""
    return re.search(variables_pattern, text)


# ===========================================================================
# resolve_var_in_match
# ===========================================================================

class TestResolveVarInMatch:
    """Tests for the module-level resolve_var_in_match function."""

    def test_variable_found_no_escape(self):
        """When the variable exists and escape=False, the raw value is returned."""
        match = _make_regex_match("{{ USERNAME }}")
        result = resolve_var_in_match(match, {"USERNAME": "admin"}, escape=False)
        assert result == "admin"

    def test_variable_found_escape_true(self):
        """When escape=True, the value is passed through re.escape."""
        match = _make_regex_match("{{ PATH }}")
        result = resolve_var_in_match(match, {"PATH": "C:\\Users"}, escape=True)
        assert result == re.escape("C:\\Users")

    def test_variable_missing_returns_empty(self):
        """When the variable key is not in the dict, an empty string is returned."""
        match = _make_regex_match("{{ MISSING }}")
        result = resolve_var_in_match(match, {"OTHER": "val"}, escape=False)
        assert result == ""

    def test_variable_with_regex_special_chars_escaped(self):
        """Regex-special characters in the value are escaped when escape=True."""
        special = "file[0].log(1)+2*3?"
        match = _make_regex_match("{{ FILE }}")
        result = resolve_var_in_match(match, {"FILE": special}, escape=True)
        # The escaped version must match the literal string via re
        assert re.fullmatch(result, special)
        # And must differ from the raw value (since it contains special chars)
        assert result != special

    def test_variable_found_escape_false_preserves_specials(self):
        """With escape=False, regex-special characters are returned as-is."""
        special = "hello.*world"
        match = _make_regex_match("{{ PAT }}")
        result = resolve_var_in_match(match, {"PAT": special}, escape=False)
        assert result == special


# ===========================================================================
# resolve_yamlobj_in_dict
# ===========================================================================

class TestResolveYamlobjInDict:
    """Tests for the module-level resolve_yamlobj_in_dict function."""

    def test_yamlcustomtag_values_resolved(self):
        """YamlCustomTag values are replaced with their __repr__."""
        tag = YamlString("hello")
        result = resolve_yamlobj_in_dict({"key": tag})
        assert result == {"key": "!s hello"}

    def test_nested_dict_resolved_recursively(self):
        """Nested dicts have their YamlCustomTag values resolved."""
        inner_tag = YamlString("inner")
        d = {"outer": {"nested": inner_tag}}
        result = resolve_yamlobj_in_dict(d)
        assert result == {"outer": {"nested": "!s inner"}}

    def test_list_values_with_yamlcustomtag(self):
        """YamlCustomTag items inside lists are resolved."""
        tag1 = YamlString("a")
        tag2 = YamlString("b")
        d = {"items": [tag1, "plain", tag2]}
        result = resolve_yamlobj_in_dict(d)
        assert result == {"items": ["!s a", "plain", "!s b"]}

    def test_plain_values_pass_through(self):
        """Non-YamlCustomTag values are copied unchanged."""
        d = {"str": "hello", "int": 42, "bool": True, "none": None}
        result = resolve_yamlobj_in_dict(d)
        assert result == d

    def test_empty_dict_returns_empty(self):
        """An empty dict input produces an empty dict output."""
        assert resolve_yamlobj_in_dict({}) == {}


# ===========================================================================
# BasicTest.has_placeholders / get_placeholders
# ===========================================================================

class TestHasPlaceholders:
    """Tests for BasicTest.has_placeholders."""

    def test_with_placeholder_returns_true(self):
        bt = _make_test()
        assert bt.has_placeholders("prefix-{{ VAR }}-suffix") is True

    def test_plain_text_returns_false(self):
        bt = _make_test()
        assert bt.has_placeholders("no placeholders here") is False

    def test_only_opening_braces_returns_false(self):
        bt = _make_test()
        assert bt.has_placeholders("{{ missing close") is False

    def test_only_closing_braces_returns_false(self):
        bt = _make_test()
        assert bt.has_placeholders("missing open }}") is False


class TestGetPlaceholders:
    """Tests for BasicTest.get_placeholders."""

    def test_extracts_multiple_names(self):
        bt = _make_test()
        result = bt.get_placeholders("{{ ALPHA }}-{{ BETA }}")
        assert result == ["ALPHA", "BETA"]

    def test_no_placeholders_returns_empty_list(self):
        bt = _make_test()
        assert bt.get_placeholders("plain text") == []

    def test_strips_whitespace_from_names(self):
        bt = _make_test()
        result = bt.get_placeholders("{{  SPACED  }}")
        assert result == ["SPACED"]

    def test_single_placeholder(self):
        bt = _make_test()
        result = bt.get_placeholders("Hello {{ WORLD }}")
        assert result == ["WORLD"]


# ===========================================================================
# BasicTest.resolve_variables
# ===========================================================================

class TestResolveVariables:
    """Tests for BasicTest.resolve_variables."""

    def test_replaces_placeholder_with_resolved_value(self):
        metadata = {
            "VAR1": {"resolved_value": "nginx"},
        }
        bt = _make_test(variable_metadata=metadata)
        result = bt.resolve_variables("service-{{ VAR1 }}")
        assert result == "service-nginx"

    def test_no_variable_metadata_returns_original(self):
        bt = _make_test(variable_metadata=None)
        assert bt.resolve_variables("{{ X }}") == "{{ X }}"

    def test_unmatched_placeholder_returns_original(self):
        """If the placeholder name is not in variable_metadata, it stays."""
        metadata = {"OTHER": {"resolved_value": "val"}}
        bt = _make_test(variable_metadata=metadata)
        result = bt.resolve_variables("{{ UNKNOWN }}")
        assert result == "{{ UNKNOWN }}"

    def test_multiple_placeholders_resolved(self):
        metadata = {
            "A": {"resolved_value": "1"},
            "B": {"resolved_value": "2"},
        }
        bt = _make_test(variable_metadata=metadata)
        result = bt.resolve_variables("{{ A }}-{{ B }}")
        assert result == "1-2"

    def test_text_without_placeholders_unchanged(self):
        metadata = {"X": {"resolved_value": "val"}}
        bt = _make_test(variable_metadata=metadata)
        assert bt.resolve_variables("plain") == "plain"


# ===========================================================================
# BasicTest.compare_with_placeholder
# ===========================================================================

class TestCompareWithPlaceholder:
    """Tests for BasicTest.compare_with_placeholder."""

    # --- string type (default) ---

    def test_string_exact_match(self):
        metadata = {"NAME": {"type": "string", "resolved_value": "hello"}}
        bt = _make_test(variable_metadata=metadata)
        success, msg = bt.compare_with_placeholder("NAME", "hello")
        assert success is True
        assert "match" in msg.lower()

    def test_string_mismatch(self):
        metadata = {"NAME": {"type": "string", "resolved_value": "hello"}}
        bt = _make_test(variable_metadata=metadata)
        success, msg = bt.compare_with_placeholder("NAME", "world")
        assert success is False
        assert "no match" in msg.lower()

    # --- regex type ---

    def test_regex_matching_pattern(self):
        metadata = {"PAT": {"type": "regex", "resolved_value": r"\d{3}-\d{4}"}}
        bt = _make_test(variable_metadata=metadata)
        success, msg = bt.compare_with_placeholder("PAT", "123-4567")
        assert success is True
        assert "match" in msg.lower()

    def test_regex_non_matching_pattern(self):
        metadata = {"PAT": {"type": "regex", "resolved_value": r"^\d+$"}}
        bt = _make_test(variable_metadata=metadata)
        success, msg = bt.compare_with_placeholder("PAT", "abc")
        assert success is False
        assert "no match" in msg.lower()

    def test_regex_invalid_pattern(self):
        metadata = {"PAT": {"type": "regex", "resolved_value": "[invalid"}}
        bt = _make_test(variable_metadata=metadata)
        success, msg = bt.compare_with_placeholder("PAT", "anything")
        assert success is False
        assert "error" in msg.lower()

    # --- timestamp type ---

    def test_timestamp_with_tolerance_within_range(self):
        metadata = {
            "TS": {
                "type": "timestamp",
                "resolved_value": "2026-03-31T12:00:00",
                "tolerance": 60,
            },
        }
        bt = _make_test(variable_metadata=metadata)
        success, msg = bt.compare_with_placeholder("TS", "2026-03-31T12:00:30")
        assert success is True
        assert "tolerance" in msg.lower() or "within" in msg.lower()

    def test_timestamp_without_tolerance_exact_match(self):
        """No tolerance means exact string comparison."""
        metadata = {
            "TS": {
                "type": "timestamp",
                "resolved_value": "2026-03-31T12:00:00",
            },
        }
        bt = _make_test(variable_metadata=metadata)
        success, msg = bt.compare_with_placeholder("TS", "2026-03-31T12:00:00")
        assert success is True
