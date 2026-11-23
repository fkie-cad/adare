"""An unexpected exception inside a testfunction is an ERROR, never a FAILED result.

Collections used to wrap their bodies in ``except Exception`` and some turned
any error into FAILED, which reads as "the artifact is wrong" when the test
itself broke. They now let unexpected exceptions reach the ``@testfunction``
decorator, which reports them as ERROR.
"""

import inspect
import typing
from pathlib import Path

import attrs
import pytest

from adarelib.helper.module import import_module_from_pyfile
from adarelib.constants import StatusEnum
from adarelib.testset.api import TestContext

pytestmark = pytest.mark.unit

COLLECTIONS = Path(__file__).resolve().parents[3] / 'appdata' / 'testfunctions'
FILE_COLLECTIONS = (
    'csv',
    'excel',
    'json',
    'jsonl',
    'xml',
    'standard',
    'plist',
    'yaml',
    'toml',
    'ini',
    'image',
    'text',
    'binary',
)

_DUMMIES = {str: 'x', int: 1, float: 1.0, bool: False, list: [], dict: {}}

# Required parameters whose type dummy fails the function's own checks before dst is read.
VALID_PARAMS = {
    # round 2: lines_in_order
    'text.lines_in_order': {'patterns': ['x']},
    'jsonl.lines_in_order': {'conditions': [{'x': 1}]},
}


def _dummy(field):
    tp = field.type
    origin = typing.get_origin(tp) or tp
    if origin in (typing.Union, getattr(__import__('types'), 'UnionType', ())):
        origin = next(typing.get_origin(a) or a for a in typing.get_args(tp) if a is not type(None))
    return _DUMMIES.get(origin, 'x')


def _file_testfunctions():
    for collection in FILE_COLLECTIONS:
        module = import_module_from_pyfile(COLLECTIONS / collection / f'{collection}.py')
        for name, obj in vars(module).items():
            test_class = getattr(obj, '_test_class', None)
            source = inspect.getsource(obj) if test_class is not None else ''
            # file tests resolve dst themselves or through adarelib.testset.structured
            if not any(marker in source for marker in ('resolve_globfilepath', 'structured.', 'load_data(')):
                continue
            yield pytest.param(obj, VALID_PARAMS.get(f'{collection}.{name}', {}), id=f'{collection}.{name}')


@pytest.mark.parametrize(('testfunction', 'valid_params'), list(_file_testfunctions()))
def test_unexpected_exception_is_an_error(testfunction, valid_params, monkeypatch):
    def broken(self, *args, **kwargs):
        raise RuntimeError('boom')

    monkeypatch.setattr(TestContext, 'resolve_globfilepath', broken)
    param_cls = testfunction._parameter_class
    params = {f.name: _dummy(f) for f in attrs.fields(param_cls) if f.default is attrs.NOTHING}
    params.update(valid_params)
    test = testfunction._test_class(name='t', parameter=param_cls(**params))

    result = test.test()

    assert result.status == StatusEnum.ERROR, f'{result.status}: {result.details}'
    assert any('boom' in detail for detail in result.details)


def test_every_file_collection_is_covered():
    covered = {p.id.split('.')[0] for p in _file_testfunctions()}
    assert covered == set(FILE_COLLECTIONS)


# --- errors while reading a workbook ------------------------------------------

EXCEL = import_module_from_pyfile(COLLECTIONS / 'excel' / 'excel.py')


def _sheet_exists(path):
    param_cls = EXCEL.sheet_exists._parameter_class
    return EXCEL.sheet_exists._test_class(name='t', parameter=param_cls(dst=str(path), sheet='Data'))


def test_bug_while_reading_a_workbook_is_an_error_not_a_failure(create_excel_file, monkeypatch):
    path = create_excel_file('ok.xlsx', {'Data': [['a']]})

    def broken(self, filepath):
        raise RuntimeError('reader bug')

    monkeypatch.setattr(EXCEL.Workbook, '__init__', broken)

    result = _sheet_exists(path).test()

    assert result.status == StatusEnum.ERROR, result.details


def test_unreadable_workbook_is_an_error(tmp_path):
    path = tmp_path / 'corrupt.xlsx'
    path.write_bytes(b'this is not a zip archive')

    result = _sheet_exists(path).test()

    assert result.status == StatusEnum.ERROR, result.details
    assert 'Cannot parse Excel file' in result.details[0]


# --- placeholder comparisons ----------------------------------------------------


class _Ctx:
    def __init__(self, error):
        self.error = error

    def get_placeholders(self, text):
        return ['ts']

    def has_placeholders(self, text):
        return True

    def compare_with_placeholder(self, name, actual):
        raise self.error


def test_uninterpretable_placeholder_value_is_a_placeholder_error():
    # a value the placeholder cannot evaluate is a test-definition problem: ERROR, never "no match"
    from adarelib.testset.basictest import PlaceholderError
    from adarelib.testset.compare import compare_with_single_placeholder, row_matches_pattern

    with pytest.raises(PlaceholderError, match='bad timestamp'):
        compare_with_single_placeholder(_Ctx(ValueError('bad timestamp')), '{{ts}}', 'x')
    with pytest.raises(PlaceholderError, match='bad timestamp'):
        row_matches_pattern(_Ctx(ValueError('bad timestamp')), ['x'], ['{{ts}}'])


def test_bug_in_placeholder_comparison_propagates():
    from adarelib.testset.compare import compare_with_single_placeholder, row_matches_pattern

    with pytest.raises(RuntimeError):
        compare_with_single_placeholder(_Ctx(RuntimeError('bug')), '{{ts}}', 'x')
    with pytest.raises(RuntimeError):
        row_matches_pattern(_Ctx(RuntimeError('bug')), ['x'], ['{{ts}}'])
