"""Unit tests for json.value_count (test_json.py is at its size budget).

Runs on the guests' Python 3.10 too (``make test-testfunctions-guest``).
"""

import json
from pathlib import Path

import pytest

from adarelib.helper.module import import_module_from_pyfile

pytestmark = pytest.mark.unit

COLLECTIONS = Path(__file__).resolve().parents[3] / 'appdata' / 'testfunctions'
json_tf_module = import_module_from_pyfile(COLLECTIONS / 'json' / 'json.py')
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
