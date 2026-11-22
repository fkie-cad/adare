"""Shared comparison helpers used by the csv/excel/json/jsonl/xml collections."""

import pytest

from adarelib.constants import StatusEnum
from adarelib.testset.compare import (
    compare_row_sequences,
    compare_row_sets,
    extract_columns,
    format_diff_report,
    get_nested_value,
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
