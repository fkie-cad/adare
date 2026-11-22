"""FAILED means "the file was read and the condition does not hold"; anything else is ERROR.

``test_missing_dst_is_error.py`` covers a missing ``dst`` and globs with 0 or 2 matches. This
module covers the other ways a content test cannot answer, per collection:

- the file exists but cannot be parsed (corrupt CSV/JSON/JSONL/XML/workbook),
- the parameters are invalid (wrong type, empty list, both/neither of two options, a bad
  regex, an unknown mode, more than one placeholder where one is required),

and checks that a real mismatch on a readable file still FAILS, so the rule does not turn
every negative answer into an error. ``expect_to_fail`` inverts only SUCCESS/FAILED, so an
ERROR can never become a pass.
"""

import csv as stdlib_csv
from pathlib import Path

import pandas as pd
import pytest

from adarelib.constants import StatusEnum
from adarelib.helper.module import import_module_from_pyfile

pytestmark = pytest.mark.unit

COLLECTIONS = Path(__file__).resolve().parents[3] / 'appdata' / 'testfunctions'
VARIABLES = {'VAR1': {'type': 'string', 'resolved_value': 'value1'}}

_modules = {}


def _module(collection):
    if collection not in _modules:
        _modules[collection] = import_module_from_pyfile(COLLECTIONS / collection / f'{collection}.py')
    return _modules[collection]


def _run(dotted, variable_metadata=None, **params):
    collection, name = dotted.split('.')
    testfunction = getattr(_module(collection), name)
    test = testfunction._test_class(
        name='t', parameter=testfunction._parameter_class(**params), variable_metadata=variable_metadata
    )
    return test.test()


def _assert(result, status):
    assert result.status == status, f'expected {status.name}, got {result.status}: {result.details}'


def _workbook(path, sheets):
    with pd.ExcelWriter(path, engine='openpyxl') as writer:
        for sheet_name, rows in sheets.items():
            pd.DataFrame(rows).to_excel(writer, sheet_name=sheet_name, index=False, header=False)
    return str(path)


@pytest.fixture
def files(tmp_path):
    """One readable and one corrupt file per format."""
    paths = {
        'csv': tmp_path / 'good.csv',
        'json': tmp_path / 'good.json',
        'jsonl': tmp_path / 'good.jsonl',
        'xml': tmp_path / 'good.xml',
        'txt': tmp_path / 'good.txt',
        'bad_json': tmp_path / 'bad.json',
        'bad_jsonl': tmp_path / 'bad.jsonl',
        'bad_xml': tmp_path / 'bad.xml',
        'bad_xlsx': tmp_path / 'bad.xlsx',
        'bad_csv_bytes': tmp_path / 'bad.csv',
    }
    paths['csv'].write_text('a,b\nc,d\n')
    paths['json'].write_text('{"a": 1, "arr": [1, 2], "s": "text"}')
    paths['jsonl'].write_text('{"a": 1}\n{"a": 2}\n')
    paths['xml'].write_text('<root><item id="1">x</item><item id="2">y</item></root>')
    paths['txt'].write_text('hello world')
    paths['bad_json'].write_text('{"a": 1,')
    paths['bad_jsonl'].write_text('{"a": 1}\n{not json\n')
    paths['bad_xml'].write_text('<root><item></root>')
    paths['bad_xlsx'].write_bytes(b'PK\x03\x04 this is not a workbook')
    paths['bad_csv_bytes'].write_bytes(b'a,b\n\xff\xfe\xfa,\x80\n')
    out = {k: str(v) for k, v in paths.items()}
    out['xlsx'] = _workbook(tmp_path / 'good.xlsx', {'S': [['a', 'b'], ['c', 'd']]})
    out['other_xlsx'] = _workbook(tmp_path / 'other.xlsx', {'S': [['a', 'b'], ['x', 'y']]})
    return out


# --- corrupt file -> ERROR ------------------------------------------------------------

CORRUPT = [
    ('json.contains_key', 'bad_json', {'key_path': 'a'}),
    ('json.value_matches', 'bad_json', {'key_path': 'a', 'expected_value': 1}),
    ('json.array_contains', 'bad_json', {'array_path': 'arr', 'expected_element': 1}),
    ('jsonl.line_matches', 'bad_jsonl', {'conditions': {'a': 1}, 'skip_malformed': False}),
    ('jsonl.line_count', 'bad_jsonl', {'expected_count': 1, 'skip_malformed': False}),
    ('jsonl.value_in_any_line', 'bad_jsonl', {'key_path': 'a', 'expected_value': 1, 'skip_malformed': False}),
    ('xml.element_exists', 'bad_xml', {'xpath': './/item'}),
    ('xml.element_count', 'bad_xml', {'xpath': './/item', 'expected_count': 1}),
    ('excel.sheet_exists', 'bad_xlsx', {'sheet_name': 'S'}),
    ('excel.cell_value_matches', 'bad_xlsx', {'row': 0, 'column': 0, 'expected_value': 'a'}),
    ('excel.contains_row', 'bad_xlsx', {'entry': ['a', 'b']}),
    ('excel.validate_columns', 'bad_xlsx', {'expected_columns': ['a']}),
    ('excel.compare_rows', 'bad_xlsx', {'reference_rows': [['a', 'b']]}),
    ('csv.contains_line', 'bad_csv_bytes', {'entry': ['a', 'b']}),
]


@pytest.mark.parametrize(('dotted', 'kind', 'params'), CORRUPT, ids=[c[0] for c in CORRUPT])
def test_corrupt_file_is_an_error(files, dotted, kind, params):
    _assert(_run(dotted, dst=files[kind], **params), StatusEnum.ERROR)


@pytest.mark.parametrize('dotted', ['excel.compare_sheets', 'excel.compare_files'])
def test_corrupt_workbook_pair_is_an_error(files, dotted):
    _assert(_run(dotted, actual=files['bad_xlsx'], reference=files['xlsx']), StatusEnum.ERROR)
    _assert(_run(dotted, actual=files['xlsx'], reference=files['bad_xlsx']), StatusEnum.ERROR)


def test_corrupt_excel_reference_file_is_an_error(files):
    result = _run('excel.compare_rows', dst=files['xlsx'], reference_file=files['bad_xlsx'])

    _assert(result, StatusEnum.ERROR)
    assert 'Cannot parse reference Excel file' in result.details[0]


@pytest.mark.parametrize(
    ('dotted', 'params'),
    [
        ('csv.contains_line', {'entry': ['a', 'b']}),
        ('csv.compare_rows', {'reference_rows': [['a', 'b']]}),
        ('csv.compare_files', {}),
    ],
)
def test_csv_parse_error_is_an_error(files, monkeypatch, dotted, params):
    # Python 3.13's lenient default dialect accepts almost any text, so force the parse error.
    def broken_reader(*args, **kwargs):
        raise stdlib_csv.Error('line contains NUL')

    monkeypatch.setattr(_module('csv').csv, 'reader', broken_reader)
    if dotted == 'csv.compare_files':
        result = _run(dotted, actual=files['csv'], reference=files['csv'])
    else:
        result = _run(dotted, dst=files['csv'], **params)

    _assert(result, StatusEnum.ERROR)
    assert 'CSV parsing error' in result.details[0]


# --- invalid parameters -> ERROR ------------------------------------------------------

BAD_PARAMS = [
    ('csv.compare_rows', 'csv', {'reference_rows': 'not a list'}),
    ('csv.compare_rows', 'csv', {'reference_rows': []}),
    ('csv.compare_rows', 'csv', {'reference_rows': ['a']}),
    ('excel.validate_columns', 'xlsx', {'expected_columns': 'a'}),
    ('excel.validate_columns', 'xlsx', {'expected_columns': []}),
    ('excel.compare_rows', 'xlsx', {}),
    ('excel.compare_rows', 'xlsx', {'reference_rows': [['a', 'b']], 'reference_file': '/x.xlsx'}),
    ('excel.compare_rows', 'xlsx', {'reference_rows': []}),
    ('excel.compare_rows', 'xlsx', {'reference_rows': 'not a list'}),
    ('excel.compare_rows', 'xlsx', {'reference_rows': ['a']}),
    ('json.value_matches', 'json', {'key_path': 'a', 'expected_value': 1, 'wildcard_mode': 'some'}),
    ('json.value_matches', 'json', {'key_path': 's', 'expected_value': '[unclosed', 'regex_match': True}),
    ('jsonl.line_matches', 'jsonl', {'conditions': {'a': '[unclosed'}, 'regex_match': True}),
    ('jsonl.line_count', 'jsonl', {'expected_count': 'two'}),
    ('xml.element_text_matches', 'xml', {'xpath': './/item', 'expected_text': '[unclosed', 'regex_match': True}),
    (
        'xml.attribute_matches',
        'xml',
        {'xpath': './/item', 'attribute': 'id', 'expected_value': '[unclosed', 'regex_match': True},
    ),
    ('xml.element_count', 'xml', {'xpath': './/item', 'expected_count': 1, 'comparison_type': 'roughly'}),
    ('standard.file_content_matches_regex', 'txt', {'regex': '[unclosed'}),
    ('standard.file_hash_matches', 'txt', {'expected_hash': '0' * 64, 'hash_type': 'crc0'}),
]


@pytest.mark.parametrize(
    ('dotted', 'kind', 'params'), BAD_PARAMS, ids=[f'{c[0]}-{i}' for i, c in enumerate(BAD_PARAMS)]
)
def test_invalid_parameters_are_an_error(files, dotted, kind, params):
    _assert(_run(dotted, dst=files[kind], **params), StatusEnum.ERROR)


def test_excel_invalid_sheet_mode_is_an_error(files):
    result = _run('excel.compare_files', actual=files['xlsx'], reference=files['xlsx'], sheet_mode='by_colour')

    _assert(result, StatusEnum.ERROR)
    assert 'Invalid sheet_mode' in result.details[0]


def test_json_array_contains_needs_exactly_one_placeholder(files):
    result = _run(
        'json.array_contains',
        variable_metadata={**VARIABLES, 'VAR2': {'type': 'string', 'resolved_value': 'value2'}},
        dst=files['json'],
        array_path='arr',
        expected_element='{{VAR1}}-{{VAR2}}',
    )

    _assert(result, StatusEnum.ERROR)
    assert 'expected 1 placeholder' in result.details[0]


def test_excel_cell_value_needs_exactly_one_placeholder(files):
    result = _run(
        'excel.cell_value_matches',
        variable_metadata={**VARIABLES, 'VAR2': {'type': 'string', 'resolved_value': 'value2'}},
        dst=files['xlsx'],
        row=0,
        column=0,
        expected_value='{{VAR1}}-{{VAR2}}',
    )

    _assert(result, StatusEnum.ERROR)
    assert 'exactly one placeholder' in result.details[0]


# --- Excel: a missing sheet in the file under test is a finding, in the reference not --


@pytest.mark.parametrize(
    ('dotted', 'params'),
    [
        ('excel.cell_value_matches', {'row': 0, 'column': 0, 'expected_value': 'a', 'sheet': 'Nope'}),
        ('excel.contains_row', {'entry': ['a', 'b'], 'sheet': 'Nope'}),
        ('excel.validate_columns', {'expected_columns': ['a'], 'sheet': 'Nope'}),
        ('excel.compare_rows', {'reference_rows': [['a', 'b']], 'sheet': 7}),
    ],
)
def test_excel_missing_sheet_in_dst_fails(files, dotted, params):
    result = _run(dotted, dst=files['xlsx'], **params)

    _assert(result, StatusEnum.FAILED)
    assert 'not found' in result.details[0] or 'out of range' in result.details[0]


def test_excel_missing_actual_sheet_fails_but_missing_reference_sheet_errors(files):
    _assert(
        _run('excel.compare_sheets', actual=files['xlsx'], reference=files['xlsx'], actual_sheet='Nope'),
        StatusEnum.FAILED,
    )
    _assert(
        _run('excel.compare_sheets', actual=files['xlsx'], reference=files['xlsx'], reference_sheet='Nope'),
        StatusEnum.ERROR,
    )
    _assert(
        _run('excel.compare_rows', dst=files['xlsx'], reference_file=files['xlsx'], reference_sheet='Nope'),
        StatusEnum.ERROR,
    )


# --- empty JSONL: count it like any other file ------------------------------------------


@pytest.mark.parametrize(
    ('expected_count', 'status'), [(0, StatusEnum.SUCCESS), ({'max': 0}, StatusEnum.SUCCESS), (1, StatusEnum.FAILED)]
)
def test_jsonl_line_count_on_empty_file_counts_zero(tmp_path, expected_count, status):
    empty = tmp_path / 'empty.jsonl'
    empty.write_text('')

    result = _run('jsonl.line_count', dst=str(empty), expected_count=expected_count)

    _assert(result, status)
    assert 'Found 0 matching lines' in result.details[0]


@pytest.mark.parametrize(
    ('dotted', 'params'),
    [
        ('jsonl.line_matches', {'conditions': {'a': 1}}),
        ('jsonl.value_in_any_line', {'key_path': 'a', 'expected_value': 1}),
    ],
)
def test_jsonl_empty_file_still_fails_where_a_line_is_required(tmp_path, dotted, params):
    empty = tmp_path / 'empty.jsonl'
    empty.write_text('')

    _assert(_run(dotted, dst=str(empty), **params), StatusEnum.FAILED)


# --- a real mismatch on a readable file stays FAILED ------------------------------------

MISMATCH = [
    ('csv.contains_line', 'csv', {'entry': ['x', 'y']}),
    ('csv.compare_rows', 'csv', {'reference_rows': [['a', 'b'], ['x', 'y']]}),
    ('excel.sheet_exists', 'xlsx', {'sheet_name': 'Other'}),
    ('excel.cell_value_matches', 'xlsx', {'row': 0, 'column': 0, 'expected_value': 'z'}),
    ('excel.contains_row', 'xlsx', {'entry': ['x', 'y']}),
    ('excel.validate_columns', 'xlsx', {'expected_columns': ['x', 'y']}),
    ('excel.compare_rows', 'xlsx', {'reference_rows': [['a', 'b'], ['x', 'y']]}),
    ('json.contains_key', 'json', {'key_path': 'missing'}),
    ('json.value_matches', 'json', {'key_path': 'a', 'expected_value': 2}),
    ('json.array_contains', 'json', {'array_path': 'arr', 'expected_element': 9}),
    ('jsonl.line_matches', 'jsonl', {'conditions': {'a': 9}}),
    ('jsonl.line_count', 'jsonl', {'expected_count': 5}),
    ('jsonl.value_in_any_line', 'jsonl', {'key_path': 'a', 'expected_value': 9}),
    ('xml.element_exists', 'xml', {'xpath': './/missing'}),
    ('xml.element_text_matches', 'xml', {'xpath': './/item', 'expected_text': 'z'}),
    ('xml.attribute_matches', 'xml', {'xpath': './/item', 'attribute': 'id', 'expected_value': '9'}),
    ('xml.element_count', 'xml', {'xpath': './/item', 'expected_count': 5}),
    ('standard.file_content_contains', 'txt', {'content': 'absent'}),
    ('standard.file_content_equals', 'txt', {'content': 'other text'}),
    ('standard.file_content_matches_regex', 'txt', {'regex': '^absent$'}),
    ('standard.file_hash_matches', 'txt', {'expected_hash': '0' * 64}),
]


@pytest.mark.parametrize(('dotted', 'kind', 'params'), MISMATCH, ids=[c[0] for c in MISMATCH])
def test_real_mismatch_still_fails(files, dotted, kind, params):
    _assert(_run(dotted, dst=files[kind], **params), StatusEnum.FAILED)


@pytest.mark.parametrize('dotted', ['excel.compare_sheets', 'excel.compare_files'])
def test_real_workbook_mismatch_still_fails(files, dotted):
    _assert(_run(dotted, actual=files['xlsx'], reference=files['other_xlsx']), StatusEnum.FAILED)


def test_real_csv_file_mismatch_still_fails(files, tmp_path):
    other = tmp_path / 'other.csv'
    other.write_text('a,b\nx,y\n')

    _assert(_run('csv.compare_files', actual=files['csv'], reference=str(other)), StatusEnum.FAILED)
