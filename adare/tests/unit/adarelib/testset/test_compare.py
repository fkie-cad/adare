"""Shared comparison helpers used by the csv/excel/json/jsonl/xml collections."""

import pytest

from adarelib.constants import StatusEnum
from adarelib.testset.compare import (
    compare_row_sequences,
    compare_row_sets,
    extract_columns,
    format_diff_report,
    get_nested_value,
    regex_expected_problem,
    regex_pattern_problem,
    rows_regex_problem,
)

pytestmark = pytest.mark.unit


class _PlainCtx:
    def has_placeholders(self, text):
        return False


def test_extract_columns_ignores_out_of_range_indices():
    assert extract_columns(['a', 'b'], [0, 5]) == ['a']
    assert extract_columns(['a', 'b'], None) == ['a', 'b']


def test_get_nested_value_walks_dicts_and_lists():
    data = {'user': {'tags': ['x', 'y']}}
    assert get_nested_value(data, 'user.tags') == (['x', 'y'], True)
    assert get_nested_value(data, 'user.missing')[1] is False


def test_diff_report_carries_the_collection_label():
    report = format_diff_report([(1, ['a'])], [], [], actual_count=0, reference_count=1, columns=None, label='Excel')
    assert report[0] == 'Excel comparison failed: 1 missing row'


@pytest.mark.parametrize('compare', [compare_row_sets, compare_row_sequences])
def test_row_comparisons(compare):
    ctx = _PlainCtx()
    same = compare(ctx, [['a', '1']], [['a', '1']], None, False, False)
    assert same.status == StatusEnum.SUCCESS

    differs = compare(ctx, [['a', '1']], [['a', '2']], None, False, False, label='Excel')
    assert differs.status == StatusEnum.FAILED
    assert differs.details[0].startswith('Excel comparison failed')


# --- key paths -----------------------------------------------------------------

from adarelib.testset.compare import parse_key_path, resolve_key_path  # noqa: E402

_DATA = {
    'users': [{'name': 'a', 'tags': ['x', 'y']}, {'name': 'b', 'tags': []}],
    'config': {'one': {'enabled': True}, 'two': {'enabled': False}},
    'com.example.key': 5,
    'odd[key]': 3,
    'matrix': [[1, 2], [3]],
}


@pytest.mark.parametrize(
    ('path', 'expected'),
    [
        ('users[*].name', ['a', 'b']),
        ('config.*.enabled', [True, False]),
        ('users[0].name', ['a']),
        ('users[-1].name', ['b']),
        ('users[2].name', []),
        ('users[0].tags[1]', ['y']),
        ('matrix[0][1]', [2]),
        ('matrix[*][0]', [1, 3]),
        ("['com.example.key']", [5]),
        ('["com.example.key"]', [5]),
        ('com.example.key', []),
        ('odd[key]', [3]),  # not index syntax: part of the key
        ('users[x]', []),
        ('users', [_DATA['users']]),
        ('missing', []),
    ],
)
def test_resolve_key_path(path, expected):
    assert resolve_key_path(_DATA, path) == expected


def test_top_level_array():
    rows = [{'id': 1}, {'id': 2}]
    assert resolve_key_path(rows, '[*].id') == [1, 2]
    assert resolve_key_path(rows, '[1].id') == [2]
    assert resolve_key_path(rows, 'id') == []


def test_quoted_key_inside_a_path():
    data = {'prefs': {'a.b.c': {'v': 1}}}
    assert resolve_key_path(data, "prefs['a.b.c'].v") == [1]
    assert parse_key_path("prefs['a.b.c'].v") == [('key', 'prefs'), ('key', 'a.b.c'), ('key', 'v')]


def test_get_nested_value_keeps_its_return_contract():
    assert get_nested_value(_DATA, 'users[0].name') == ('a', True)
    assert get_nested_value(_DATA, 'users[*].name') == (['a', 'b'], True)
    assert get_nested_value(_DATA, 'nope') == ([], False)


def test_literal_key_with_brackets_wins_like_before():
    data = {'files[0]': 'literal', 'files': ['element'], 'm[*]': 1}
    assert resolve_key_path(data, 'files[0]') == ['literal']
    assert resolve_key_path({'files': ['element']}, 'files[0]') == ['element']
    assert resolve_key_path(data, 'm[*]') == [1]
    assert get_nested_value({'files[0]': 'a'}, 'files[0]') == ('a', True)


class _MetaCtx:
    """The placeholder part of a testfunction context."""

    def __init__(self, metadata=None):
        self._metadata = metadata or {}

    def has_placeholders(self, text):
        return '{{' in text and '}}' in text

    def get_placeholders(self, text):
        import re

        return [m.strip() for m in re.findall(r'\{\{\s*([^}]+)\s*\}\}', text)]

    def get_placeholder_metadata(self, name):
        return self._metadata.get(name, {})


def _regex_var(pattern):
    return {'type': 'regex', 'raw_value': pattern, 'resolved_value': pattern}


def test_regex_expected_problem_flags_an_invalid_regex_match_string():
    result = regex_expected_problem(_MetaCtx(), ['ok', '[bad'], regex_match=True)

    assert result.status == StatusEnum.ERROR
    assert "'[bad'" in result.details[0]


def test_regex_expected_problem_ignores_strings_without_regex_match():
    assert regex_expected_problem(_MetaCtx(), ['[bad', 1, None, '*'], regex_match=False) is None
    assert regex_expected_problem(_MetaCtx(), ['*', 'a.*'], regex_match=True) is None


def test_regex_expected_problem_checks_regex_placeholders():
    ctx = _MetaCtx({'P': _regex_var('[bad'), 'Q': _regex_var('a{{ Z }}'), 'T': {'type': 'timestamp'}})

    assert 'invalid regular expression' in regex_expected_problem(ctx, ['{{ P }}']).details[0]
    assert "unknown variable 'Z'" in regex_expected_problem(ctx, ['{{ Q }}']).details[0]
    assert "unknown placeholder '{{ NOPE }}'" in regex_expected_problem(ctx, ['{{ NOPE }}']).details[0]
    assert regex_expected_problem(ctx, ['{{ T }}']) is None
    assert regex_expected_problem(_MetaCtx({'P': _regex_var('a+')}), ['{{ P }}']) is None


def test_regex_expected_problem_several_placeholders_only_when_asked():
    ctx = _MetaCtx({'P': _regex_var('[bad'), 'G': _regex_var('a+')})
    value = '{{ G }} and {{ P }}'

    assert regex_expected_problem(ctx, [value]) is None
    assert regex_expected_problem(ctx, [value], many_placeholders=True).status == StatusEnum.ERROR


def test_regex_pattern_problem():
    assert regex_pattern_problem('a+') is None
    assert "'*'" in regex_pattern_problem('*').details[0]


def test_rows_regex_problem_checks_every_cell_and_ignores_non_rows():
    ctx = _MetaCtx({'P': _regex_var('[bad')})

    assert rows_regex_problem(ctx, [['a', 'b'], ['c', '{{ P }}']]).status == StatusEnum.ERROR
    assert rows_regex_problem(ctx, [['a', 'b']]) is None
    assert rows_regex_problem(ctx, None) is None
    assert rows_regex_problem(ctx, ['not a row']) is None
