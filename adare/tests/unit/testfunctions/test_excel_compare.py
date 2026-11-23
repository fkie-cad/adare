"""Ordered comparisons in excel.cell_value_matches (test_excel.py is at its size budget).

Runs on the guests' Python 3.10 too (``make test-testfunctions-guest``).
"""

import datetime
from pathlib import Path

import pytest

from adarelib.constants import StatusEnum
from adarelib.helper.module import import_module_from_pyfile

pytestmark = pytest.mark.unit

COLLECTIONS = Path(__file__).resolve().parents[3] / 'appdata' / 'testfunctions'
excel_module = import_module_from_pyfile(COLLECTIONS / 'excel' / 'excel.py')
CellValueMatches = excel_module.cell_value_matches._test_class
CellValueMatchesParameter = excel_module.cell_value_matches._parameter_class


@pytest.fixture
def workbook(tmp_path):
    openpyxl = pytest.importorskip('openpyxl')
    book = openpyxl.Workbook()
    sheet = book.active
    sheet.append(['item', 'amount', 'when'])
    sheet.append(['rent', 1500, datetime.datetime(2026, 3, 1, 10, 0, 0)])
    sheet.append(['note', 'n/a', 'later'])
    path = tmp_path / 'budget.xlsx'
    book.save(path)
    return str(path)


def _cell(dst, row, column, expected_value, **params):
    parameter = CellValueMatchesParameter(dst=dst, row=row, column=column, expected_value=expected_value, **params)
    return CellValueMatches(name='t', parameter=parameter).test()


def _assert(result, status):
    assert result.status == status, f'{result.status}: {result.details}'


@pytest.mark.parametrize(
    ('row', 'column', 'expected_value', 'params', 'status'),
    [
        (1, 1, 1000, {'comparison_type': 'greater'}, StatusEnum.SUCCESS),
        (1, 1, 1500, {'value_type': 'number'}, StatusEnum.SUCCESS),  # '1500' or '1500.0' as read
        (1, 1, 1490, {'tolerance': 5}, StatusEnum.FAILED),
        (1, 2, '2026-03-01T09:00:00Z', {'comparison_type': 'greater'}, StatusEnum.SUCCESS),
        (1, 2, '2026-03-01T10:00:00Z', {'comparison_type': 'not_equals'}, StatusEnum.FAILED),
        (2, 1, 1, {'comparison_type': 'greater'}, StatusEnum.ERROR),  # 'n/a' is no number
        (2, 2, '2026-03-01', {'comparison_type': 'greater'}, StatusEnum.ERROR),
        (1, 1, '1', {'comparison_type': 'greater', 'regex_match': True}, StatusEnum.ERROR),
        (1, 1, 1, {'comparison_type': 'bigger'}, StatusEnum.ERROR),
    ],
)
def test_cell_value_ordered(workbook, row, column, expected_value, params, status):
    _assert(_cell(workbook, row, column, expected_value, **params), status)


def test_cell_value_default_behaviour_unchanged(workbook):
    _assert(_cell(workbook, 0, 0, 'item'), StatusEnum.SUCCESS)
    _assert(_cell(workbook, 0, 0, 'ite', regex_match=True), StatusEnum.SUCCESS)
    _assert(_cell(workbook, 0, 0, 'other'), StatusEnum.FAILED)
