"""Sheet pairing and whole-workbook report helpers of workbook.py (the excel collection's shared checks)."""

import pytest

from adarelib.testset.workbook import compare_files_failure_details, match_sheets, sheet_set_differences

pytestmark = pytest.mark.unit


@pytest.mark.parametrize(
    ('mode', 'actual', 'reference', 'specific', 'expected'),
    [
        ('by_name', ['a', 'x'], ['a', 'b'], None, (['b'], ['x'])),
        ('by_index', ['a'], ['a', 'b', 'c'], None, (['b', 'c'], [])),
        ('by_index', ['a', 'b', 'c'], ['a'], None, ([], ['b', 'c'])),
        ('specific', ['a', 'x'], ['a', 'b'], ['a', 'b'], (['b'], [])),
        ('specific', ['a'], ['a'], None, ([], [])),
    ],
)
def test_sheet_set_differences(mode, actual, reference, specific, expected):
    matches = match_sheets(actual, reference, mode, specific)

    assert sheet_set_differences(mode, actual, reference, specific, matches) == expected


def test_failure_details_empty_when_nothing_failed():
    assert compare_files_failure_details('by_name', ['a'], ['a'], [], [], False, False, []) == []


def test_failure_details_ignore_allowed_sheet_differences():
    assert compare_files_failure_details('by_name', ['a', 'x'], ['a', 'b'], ['b'], ['x'], True, True, []) == []


def test_failure_details_report_structure_and_row_differences():
    details = compare_files_failure_details(
        'by_name', ['a', 'x'], ['a', 'b'], ['b'], ['x'], False, False, [{'sheet': 'a', 'details': ['row 1 differs']}]
    )

    assert details == [
        'Excel file comparison failed: 1 missing sheet(s), 1 extra sheet(s), 1 sheet(s) with row differences',
        'Actual: 2 sheets, Reference: 2 sheets',
        'Sheet matching mode: by_name',
        '',
        "Missing sheets (in reference but not in actual): ['b']",
        "Extra sheets (in actual but not in reference): ['x']",
        '',
        'Sheet comparison failures:',
        '',
        "Sheet 'a':",
        '  row 1 differs',
    ]
