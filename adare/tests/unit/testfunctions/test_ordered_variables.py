"""Saved variables in ordered comparisons: ``expected_value: '{{ name }}'`` with ``comparison_type``.

A lone placeholder is the variable's saved value: a number or text (save_variable, a command's
capture) or a point in time (save_timestamp). A variable not set yet, a regex variable, a
timestamp with a tolerance or interval and text around the placeholder are an ERROR: the test
definition is broken, nothing was learnt about the artifact.

Runs on the guests' Python 3.10 too (``make test-testfunctions-guest``).
"""

import datetime
import json
import struct
from pathlib import Path

import pytest

from adarelib.constants import StatusEnum
from adarelib.helper.module import import_module_from_pyfile

pytestmark = pytest.mark.unit

COLLECTIONS = Path(__file__).resolve().parents[3] / 'appdata' / 'testfunctions'
SUCCESS, FAILED, ERROR = StatusEnum.SUCCESS, StatusEnum.FAILED, StatusEnum.ERROR

_modules = {}


def _module(collection):
    if collection not in _modules:
        _modules[collection] = import_module_from_pyfile(COLLECTIONS / collection / f'{collection}.py')
    return _modules[collection]


def _run(dotted, variable_metadata, **params):
    collection, name = dotted.split('.')
    testfunction = getattr(_module(collection), name)
    test = testfunction._test_class(
        name='t', parameter=testfunction._parameter_class(**params), variable_metadata=variable_metadata
    )
    return test.test()


def _assert(result, status):
    assert result.status == status, f'expected {status.name}, got {result.status}: {result.details}'


SAVED = {
    'count': {'type': 'integer', 'raw_value': '5', 'resolved_value': '5'},
    'ratio': {'type': 'float', 'resolved_value': 0.5},
    'label': {'type': 'string', 'resolved_value': '6'},
    'started': {'type': 'timestamp', 'raw_value': '2026-03-01T10:00:00Z', 'resolved_value': '2026-03-01T10:00:00Z'},
    'started_unix': {'type': 'timestamp', 'resolved_value': '1772359200'},
    'started_local': {'type': 'timestamp', 'resolved_value': '2026-03-01 12:00:00', 'localtime': True},
    'pattern': {'type': 'regex', 'raw_value': '^7', 'resolved_value': '^7'},
    'loose': {'type': 'timestamp', 'resolved_value': '2026-03-01T10:00:00Z', 'tolerance': [-5, 5]},
    'window': {'type': 'timestamp', 'resolved_value': '2026-03-01T10:00:00Z', 'interval': ['a', 'b']},
    'pending': {'type': 'timestamp', 'raw_value': '{{ t0 }}', 'resolved_value': '{{ t0 }}'},
    'flags': {'type': 'list', 'resolved_value': '[1]'},
    'garbled': {'type': 'timestamp', 'resolved_value': 'not a time'},
}


@pytest.fixture
def dst(tmp_path):
    path = tmp_path / 'state.json'
    path.write_text(
        json.dumps({'count': 7, 'modified': '2026-03-01T10:00:04Z', 'opened': '2026-03-01T09:59:00Z', 'base': 2}),
        encoding='utf-8',
    )
    return str(path)


def _value(dst, key_path, expected_value, **params):
    return _run('json.value_matches', SAVED, dst=dst, key_path=key_path, expected_value=expected_value, **params)


@pytest.mark.parametrize(
    ('key_path', 'expected', 'params', 'status'),
    [
        ('count', '{{ count }}', {'comparison_type': 'greater'}, SUCCESS),  # 7 > 5
        ('count', '{{count}}', {'comparison_type': 'less'}, FAILED),
        ('count', ' {{ ratio }} ', {'comparison_type': 'greater'}, SUCCESS),  # whitespace around it
        ('count', '{{ label }}', {'comparison_type': 'greater_equal'}, SUCCESS),  # text holding a number
        ('count', '{{ count }}', {'tolerance': 2}, SUCCESS),  # |7 - 5| <= 2
        ('modified', '{{ started }}', {'comparison_type': 'greater'}, SUCCESS),  # 10:00:04 after 10:00:00
        ('opened', '{{ started }}', {'comparison_type': 'less'}, SUCCESS),  # 09:59 before 10:00
        ('modified', '{{ started }}', {'comparison_type': 'less'}, FAILED),
        ('modified', '{{ started_unix }}', {'comparison_type': 'greater'}, SUCCESS),
        ('modified', '{{ started }}', {'tolerance': 5}, SUCCESS),
        ('modified', '{{ started }}', {'tolerance': 2}, FAILED),
    ],
)
def test_saved_variable_is_the_expected_value(dst, key_path, expected, params, status):
    _assert(_value(dst, key_path, expected, **params), status)


def test_localtime_timestamp_uses_the_guest_offset(dst):
    # 12:00 guest local time at +02:00 is 10:00 UTC: the file's 10:00:04Z is later
    saved = {'started_local': {**SAVED['started_local'], 'guest_utc_offset': '+02:00'}}
    result = _run(
        'json.value_matches',
        saved,
        dst=dst,
        key_path='modified',
        expected_value='{{ started_local }}',
        comparison_type='greater',
    )
    _assert(result, SUCCESS)
    result = _run(
        'json.value_matches',
        saved,
        dst=dst,
        key_path='opened',
        expected_value='{{ started_local }}',
        comparison_type='greater',
    )
    _assert(result, FAILED)


@pytest.mark.parametrize(
    ('expected', 'message'),
    [
        ('{{ unknown }}', 'not set before the test'),
        ('{{ pending }}', 'not set before the test'),
        ('{{ pattern }}', 'regex'),
        ('{{ loose }}', 'tolerance or interval'),
        ('{{ window }}', 'tolerance or interval'),
        ('{{ flags }}', 'type list'),
        ('{{ garbled }}', 'no timestamp'),
        ('at {{ count }}', 'mixes text'),
    ],
)
def test_unusable_variable_is_an_error(dst, expected, message):
    result = _value(dst, 'count', expected, comparison_type='greater')
    _assert(result, ERROR)
    assert message in ' '.join(result.details)


def test_without_variable_metadata_the_variable_is_not_set(dst):
    result = _run(
        'json.value_matches', None, dst=dst, key_path='count', expected_value='{{ count }}', comparison_type='greater'
    )
    _assert(result, ERROR)
    assert 'not set before the test' in result.details[0]


def test_equality_mode_keeps_placeholder_matching(dst):
    # no ordered parameter: the old placeholder comparison (exact text of a string variable)
    _assert(_value(dst, 'count', '{{ label }}'), FAILED)  # 7 != '6'


@pytest.mark.parametrize(
    ('dotted', 'params'),
    [
        ('yaml.value_matches', {'key_path': 'count'}),
        ('toml.value_matches', {'key_path': 'count'}),
        ('ini.value_matches', {'section': 'main', 'key': 'count'}),
        ('xml.element_text_matches', {'xpath': './count'}),
        ('xml.attribute_matches', {'xpath': '.', 'attribute': 'count'}),
        ('jsonl.value_in_any_line', {'key_path': 'count'}),
    ],
)
def test_other_collections_resolve_saved_variables(tmp_path, dotted, params):
    files = {
        'yaml': ('a.yaml', 'count: 7\n'),
        'toml': ('a.toml', 'count = 7\n'),
        'ini': ('a.ini', '[main]\ncount = 7\n'),
        'xml': ('a.xml', '<root count="7"><count>7</count></root>'),
        'jsonl': ('a.jsonl', '{"count": 7}\n'),
    }
    name, content = files[dotted.split('.')[0]]
    path = tmp_path / name
    path.write_text(content, encoding='utf-8')
    for comparison, status in (('greater', SUCCESS), ('less', FAILED)):
        result = _run(dotted, SAVED, dst=str(path), expected_value='{{ count }}', comparison_type=comparison, **params)
        _assert(result, status)
    _assert(
        _run(dotted, SAVED, dst=str(path), expected_value='{{ pattern }}', comparison_type='greater', **params), ERROR
    )


# --- values_compare: offset ----------------------------------------------------------------


def test_values_compare_offset_may_be_a_saved_number(dst):
    result = _run('json.values_compare', SAVED, dst=dst, key_path='count', other_key_path='base', offset='{{ count }}')
    _assert(result, SUCCESS)  # 7 == 2 + 5
    result = _run('json.values_compare', SAVED, dst=dst, key_path='count', other_key_path='base', offset='{{ ratio }}')
    _assert(result, FAILED)


@pytest.mark.parametrize('offset', ['{{ started }}', '{{ unknown }}', '{{ pattern }}', 'x {{ count }}'])
def test_values_compare_offset_variable_errors(dst, offset):
    result = _run('json.values_compare', SAVED, dst=dst, key_path='count', other_key_path='base', offset=offset)
    _assert(result, ERROR)


# --- binary.struct_value_matches ------------------------------------------------------------


@pytest.fixture
def blob(tmp_path):
    path = tmp_path / 'entry.bin'
    stamp = int(datetime.datetime(2026, 3, 1, 10, 0, 4, tzinfo=datetime.timezone.utc).timestamp())
    path.write_bytes(struct.pack('<II', 7, stamp))
    return str(path)


@pytest.mark.parametrize(
    ('offset', 'expected', 'params', 'status'),
    [
        (0, '{{ count }}', {'comparison_type': 'greater'}, SUCCESS),
        (0, '{{ count }}', {'comparison_type': 'less'}, FAILED),
        (0, '{{ count }}', {'tolerance': 2}, SUCCESS),
        (4, '{{ started }}', {'comparison_type': 'greater', 'timestamp_epoch': 1970}, SUCCESS),
        (4, '{{ started }}', {'comparison_type': 'less', 'timestamp_epoch': 1970}, FAILED),
        (0, '{{ unknown }}', {'comparison_type': 'greater'}, ERROR),
        (0, '{{ pattern }}', {'comparison_type': 'greater'}, ERROR),
        (4, '{{ loose }}', {'comparison_type': 'greater', 'timestamp_epoch': 1970}, ERROR),
    ],
)
def test_binary_struct_value_resolves_saved_variables(blob, offset, expected, params, status):
    result = _run(
        'binary.struct_value_matches',
        SAVED,
        dst=blob,
        offset=offset,
        value_format='u32le',
        expected_value=expected,
        **params,
    )
    _assert(result, status)
