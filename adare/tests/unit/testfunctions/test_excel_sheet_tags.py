"""excel.sheet_exists with a !re tag in ``sheet`` (test_excel.py is at its size budget).

Runs on the guests' Python 3.10 too (``make test-testfunctions-guest``).
"""

from pathlib import Path

import pytest

from adarelib.constants import StatusEnum
from adarelib.helper.module import import_module_from_pyfile

pytestmark = pytest.mark.unit

COLLECTIONS = Path(__file__).resolve().parents[3] / 'appdata' / 'testfunctions'
excel_module = import_module_from_pyfile(COLLECTIONS / 'excel' / 'excel.py')
SheetExists = excel_module.sheet_exists._test_class
SheetExistsParameter = excel_module.sheet_exists._parameter_class


def _sheet_exists(dst, pattern):
    """A !re tag arrives as a {{placeholder}} with regex metadata."""
    return SheetExists(
        name='t',
        parameter=SheetExistsParameter(dst=str(dst), sheet='{{SHEET_RE}}'),
        variable_metadata={'SHEET_RE': {'type': 'regex', 'resolved_value': pattern}},
    ).test()


def test_re_tag_matches_a_sheet_name(create_excel_file):
    workbook = create_excel_file('test.xlsx', {'Sheet1': [['A'], ['1']], 'Report 2025': [['B'], ['2']]})
    assert _sheet_exists(workbook, r'Report \d{4}$').status == StatusEnum.SUCCESS


def test_re_tag_matching_no_sheet_fails(create_excel_file):
    """It used to be compared as plain text and fail silently; now it is matched and named."""
    workbook = create_excel_file('test.xlsx', {'Sheet1': [['A'], ['1']]})
    result = _sheet_exists(workbook, r'Report \d{4}$')
    assert result.status == StatusEnum.FAILED
    assert 'no sheet matches' in result.details[0]


def test_re_tag_with_an_invalid_regex_is_an_error(create_excel_file):
    workbook = create_excel_file('test.xlsx', {'Sheet1': [['A'], ['1']]})
    assert _sheet_exists(workbook, 'Report [').status == StatusEnum.ERROR
