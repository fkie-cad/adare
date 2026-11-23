"""Unit tests for plist testfunctions (XML and binary property lists)."""

import datetime
import importlib.util
import plistlib
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

plist_tf = import_module_from_pyfile(PROJECT_ROOT / "appdata" / "testfunctions" / "plist" / "plist.py")

ContainsKey = plist_tf.contains_key._test_class
ContainsKeyParameter = plist_tf.contains_key._parameter_class
ValueMatches = plist_tf.value_matches._test_class
ValueMatchesParameter = plist_tf.value_matches._parameter_class
ValueCount = plist_tf.value_count._test_class
ValueCountParameter = plist_tf.value_count._parameter_class

helpers_path = Path(__file__).parent / "helpers.py"
spec = importlib.util.spec_from_file_location("helpers", helpers_path)
helpers = importlib.util.module_from_spec(spec)
spec.loader.exec_module(helpers)

assert_test_success = helpers.assert_test_success
assert_test_failed = helpers.assert_test_failed
assert_test_error = helpers.assert_test_error

DATA = {
    "com.example.lastVersion": "2.4.1",
    "com.example.lastLaunch": datetime.datetime(2024, 1, 15, 10, 30, 0),
    "token": b"\x0a\x1b\xff",
    "window": {"width": 1280, "height": 800, "fullscreen": False},
    "recent": [
        {"name": "report.txt", "pinned": True},
        {"name": "notes.txt", "pinned": False},
    ],
    "ratio": 1.5,
}


def contains_key(dst, key_path):
    return ContainsKey(name="t", parameter=ContainsKeyParameter(dst=str(dst), key_path=key_path)).test()


def value_matches(dst, key_path, expected_value, **kwargs):
    parameter = ValueMatchesParameter(dst=str(dst), key_path=key_path, expected_value=expected_value, **kwargs)
    return ValueMatches(name="t", parameter=parameter).test()


def value_count(dst, key_path, expected_count, **kwargs):
    parameter = ValueCountParameter(dst=str(dst), key_path=key_path, expected_count=expected_count, **kwargs)
    return ValueCount(name="t", parameter=parameter).test()


@pytest.fixture(params=[plistlib.FMT_XML, plistlib.FMT_BINARY], ids=["xml", "binary"])
def plist_file(request, tmp_path):
    path = tmp_path / "com.example.app.plist"
    path.write_bytes(plistlib.dumps(DATA, fmt=request.param))
    return path


@pytest.fixture
def bad_plist(tmp_path):
    path = tmp_path / "bad.plist"
    path.write_bytes(b'<?xml version="1.0"?><plist version="1.0"><dict><key>a</key>')
    return path


# ============================================================================
# contains_key
# ============================================================================


class TestContainsKey:
    def test_nested_key(self, plist_file):
        result = contains_key(plist_file, "window.width")
        assert_test_success(result)
        assert "1280" in result.details[0]

    def test_dotted_key_in_brackets(self, plist_file):
        assert_test_success(contains_key(plist_file, "['com.example.lastVersion']"))

    def test_dotted_key_without_brackets_fails(self, plist_file):
        assert_test_failed(contains_key(plist_file, "com.example.lastVersion"))

    def test_missing_key_fails(self, plist_file):
        result = contains_key(plist_file, "window.depth")
        assert_test_failed(result)
        assert "does not exist" in result.details[0]

    def test_array_index(self, plist_file):
        assert_test_success(contains_key(plist_file, "recent[-1].name"))
        assert_test_failed(contains_key(plist_file, "recent[5].name"))

    def test_top_level_array(self, tmp_path):
        path = tmp_path / "list.plist"
        path.write_bytes(plistlib.dumps([{"id": 1}, {"id": 2}], fmt=plistlib.FMT_BINARY))
        assert_test_success(contains_key(path, "[1].id"))

    def test_missing_file_is_error(self, tmp_path):
        result = contains_key(tmp_path / "missing.plist", "a")
        assert_test_error(result)
        assert "does not exist" in " ".join(result.details)

    def test_corrupt_xml_is_error(self, bad_plist):
        result = contains_key(bad_plist, "a")
        assert_test_error(result)
        assert "Invalid plist" in " ".join(result.details)

    @pytest.mark.parametrize(
        "content",
        [
            b"bplist00 truncated",
            b"",
            b"not a plist at all",
            b'<?xml version="1.0"?><plist version="1.0"><dict><key>a</key><integer>x</integer></dict></plist>',
            b'<?xml version="1.0"?><plist version="1.0"><dict><key>a</key><date>soon</date></dict></plist>',
            b'<?xml version="1.0" encoding="no-such-codec"?><plist version="1.0"><string>a</string></plist>',
        ],
        ids=["binary", "empty", "text", "bad-integer", "bad-date", "unknown-encoding"],
    )
    def test_invalid_content_is_error(self, tmp_path, content):
        path = tmp_path / "bad.plist"
        path.write_bytes(content)
        assert_test_error(contains_key(path, "a"))

    def test_glob_without_match_is_error(self, tmp_path):
        assert_test_error(contains_key(tmp_path / "*.plist", "a"))

    def test_ambiguous_glob_is_error(self, tmp_path):
        for name in ("a.plist", "b.plist"):
            (tmp_path / name).write_bytes(plistlib.dumps(DATA))
        assert_test_error(contains_key(tmp_path / "*.plist", "window"))

    def test_glob_with_one_match(self, plist_file):
        assert_test_success(contains_key(plist_file.parent / "*.plist", "window"))

    def test_member_of_zip_archive(self, tmp_path):
        archive = tmp_path / "backup.zip"
        with zipfile.ZipFile(archive, "w") as zf:
            zf.writestr("prefs/com.example.app.plist", plistlib.dumps(DATA, fmt=plistlib.FMT_BINARY))
        assert_test_success(contains_key(f"{archive}!/prefs/com.example.app.plist", "window.height"))


# ============================================================================
# value_matches
# ============================================================================


class TestValueMatches:
    def test_string_in_dotted_key(self, plist_file):
        assert_test_success(value_matches(plist_file, "['com.example.lastVersion']", "2.4.1"))

    def test_mismatch_fails(self, plist_file):
        result = value_matches(plist_file, "['com.example.lastVersion']", "2.5.0")
        assert_test_failed(result)
        assert "2.4.1" in result.details[0]

    def test_types_are_kept(self, plist_file):
        assert_test_success(value_matches(plist_file, "window.width", 1280))
        assert_test_failed(value_matches(plist_file, "window.width", "1280"))
        assert_test_success(value_matches(plist_file, "window.fullscreen", False))
        assert_test_success(value_matches(plist_file, "ratio", 1.5))

    def test_date_compares_as_iso_string(self, plist_file):
        assert_test_success(value_matches(plist_file, "['com.example.lastLaunch']", "2024-01-15T10:30:00"))
        assert_test_success(
            value_matches(plist_file, "['com.example.lastLaunch']", r"^2024-01-15T10:\d\d", regex_match=True)
        )

    def test_data_compares_as_hex(self, plist_file):
        assert_test_success(value_matches(plist_file, "token", "0a1bff"))
        assert_test_failed(value_matches(plist_file, "token", "0A1BFF"))

    def test_wildcard_any_and_all(self, plist_file):
        assert_test_success(value_matches(plist_file, "recent[*].pinned", True))
        assert_test_failed(value_matches(plist_file, "recent[*].pinned", True, wildcard_mode="all"))
        assert_test_success(
            value_matches(plist_file, "recent[*].name", r"\.txt$", regex_match=True, wildcard_mode="all")
        )

    def test_missing_key_fails(self, plist_file):
        assert_test_failed(value_matches(plist_file, "window.depth", 1))

    def test_bad_wildcard_mode_is_error(self, plist_file):
        assert_test_error(value_matches(plist_file, "window.width", 1280, wildcard_mode="most"))

    def test_invalid_regex_is_error(self, plist_file):
        assert_test_error(value_matches(plist_file, "window.width", "[unclosed", regex_match=True))

    def test_missing_file_is_error(self, tmp_path):
        assert_test_error(value_matches(tmp_path / "missing.plist", "a", 1))

    def test_corrupt_is_error(self, bad_plist):
        assert_test_error(value_matches(bad_plist, "a", 1))

    def test_glob_errors(self, tmp_path):
        assert_test_error(value_matches(tmp_path / "*.plist", "a", 1))
        for name in ("a.plist", "b.plist"):
            (tmp_path / name).write_bytes(plistlib.dumps({"a": 1}))
        assert_test_error(value_matches(tmp_path / "*.plist", "a", 1))


# ============================================================================
# value_count
# ============================================================================


class TestValueCount:
    def test_counts_array_elements(self, plist_file):
        assert_test_success(value_count(plist_file, "recent[*]", 2))
        assert_test_failed(value_count(plist_file, "recent[*]", 3))

    def test_counts_matching_values(self, plist_file):
        assert_test_success(value_count(plist_file, "recent[*].pinned", 1, expected_value=True))
        assert_test_success(value_count(plist_file, "recent[*].name", 2, expected_value=r"\.txt$", regex_match=True))

    def test_comparison_types(self, plist_file):
        assert_test_success(value_count(plist_file, "window.*", 2, comparison_type="greater"))
        assert_test_failed(value_count(plist_file, "window.*", 3, comparison_type="less"))
        assert_test_success(value_count(plist_file, "window.*", 3, comparison_type="less_equal"))

    def test_zero_asserts_absence(self, plist_file):
        assert_test_success(value_count(plist_file, "['com.example.removed']", 0))
        assert_test_failed(value_count(plist_file, "['com.example.lastVersion']", 0))
        assert_test_success(value_count(plist_file, "recent[*].name", 0, expected_value="deleted.txt"))

    def test_absence_in_missing_file_is_error(self, tmp_path):
        result = value_count(tmp_path / "missing.plist", "a", 0)
        assert_test_error(result)
        assert "does not exist" in " ".join(result.details)

    def test_corrupt_is_error(self, bad_plist):
        assert_test_error(value_count(bad_plist, "a", 0))

    @pytest.mark.parametrize(("expected_count", "comparison_type"), [(-1, "equals"), (True, "equals"), (1, "about")])
    def test_bad_parameters_are_errors(self, plist_file, expected_count, comparison_type):
        assert_test_error(value_count(plist_file, "recent[*]", expected_count, comparison_type=comparison_type))

    def test_glob_errors(self, tmp_path):
        assert_test_error(value_count(tmp_path / "*.plist", "a", 0))
        for name in ("a.plist", "b.plist"):
            (tmp_path / name).write_bytes(plistlib.dumps({"a": 1}))
        assert_test_error(value_count(tmp_path / "*.plist", "a", 0))


# ============================================================================
# ordered comparisons, values_compare
# ============================================================================

ValuesCompare = plist_tf.values_compare._test_class


def values_compare(dst, key_path, other_key_path, **kwargs):
    parameter = plist_tf.values_compare._parameter_class(
        dst=str(dst), key_path=key_path, other_key_path=other_key_path, **kwargs
    )
    return ValuesCompare(name="t", parameter=parameter).test()


class TestOrderedComparison:
    def test_value_matches_date_after(self, plist_file):
        assert_test_success(
            value_matches(plist_file, "['com.example.lastLaunch']", "2024-01-01T00:00:00Z", comparison_type="greater")
        )
        assert_test_failed(
            value_matches(plist_file, "['com.example.lastLaunch']", "2024-02-01T00:00:00Z", comparison_type="greater")
        )

    def test_values_compare(self, plist_file):
        assert_test_success(values_compare(plist_file, "window.width", "window.height", comparison_type="greater"))
        assert_test_success(values_compare(plist_file, "window.width", "window.height", offset=480))
        assert_test_failed(values_compare(plist_file, "window.depth", "window.height"))
        assert_test_error(values_compare(plist_file, "recent[*].name", "window.height"))
        assert_test_error(values_compare(plist_file, "token", "window.height"))  # data is no number


# --- round 2: value_decode, values_compare with other_dst --------------------------------
from adarelib.constants import StatusEnum  # noqa: E402


def _r2_write(path, data):
    path.write_bytes(plistlib.dumps(data))
    return str(path)


def _r2_run(function, **params):
    testfunction = getattr(plist_tf, function)
    return testfunction._test_class(name='t', parameter=testfunction._parameter_class(**params)).test()


@pytest.fixture
def r2_files(tmp_path):
    before = _r2_write(tmp_path / 'before.plist', {'count': 3, 'saved': '2026-03-01T10:00:00Z', 'blob': 'eyJpZCI6IDd9'})
    after = _r2_write(tmp_path / 'after.plist', {'count': 5, 'saved': '2026-03-01T10:05:00Z', 'blob': 'eyJpZCI6IDl9'})
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
        'values_compare', dst=after, key_path='count', other_key_path='count', other_dst=str(tmp_path / 'gone.plist')
    )
    assert missing.status == StatusEnum.ERROR and 'does not exist' in missing.details[0]


def test_values_compare_other_dst_archive_member(r2_files, tmp_path):
    import zipfile as _zipfile

    before, after = r2_files
    archive = tmp_path / 'backup.zip'
    with _zipfile.ZipFile(archive, 'w') as zf:
        zf.write(before, 'state/before.plist')
    result = _r2_run(
        'values_compare',
        dst=after,
        key_path='count',
        other_key_path='count',
        other_dst=f'{archive}!/state/before.plist',
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
