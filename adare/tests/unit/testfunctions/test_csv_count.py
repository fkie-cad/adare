"""Unit tests for csv.line_count (test_csv.py is at its size budget).

Runs on the guests' Python 3.10 too (``make test-testfunctions-guest``).
"""

from pathlib import Path

import pytest

from adarelib.constants import StatusEnum
from adarelib.helper.module import import_module_from_pyfile

pytestmark = pytest.mark.unit

COLLECTIONS = Path(__file__).resolve().parents[3] / 'appdata' / 'testfunctions'
csv_module = import_module_from_pyfile(COLLECTIONS / 'csv' / 'csv.py')
LineCount = csv_module.line_count._test_class
LineCountParameter = csv_module.line_count._parameter_class

ROWS = [
    ['name', 'size', 'action'],
    ['report.txt', '10', 'Created'],
    ['report.txt', '12', 'Deleted'],
    ['notes.txt', '3', 'Deleted'],
    ['report.txt', '12', 'Deleted', 'extra'],
]


def _count(dst, variable_metadata=None, **params):
    param = LineCountParameter(dst=str(dst), **params)
    return LineCount(name='t', parameter=param, variable_metadata=variable_metadata).test()


@pytest.fixture
def timeline(create_csv_file):
    return create_csv_file('timeline.csv', ROWS)


@pytest.mark.parametrize(
    ('entry', 'count'),
    [
        (['report.txt', '12', 'Deleted'], 1),  # the 4-column row does not count
        (['notes.txt', '3', 'Deleted'], 1),
        (['report.txt', '12', 'Deleted', 'extra'], 1),
        (['absent.txt', '1', 'Created'], 0),
        (['report.txt'], 0),
    ],
)
def test_counts_matching_rows(timeline, entry, count):
    result = _count(timeline, entry=entry, expected_count=count)

    assert result.status == StatusEnum.SUCCESS, result.details
    assert result.details[0].startswith(f'{count} of 5 row(s)')


def test_placeholder_columns(timeline):
    variables = {'ANY': {'type': 'regex', 'resolved_value': '.*'}}

    result = _count(timeline, variable_metadata=variables, entry=['{{ANY}}', '{{ANY}}', 'Deleted'], expected_count=2)

    assert result.status == StatusEnum.SUCCESS, result.details


@pytest.mark.parametrize(
    ('expected_count', 'comparison_type', 'status'),
    [
        (1, 'equals', StatusEnum.SUCCESS),
        (2, 'equals', StatusEnum.FAILED),
        (0, 'greater', StatusEnum.SUCCESS),
        (1, 'greater', StatusEnum.FAILED),
        (2, 'less', StatusEnum.SUCCESS),
        (1, 'greater_equal', StatusEnum.SUCCESS),
        (0, 'less_equal', StatusEnum.FAILED),
    ],
)
def test_comparison_types(timeline, expected_count, comparison_type, status):
    result = _count(
        timeline,
        entry=['report.txt', '10', 'Created'],
        expected_count=expected_count,
        comparison_type=comparison_type,
    )

    assert result.status == status, result.details


def test_empty_file_has_no_rows(tmp_path):
    empty = tmp_path / 'empty.csv'
    empty.write_text('')

    assert _count(empty, entry=['a'], expected_count=0).status == StatusEnum.SUCCESS
    assert _count(empty, entry=['a'], expected_count=1).status == StatusEnum.FAILED


@pytest.mark.parametrize(
    'params',
    [
        {'entry': ['a'], 'expected_count': -1},
        {'entry': ['a'], 'expected_count': 'one'},
        {'entry': ['a'], 'expected_count': 1, 'comparison_type': 'roughly'},
        {'entry': 'a,b', 'expected_count': 1},
        {'entry': None, 'expected_count': 1},
    ],
)
def test_bad_parameters_are_errors(timeline, params):
    assert _count(timeline, **params).status == StatusEnum.ERROR


def test_missing_file_is_an_error(tmp_path):
    # ERROR, not FAILED: expect_to_fail inverts only SUCCESS/FAILED
    result = _count(tmp_path / 'missing.csv', entry=['a'], expected_count=0)

    assert result.status == StatusEnum.ERROR
    assert 'does not exist' in result.details[0]


@pytest.mark.parametrize('pattern', ['nothing*.csv', 'a*.csv'])
def test_glob_without_unique_match_is_an_error(tmp_path, pattern):
    (tmp_path / 'a1.csv').write_text('a\n')
    (tmp_path / 'a2.csv').write_text('a\n')

    assert _count(tmp_path / pattern, entry=['a'], expected_count=1).status == StatusEnum.ERROR


def test_undecodable_file_is_an_error(tmp_path):
    bad = tmp_path / 'bad.csv'
    bad.write_bytes(b'a,b\n\xff\xfe\xfa,\x80\n')

    result = _count(bad, entry=['a', 'b'], expected_count=1, comparison_type='greater_equal')

    assert result.status == StatusEnum.ERROR, result.details


def test_csv_parse_error_is_an_error(timeline, monkeypatch):
    def broken_reader(*args, **kwargs):
        raise csv_module.csv.Error('line contains NUL')

    monkeypatch.setattr(csv_module.csv, 'reader', broken_reader)

    result = _count(timeline, entry=['a'], expected_count=0)

    assert result.status == StatusEnum.ERROR
    assert 'CSV parsing error' in result.details[0]
