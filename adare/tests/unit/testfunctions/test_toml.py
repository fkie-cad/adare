"""Unit tests for TOML testfunctions."""

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

toml_tf = import_module_from_pyfile(PROJECT_ROOT / "appdata" / "testfunctions" / "toml" / "toml.py")

ContainsKey = toml_tf.contains_key._test_class
ContainsKeyParameter = toml_tf.contains_key._parameter_class
ValueMatches = toml_tf.value_matches._test_class
ValueMatchesParameter = toml_tf.value_matches._parameter_class
ValueCount = toml_tf.value_count._test_class
ValueCountParameter = toml_tf.value_count._parameter_class

helpers_path = Path(__file__).parent / "helpers.py"
spec = importlib.util.spec_from_file_location("helpers", helpers_path)
helpers = importlib.util.module_from_spec(spec)
spec.loader.exec_module(helpers)

assert_test_success = helpers.assert_test_success
assert_test_failed = helpers.assert_test_failed
assert_test_error = helpers.assert_test_error

SETTINGS = """\
title = "Example"
installed = 2024-01-15
alarm = 07:32:00
local = 2024-01-15T10:30:00
updated = 1979-05-27T07:32:00-08:00
synced = 2024-01-15T10:30:00Z
ports = [8080, 9090]

[server]
host = "a.example.test"
port = 8080
enabled = true

["app.window"]
width = 1280

[[items]]
name = "Example Entry"
size = 3

[[items]]
name = "Other Entry"
size = 5
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
def settings(tmp_path):
    path = tmp_path / "settings.toml"
    path.write_text(SETTINGS, encoding="utf-8")
    return path


@pytest.fixture
def bad_toml(tmp_path):
    path = tmp_path / "bad.toml"
    path.write_text("[server\nport = 1\n", encoding="utf-8")
    return path


def test_module_uses_a_toml_parser_not_itself():
    assert hasattr(toml_tf.tomllib, "TOMLDecodeError")
    assert toml_tf.tomllib.__name__ in ("tomllib", "tomli")


# ============================================================================
# contains_key
# ============================================================================


class TestContainsKey:
    def test_table_key(self, settings):
        result = contains_key(settings, "server.port")
        assert_test_success(result)
        assert "8080" in result.details[0]

    def test_quoted_table_name(self, settings):
        assert_test_success(contains_key(settings, "['app.window'].width"))

    def test_array_of_tables(self, settings):
        assert_test_success(contains_key(settings, "items[*].name"))
        assert_test_success(contains_key(settings, "items[-1].size"))
        assert_test_failed(contains_key(settings, "items[2].name"))

    def test_missing_key_fails(self, settings):
        result = contains_key(settings, "server.user")
        assert_test_failed(result)
        assert "does not exist" in result.details[0]

    def test_missing_file_is_error(self, tmp_path):
        result = contains_key(tmp_path / "missing.toml", "a")
        assert_test_error(result)
        assert "does not exist" in " ".join(result.details)

    def test_corrupt_is_error(self, bad_toml):
        result = contains_key(bad_toml, "server")
        assert_test_error(result)
        assert "Invalid TOML" in " ".join(result.details)

    @pytest.mark.parametrize(
        "content",
        ["a = 1\na = 2\n", "d = 2024-02-30\n", "t = 25:00:00\n", "a = \n"],
        ids=["duplicate-key", "impossible-date", "impossible-time", "missing-value"],
    )
    def test_invalid_content_is_error(self, tmp_path, content):
        path = tmp_path / "bad.toml"
        path.write_text(content, encoding="utf-8")
        assert_test_error(contains_key(path, "a"))

    def test_undecodable_bytes_are_error(self, tmp_path):
        path = tmp_path / "bad.toml"
        path.write_bytes(b'a = "\xff"\n')
        assert_test_error(contains_key(path, "a"))

    def test_glob_errors(self, tmp_path):
        assert_test_error(contains_key(tmp_path / "*.toml", "a"))
        for name in ("a.toml", "b.toml"):
            (tmp_path / name).write_text("a = 1\n", encoding="utf-8")
        assert_test_error(contains_key(tmp_path / "*.toml", "a"))

    def test_member_of_zip_archive(self, tmp_path):
        archive = tmp_path / "a.zip"
        with zipfile.ZipFile(archive, "w") as zf:
            zf.writestr("x.toml", SETTINGS)
        assert_test_success(contains_key(f"{archive}!/x.toml", "items[0].name"))


# ============================================================================
# value_matches
# ============================================================================


class TestValueMatches:
    def test_string_value(self, settings):
        assert_test_success(value_matches(settings, "server.host", "a.example.test"))

    def test_mismatch_fails(self, settings):
        result = value_matches(settings, "server.port", 9090)
        assert_test_failed(result)
        assert "8080" in result.details[0]

    def test_types_are_kept(self, settings):
        assert_test_failed(value_matches(settings, "server.port", "8080"))
        assert_test_success(value_matches(settings, "server.enabled", True))

    @pytest.mark.parametrize(
        ("key_path", "expected"),
        [
            ("installed", "2024-01-15"),
            ("alarm", "07:32:00"),
            ("local", "2024-01-15T10:30:00"),
            ("updated", "1979-05-27T07:32:00-08:00"),
            ("synced", "2024-01-15T10:30:00+00:00"),
        ],
    )
    def test_dates_and_times_compare_as_iso_strings(self, settings, key_path, expected):
        assert_test_success(value_matches(settings, key_path, expected))

    def test_array_of_tables_wildcard(self, settings):
        assert_test_success(value_matches(settings, "items[*].name", "Other Entry"))
        assert_test_failed(value_matches(settings, "items[*].name", "Other Entry", wildcard_mode="all"))
        assert_test_success(value_matches(settings, "items[*].name", r"Entry$", regex_match=True, wildcard_mode="all"))

    def test_array_value_compares_elements(self, settings):
        assert_test_success(value_matches(settings, "ports", 9090))
        assert_test_failed(value_matches(settings, "ports", 443))

    def test_missing_key_fails(self, settings):
        assert_test_failed(value_matches(settings, "server.user", "x"))

    def test_bad_wildcard_mode_is_error(self, settings):
        assert_test_error(value_matches(settings, "server.port", 8080, wildcard_mode="most"))

    def test_invalid_regex_is_error(self, settings):
        assert_test_error(value_matches(settings, "server.host", "[unclosed", regex_match=True))

    def test_missing_file_is_error(self, tmp_path):
        assert_test_error(value_matches(tmp_path / "missing.toml", "a", 1))

    def test_corrupt_is_error(self, bad_toml):
        assert_test_error(value_matches(bad_toml, "server.port", 1))

    def test_glob_errors(self, tmp_path):
        assert_test_error(value_matches(tmp_path / "*.toml", "a", 1))
        for name in ("a.toml", "b.toml"):
            (tmp_path / name).write_text("a = 1\n", encoding="utf-8")
        assert_test_error(value_matches(tmp_path / "*.toml", "a", 1))


# ============================================================================
# value_count
# ============================================================================


class TestValueCount:
    def test_counts_array_of_tables(self, settings):
        assert_test_success(value_count(settings, "items[*]", 2))
        assert_test_failed(value_count(settings, "items[*]", 3))

    def test_counts_matching_values(self, settings):
        assert_test_success(value_count(settings, "items[*].size", 1, expected_value=5))
        assert_test_success(value_count(settings, "ports", 2, expected_value=r"^\d{4}$", regex_match=True))

    def test_comparison_types(self, settings):
        assert_test_success(value_count(settings, "server.*", 3, comparison_type="equals"))
        assert_test_success(value_count(settings, "server.*", 4, comparison_type="less"))
        assert_test_failed(value_count(settings, "server.*", 3, comparison_type="greater"))

    def test_zero_asserts_absence(self, settings):
        assert_test_success(value_count(settings, "server.user", 0))
        assert_test_failed(value_count(settings, "server.port", 0))
        assert_test_success(value_count(settings, "items[*].name", 0, expected_value="Removed Entry"))

    def test_absence_in_missing_file_is_error(self, tmp_path):
        result = value_count(tmp_path / "missing.toml", "a", 0)
        assert_test_error(result)
        assert "does not exist" in " ".join(result.details)

    def test_corrupt_is_error(self, bad_toml):
        assert_test_error(value_count(bad_toml, "a", 0))

    @pytest.mark.parametrize(("expected_count", "comparison_type"), [(-1, "equals"), (1, "about")])
    def test_bad_parameters_are_errors(self, settings, expected_count, comparison_type):
        assert_test_error(value_count(settings, "items[*]", expected_count, comparison_type=comparison_type))

    def test_glob_errors(self, tmp_path):
        assert_test_error(value_count(tmp_path / "*.toml", "a", 0))
        for name in ("a.toml", "b.toml"):
            (tmp_path / name).write_text("a = 1\n", encoding="utf-8")
        assert_test_error(value_count(tmp_path / "*.toml", "a", 0))
