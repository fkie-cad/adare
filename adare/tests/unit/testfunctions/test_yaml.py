"""Unit tests for YAML testfunctions."""

import importlib.util
import sys
import zipfile
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

PROJECT_ROOT = Path(__file__).parent.parent.parent.parent
ADARELIB_ROOT = PROJECT_ROOT.parent / "adarelib"
if str(ADARELIB_ROOT) not in sys.path:
    sys.path.insert(0, str(ADARELIB_ROOT))

from adarelib.helper.module import import_module_from_pyfile

yaml_tf = import_module_from_pyfile(PROJECT_ROOT / "appdata" / "testfunctions" / "yaml" / "yaml.py")

ContainsKey = yaml_tf.contains_key._test_class
ContainsKeyParameter = yaml_tf.contains_key._parameter_class
ValueMatches = yaml_tf.value_matches._test_class
ValueMatchesParameter = yaml_tf.value_matches._parameter_class
ValueCount = yaml_tf.value_count._test_class
ValueCountParameter = yaml_tf.value_count._parameter_class

helpers_path = Path(__file__).parent / "helpers.py"
spec = importlib.util.spec_from_file_location("helpers", helpers_path)
helpers = importlib.util.module_from_spec(spec)
spec.loader.exec_module(helpers)

assert_test_success = helpers.assert_test_success
assert_test_failed = helpers.assert_test_failed
assert_test_error = helpers.assert_test_error

CONFIG = """\
display:
  font:
    size: 12
    family: Example Sans
  dark: true
  legacy: off
installed: 2024-01-15
updated: 2024-01-15 10:30:00
synced: 2024-01-15T10:30:00Z
servers:
  - host: a.example.test
    port: 8080
  - host: b.example.test
    port: 9090
"app.window":
  width: 1280
blob: !!binary AQL/
nothing: null
"""

MULTI = """\
kind: profile
name: first
---
kind: profile
name: second
---
kind: theme
name: dark
"""


def contains_key(dst, key_path):
    return ContainsKey(name="t", parameter=ContainsKeyParameter(dst=str(dst), key_path=key_path)).test()


def value_matches(dst, key_path, expected_value, **kwargs):
    parameter = ValueMatchesParameter(dst=str(dst), key_path=key_path, expected_value=expected_value, **kwargs)
    return ValueMatches(name="t", parameter=parameter).test()


def value_count(dst, key_path, expected_count, **kwargs):
    parameter = ValueCountParameter(dst=str(dst), key_path=key_path, expected_count=expected_count, **kwargs)
    return ValueCount(name="t", parameter=parameter).test()


@pytest.fixture
def config(tmp_path):
    path = tmp_path / "config.yaml"
    path.write_text(CONFIG, encoding="utf-8")
    return path


@pytest.fixture
def multi(tmp_path):
    path = tmp_path / "profiles.yaml"
    path.write_text(MULTI, encoding="utf-8")
    return path


@pytest.fixture
def bad_yaml(tmp_path):
    path = tmp_path / "bad.yaml"
    path.write_text("a: [1, 2\nb: 3\n", encoding="utf-8")
    return path


def test_module_uses_pyyaml_not_itself():
    assert hasattr(yaml_tf.yaml, "safe_load_all")
    assert yaml_tf.yaml.__name__ == "yaml"


# ============================================================================
# contains_key
# ============================================================================


class TestContainsKey:
    def test_nested_key(self, config):
        result = contains_key(config, "display.font.size")
        assert_test_success(result)
        assert "12" in result.details[0]

    def test_null_value_counts_as_present(self, config):
        assert_test_success(contains_key(config, "nothing"))

    def test_dotted_key_in_brackets(self, config):
        assert_test_success(contains_key(config, "['app.window'].width"))

    def test_missing_key_fails(self, config):
        result = contains_key(config, "display.font.weight")
        assert_test_failed(result)
        assert "does not exist" in result.details[0]

    def test_documents_are_a_top_level_list(self, multi):
        assert_test_success(contains_key(multi, "[2].kind"))
        assert_test_failed(contains_key(multi, "[3].kind"))
        assert_test_failed(contains_key(multi, "kind"))

    def test_empty_file_has_no_keys(self, tmp_path):
        path = tmp_path / "empty.yaml"
        path.write_text("", encoding="utf-8")
        assert_test_failed(contains_key(path, "a"))

    def test_missing_file_is_error(self, tmp_path):
        result = contains_key(tmp_path / "missing.yaml", "a")
        assert_test_error(result)
        assert "does not exist" in " ".join(result.details)

    def test_corrupt_is_error(self, bad_yaml):
        result = contains_key(bad_yaml, "a")
        assert_test_error(result)
        assert "Invalid YAML" in " ".join(result.details)

    @pytest.mark.parametrize(
        "content",
        ["a:\n\tb: 1\n", "d: 2024-02-30\n", "x: !!python/object:os.getcwd {}\n", "? [a]\n: 1\n", "a: *undefined\n"],
        ids=["tab", "impossible-date", "unsafe-tag", "unhashable-key", "unknown-alias"],
    )
    def test_invalid_content_is_error(self, tmp_path, content):
        path = tmp_path / "bad.yaml"
        path.write_text(content, encoding="utf-8")
        assert_test_error(contains_key(path, "a"))

    def test_undecodable_bytes_are_error(self, tmp_path):
        path = tmp_path / "bad.yaml"
        path.write_bytes(b"a: \xff\xfe\xfa\n")
        assert_test_error(contains_key(path, "a"))

    def test_glob_errors(self, tmp_path):
        assert_test_error(contains_key(tmp_path / "*.yaml", "a"))
        for name in ("a.yaml", "b.yaml"):
            (tmp_path / name).write_text("a: 1\n", encoding="utf-8")
        assert_test_error(contains_key(tmp_path / "*.yaml", "a"))

    def test_member_of_zip_archive(self, tmp_path):
        archive = tmp_path / "backup.zip"
        with zipfile.ZipFile(archive, "w") as zf:
            zf.writestr("app/config.yaml", CONFIG)
        assert_test_success(contains_key(f"{archive}!/app/config.yaml", "servers[1].host"))


# ============================================================================
# value_matches
# ============================================================================


class TestValueMatches:
    def test_string_value(self, config):
        assert_test_success(value_matches(config, "display.font.family", "Example Sans"))

    def test_mismatch_fails(self, config):
        result = value_matches(config, "display.font.size", 14)
        assert_test_failed(result)
        assert "12" in result.details[0]

    def test_types_are_kept(self, config):
        assert_test_failed(value_matches(config, "display.font.size", "12"))
        assert_test_success(value_matches(config, "display.dark", True))
        assert_test_success(value_matches(config, "display.legacy", False))  # YAML 1.1: off is a boolean
        assert_test_success(value_matches(config, "nothing", None))

    def test_dates_compare_as_iso_strings(self, config):
        assert_test_success(value_matches(config, "installed", "2024-01-15"))
        assert_test_success(value_matches(config, "updated", "2024-01-15T10:30:00"))
        assert_test_success(value_matches(config, "synced", "2024-01-15T10:30:00+00:00"))

    def test_binary_compares_as_hex(self, config):
        assert_test_success(value_matches(config, "blob", "0102ff"))

    def test_wildcard_any_and_all(self, config):
        assert_test_success(value_matches(config, "servers[*].port", 9090))
        assert_test_failed(value_matches(config, "servers[*].port", 9090, wildcard_mode="all"))
        assert_test_success(
            value_matches(config, "servers[*].host", r"\.example\.test$", regex_match=True, wildcard_mode="all")
        )

    def test_multi_document(self, multi):
        assert_test_success(value_matches(multi, "[1].name", "second"))
        assert_test_success(value_matches(multi, "[*].kind", "theme"))
        assert_test_failed(value_matches(multi, "[*].kind", "profile", wildcard_mode="all"))

    def test_missing_key_fails(self, config):
        assert_test_failed(value_matches(config, "display.font.weight", "bold"))

    def test_bad_wildcard_mode_is_error(self, config):
        assert_test_error(value_matches(config, "display.dark", True, wildcard_mode="most"))

    def test_invalid_regex_is_error(self, config):
        assert_test_error(value_matches(config, "display.font.family", "(unclosed", regex_match=True))

    def test_missing_file_is_error(self, tmp_path):
        assert_test_error(value_matches(tmp_path / "missing.yaml", "a", 1))

    def test_corrupt_is_error(self, bad_yaml):
        assert_test_error(value_matches(bad_yaml, "b", 3))

    def test_glob_errors(self, tmp_path):
        assert_test_error(value_matches(tmp_path / "*.yaml", "a", 1))
        for name in ("a.yaml", "b.yaml"):
            (tmp_path / name).write_text("a: 1\n", encoding="utf-8")
        assert_test_error(value_matches(tmp_path / "*.yaml", "a", 1))


# ============================================================================
# value_count
# ============================================================================


class TestValueCount:
    def test_counts_sequence_elements(self, config):
        assert_test_success(value_count(config, "servers[*]", 2))
        assert_test_failed(value_count(config, "servers[*]", 1))

    def test_counts_documents(self, multi):
        assert_test_success(value_count(multi, "[*]", 3))
        assert_test_success(value_count(multi, "[*].kind", 2, expected_value="profile"))

    def test_comparison_types(self, config):
        assert_test_success(value_count(config, "servers[*]", 1, comparison_type="greater_equal"))
        assert_test_failed(value_count(config, "servers[*]", 2, comparison_type="greater"))

    def test_zero_asserts_absence(self, config):
        assert_test_success(value_count(config, "display.font.weight", 0))
        assert_test_failed(value_count(config, "display.font.size", 0))
        assert_test_success(value_count(config, "servers[*].port", 0, expected_value=443))

    def test_empty_file_counts_zero(self, tmp_path):
        path = tmp_path / "empty.yaml"
        path.write_text("", encoding="utf-8")
        assert_test_success(value_count(path, "a", 0))

    def test_absence_in_missing_file_is_error(self, tmp_path):
        result = value_count(tmp_path / "missing.yaml", "a", 0)
        assert_test_error(result)
        assert "does not exist" in " ".join(result.details)

    def test_corrupt_is_error(self, bad_yaml):
        assert_test_error(value_count(bad_yaml, "a", 0))

    @pytest.mark.parametrize(("expected_count", "comparison_type"), [(-1, "equals"), (1, "about")])
    def test_bad_parameters_are_errors(self, config, expected_count, comparison_type):
        assert_test_error(value_count(config, "servers[*]", expected_count, comparison_type=comparison_type))

    def test_glob_errors(self, tmp_path):
        assert_test_error(value_count(tmp_path / "*.yaml", "a", 0))
        for name in ("a.yaml", "b.yaml"):
            (tmp_path / name).write_text("a: 1\n", encoding="utf-8")
        assert_test_error(value_count(tmp_path / "*.yaml", "a", 0))


# ============================================================================
# ordered comparisons, values_compare
# ============================================================================

ValuesCompare = yaml_tf.values_compare._test_class

STATE = """\
session:
  opened: 2026-03-01T10:00:00Z
  closed: 2026-03-01T10:00:30Z
  pages: 4
  saved: "5"
history: [1, 2]
"""


def values_compare(dst, key_path, other_key_path, **kwargs):
    parameter = yaml_tf.values_compare._parameter_class(
        dst=str(dst), key_path=key_path, other_key_path=other_key_path, **kwargs
    )
    return ValuesCompare(name="t", parameter=parameter).test()


@pytest.fixture
def state(tmp_path):
    path = tmp_path / "state.yaml"
    path.write_text(STATE, encoding="utf-8")
    return path


class TestOrderedComparison:
    def test_value_matches_greater_on_a_yaml_timestamp(self, state):
        assert_test_success(value_matches(state, "session.closed", "2026-03-01T10:00:00Z", comparison_type="greater"))
        assert_test_failed(value_matches(state, "session.opened", "2026-03-01T10:00:00Z", comparison_type="greater"))

    def test_value_matches_number_tolerance(self, state):
        assert_test_success(value_matches(state, "session.pages", 5, tolerance=1))
        assert_test_failed(value_matches(state, "session.pages", 6, tolerance=1))

    def test_value_matches_ordered_with_regex_is_error(self, state):
        assert_test_error(value_matches(state, "session.pages", "4", regex_match=True, comparison_type="less"))

    def test_values_compare(self, state):
        assert_test_success(values_compare(state, "session.opened", "session.closed", comparison_type="less"))
        assert_test_success(values_compare(state, "session.closed", "session.opened", offset=30))
        assert_test_success(values_compare(state, "session.saved", "session.pages", offset=1))
        assert_test_failed(values_compare(state, "session.closed", "session.opened", tolerance=10))

    def test_values_compare_missing_ambiguous_and_uninterpretable(self, state):
        assert_test_failed(values_compare(state, "session.missing", "session.pages"))
        assert_test_error(values_compare(state, "history", "session.pages"))
        assert_test_error(values_compare(state, "session.*", "session.pages"))
        assert_test_error(values_compare(state, "session.pages", "session.opened"))  # number vs timestamp
