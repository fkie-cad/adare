"""Unit tests for excel.row_count (test_excel.py is at its size budget).

Runs on the guests' Python 3.10 too (``make test-testfunctions-guest``).
"""

from pathlib import Path

import pytest

from adarelib.constants import StatusEnum
from adarelib.helper.module import import_module_from_pyfile

pytestmark = pytest.mark.unit

COLLECTIONS = Path(__file__).resolve().parents[3] / 'appdata' / 'testfunctions'
excel_module = import_module_from_pyfile(COLLECTIONS / 'excel' / 'excel.py')
RowCount = excel_module.row_count._test_class
RowCountParameter = excel_module.row_count._parameter_class

ROWS = [
    ['name', 'size', 'action'],
    ['report.txt', '10', 'Created'],
    ['report.txt', '12', 'Deleted'],
    ['notes.txt', '3', 'Deleted'],
]


def _count(dst, variable_metadata=None, **params):
    param = RowCountParameter(dst=str(dst), **params)
    return RowCount(name='t', parameter=param, variable_metadata=variable_metadata).test()


@pytest.fixture
def workbook(create_excel_file):
    return create_excel_file('timeline.xlsx', {'Log': ROWS, 'Other': [['a', 'b'], ['a', 'b']]})


@pytest.mark.parametrize(
    ('entry', 'count'),
    [
        (['report.txt', '12', 'Deleted'], 1),
        (['notes.txt', '3', 'Deleted'], 1),
        (['absent.txt', '1', 'Created'], 0),
        (['report.txt'], 0),  # another width never matches
    ],
)
def test_counts_matching_rows(workbook, entry, count):
    result = _count(workbook, entry=entry, expected_count=count)

    assert result.status == StatusEnum.SUCCESS, result.details
    assert result.details[0].startswith(f'{count} of 4 row(s)')


def test_re_tag_entries(workbook):
    # the host turns `!re` items into regex placeholders before the test runs
    variables = {
        'regex_0_resolved': {'raw_value': 'report\\.txt', 'resolved_value': 'report\\.txt', 'type': 'regex'},
        'regex_1_resolved': {'raw_value': '1[0-9]', 'resolved_value': '1[0-9]', 'type': 'regex'},
    }
    entry = ['{{regex_0_resolved}}', '{{regex_1_resolved}}', 'Deleted']

    assert _count(workbook, variable_metadata=variables, entry=entry, expected_count=1).status == StatusEnum.SUCCESS
    entry[2] = 'Created'
    assert _count(workbook, variable_metadata=variables, entry=entry, expected_count=1).status == StatusEnum.SUCCESS
    entry[2] = 'Moved'
    assert _count(workbook, variable_metadata=variables, entry=entry, expected_count=1).status == StatusEnum.FAILED


def test_placeholder_columns(workbook):
    variables = {'ANY': {'type': 'regex', 'resolved_value': '.*'}}

    result = _count(workbook, variable_metadata=variables, entry=['{{ANY}}', '{{ANY}}', 'Deleted'], expected_count=2)

    assert result.status == StatusEnum.SUCCESS, result.details


def test_unknown_placeholder_is_an_error(workbook):
    result = _count(workbook, entry=['{{NOPE}}', '10', 'Created'], expected_count=1)

    assert result.status == StatusEnum.ERROR, result.details


def test_sheet_and_header_row(workbook):
    assert _count(workbook, entry=['a', 'b'], expected_count=2, sheet='Other').status == StatusEnum.SUCCESS
    assert _count(workbook, entry=['a', 'b'], expected_count=2, sheet=1).status == StatusEnum.SUCCESS
    # skipping the header row leaves 3 rows
    result = _count(workbook, entry=['name', 'size', 'action'], expected_count=0, header_row=1)
    assert result.status == StatusEnum.SUCCESS, result.details
    assert result.details[0].startswith('0 of 3 row(s)')


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
def test_comparison_types(workbook, expected_count, comparison_type, status):
    result = _count(
        workbook,
        entry=['report.txt', '10', 'Created'],
        expected_count=expected_count,
        comparison_type=comparison_type,
    )

    assert result.status == status, result.details


def test_mismatch_fails(workbook):
    result = _count(workbook, entry=['report.txt', '12', 'Deleted'], expected_count=0)

    assert result.status == StatusEnum.FAILED, result.details
    assert 'count 1 == 0 does not hold' in result.details[1]


@pytest.mark.parametrize('sheet', ['Nope', 7])
def test_missing_sheet_fails_like_contains_row(workbook, sheet):
    result = _count(workbook, entry=['a'], expected_count=0, sheet=sheet)

    assert result.status == StatusEnum.FAILED, result.details
    assert 'not found' in result.details[0] or 'out of range' in result.details[0]


@pytest.mark.parametrize(
    'params',
    [
        {'entry': ['a'], 'expected_count': -1},
        {'entry': ['a'], 'expected_count': 'one'},
        {'entry': ['a'], 'expected_count': 1, 'comparison_type': 'roughly'},
        {'entry': 'a,b', 'expected_count': 1},
        {'entry': None, 'expected_count': 1},
        {'entry': ['a'], 'expected_count': 1, 'header_row': -1},
        {'entry': ['a'], 'expected_count': 1, 'header_row': 'first'},
    ],
)
def test_bad_parameters_are_errors(workbook, params):
    assert _count(workbook, **params).status == StatusEnum.ERROR


def test_missing_file_is_an_error(tmp_path):
    # ERROR, not FAILED: expect_to_fail inverts only SUCCESS/FAILED
    result = _count(tmp_path / 'missing.xlsx', entry=['a'], expected_count=0)

    assert result.status == StatusEnum.ERROR
    assert 'does not exist' in result.details[0]


def test_corrupt_workbook_is_an_error(tmp_path):
    bad = tmp_path / 'bad.xlsx'
    bad.write_bytes(b'PK\x03\x04 this is not a workbook')

    assert _count(bad, entry=['a'], expected_count=0).status == StatusEnum.ERROR
