"""Ordered comparisons in json.value_matches and json.values_compare (two values of one file).

Runs on the guests' Python 3.10 too (``make test-testfunctions-guest``).
"""

import json
from pathlib import Path

import pytest

from adarelib.constants import StatusEnum
from adarelib.helper.module import import_module_from_pyfile
from adarelib.testset.yaml.customtags import YamlRegexString

pytestmark = pytest.mark.unit

COLLECTIONS = Path(__file__).resolve().parents[3] / 'appdata' / 'testfunctions'
json_tf = import_module_from_pyfile(COLLECTIONS / 'json' / 'json.py')
ValueMatches = json_tf.value_matches._test_class
ValuesCompare = json_tf.values_compare._test_class

SUCCESS, FAILED, ERROR = StatusEnum.SUCCESS, StatusEnum.FAILED, StatusEnum.ERROR

DATA = {
    'count': 7,
    'size': '1500',
    'ratio': 0.25,
    'label': 'seven',
    'created': '2026-03-01T10:00:00Z',
    'modified': '2026-03-01T10:00:04+00:00',
    'local': '2026-03-01 12:00:00',
    'saved_ms': 1772359204000,  # 2026-03-01T10:00:04Z in ms since 1970
    'opened_ms': 1772359200000,  # 2026-03-01T10:00:00Z
    'stamp': '01.03.2026 10:00',
    'version': {'major': 3, 'minor': 4, 'build': 5},
    'items': [{'n': 1}, {'n': 5}, {'n': 9}],
    'single': [42],
    'empty': [],
    'nothing': None,
}


@pytest.fixture
def dst(tmp_path):
    path = tmp_path / 'data.json'
    path.write_text(json.dumps(DATA), encoding='utf-8')
    return str(path)


def _matches(dst, key_path, expected_value, **params):
    parameter = json_tf.value_matches._parameter_class(
        dst=dst, key_path=key_path, expected_value=expected_value, **params
    )
    return ValueMatches(name='t', parameter=parameter).test()


def _compare(dst, key_path, other_key_path, **params):
    parameter = json_tf.values_compare._parameter_class(
        dst=dst, key_path=key_path, other_key_path=other_key_path, **params
    )
    return ValuesCompare(name='t', parameter=parameter).test()


def _assert(result, status):
    assert result.status == status, f'{result.status}: {result.details}'


# --- json.value_matches: ordered mode ---------------------------------------------------


@pytest.mark.parametrize(
    ('key_path', 'expected_value', 'params', 'status'),
    [
        ('count', 5, {'comparison_type': 'greater'}, SUCCESS),
        ('count', 7, {'comparison_type': 'greater'}, FAILED),
        ('count', 7, {'comparison_type': 'greater_equal'}, SUCCESS),
        ('count', '10', {'comparison_type': 'less'}, SUCCESS),  # numeric, not lexical
        ('size', 1500, {'value_type': 'number'}, SUCCESS),  # text 1500 == number 1500
        ('size', '1499', {'comparison_type': 'not_equals'}, SUCCESS),
        ('ratio', 0.2, {'tolerance': 0.05}, SUCCESS),
        ('ratio', 0.1, {'tolerance': 0.05}, FAILED),
        ('created', '2026-03-01T09:59:59Z', {'comparison_type': 'greater'}, SUCCESS),
        ('created', '2026-03-01T11:00:00+01:00', {'comparison_type': 'equals', 'value_type': 'timestamp'}, SUCCESS),
        ('modified', '2026-03-01T10:00:00Z', {'tolerance': 5}, SUCCESS),
        ('modified', '2026-03-01T10:00:00Z', {'tolerance': 3}, FAILED),
        ('saved_ms', '2026-03-01T10:00:04Z', {'timestamp_epoch': 1970, 'timestamp_unit': 'ms'}, SUCCESS),
        ('stamp', '01.03.2026 09:59', {'time_format': '%d.%m.%Y %H:%M', 'comparison_type': 'greater'}, SUCCESS),
        ('local', '2026-03-01T10:00:00Z', {'utc_offset': '+02:00'}, SUCCESS),
        ('local', '2026-03-01T10:00:00Z', {'value_type': 'timestamp'}, FAILED),  # read as UTC
    ],
)
def test_value_matches_ordered(dst, key_path, expected_value, params, status):
    _assert(_matches(dst, key_path, expected_value, **params), status)


def test_value_matches_default_behaviour_unchanged(dst):
    _assert(_matches(dst, 'size', '1500'), SUCCESS)
    _assert(_matches(dst, 'size', 1500), FAILED)  # type-sensitive == as before
    _assert(_matches(dst, 'label', 'sev', regex_match=True), SUCCESS)
    _assert(_matches(dst, 'label', YamlRegexString('^sev')), SUCCESS)


def test_value_matches_ordered_wildcard_modes(dst):
    _assert(_matches(dst, 'items[*].n', 8, comparison_type='greater'), SUCCESS)
    _assert(_matches(dst, 'items[*].n', 8, comparison_type='greater', wildcard_mode='all'), FAILED)
    _assert(_matches(dst, 'items[*].n', 0, comparison_type='greater', wildcard_mode='all'), SUCCESS)


@pytest.mark.parametrize(
    ('key_path', 'expected_value', 'params'),
    [
        ('label', 3, {'comparison_type': 'greater'}),  # no number or timestamp
        ('nothing', 3, {'comparison_type': 'greater'}),
        ('count', 'soon', {'comparison_type': 'greater'}),
        ('count', 3, {'comparison_type': 'after'}),  # bad comparison_type
        ('count', 3, {'value_type': 'text'}),
        ('count', 3, {'comparison_type': 'greater', 'tolerance': 1}),  # tolerance only for equals
        ('count', 3, {'tolerance': -1}),
        ('count', 3, {'timestamp_epoch': 1980}),
        ('count', 3, {'timestamp_unit': 'ms'}),  # unit without epoch
        ('count', 3, {'utc_offset': 'nowhere'}),
        ('count', 3, {'value_type': 'number', 'time_format': '%Y'}),
    ],
)
def test_value_matches_ordered_bad_values_and_parameters_are_errors(dst, key_path, expected_value, params):
    _assert(_matches(dst, key_path, expected_value, **params), ERROR)


@pytest.mark.parametrize(
    ('expected_value', 'params'),
    [
        ('7', {'comparison_type': 'greater', 'regex_match': True}),
        (YamlRegexString('^7'), {'comparison_type': 'greater'}),
        ('{{started}}', {'value_type': 'timestamp'}),
    ],
)
def test_value_matches_regex_or_placeholder_with_ordered_mode_is_error(dst, expected_value, params):
    result = _matches(dst, 'count', expected_value, **params)
    _assert(result, ERROR)
    assert 'ordered' in ' '.join(result.details) or 'in order' in ' '.join(result.details)


def test_value_matches_ordered_missing_key_fails(dst):
    _assert(_matches(dst, 'missing', 3, comparison_type='greater'), FAILED)


# --- json.values_compare ----------------------------------------------------------------


@pytest.mark.parametrize(
    ('key_path', 'other_key_path', 'params', 'status'),
    [
        ('created', 'modified', {'comparison_type': 'less'}, SUCCESS),  # created earlier than modified
        ('modified', 'created', {'comparison_type': 'less'}, FAILED),
        ('modified', 'created', {'tolerance': 5}, SUCCESS),  # within 5 s
        ('modified', 'created', {'tolerance': 2}, FAILED),
        ('modified', 'created', {'offset': 4}, SUCCESS),  # modified = created + 4 s
        ('version.build', 'version.minor', {'offset': 1}, SUCCESS),  # A = B + 1
        ('version.build', 'version.major', {'offset': 1}, FAILED),
        ('version.major', 'version.minor', {'comparison_type': 'less_equal'}, SUCCESS),
        ('count', 'size', {'comparison_type': 'less'}, SUCCESS),  # 7 < "1500" numerically
        (
            'saved_ms',
            'opened_ms',
            {'comparison_type': 'greater', 'timestamp_epoch': 1970, 'timestamp_unit': 'ms'},
            SUCCESS,
        ),
        ('saved_ms', 'opened_ms', {'offset': 4000}, SUCCESS),  # plain numbers: 4000 ms apart
        ('modified', 'saved_ms', {'timestamp_epoch': 1970, 'timestamp_unit': 'ms'}, SUCCESS),  # ISO vs epoch
        ('single', 'count', {'offset': 35}, SUCCESS),  # a one-element array is its element
    ],
)
def test_values_compare(dst, key_path, other_key_path, params, status):
    _assert(_compare(dst, key_path, other_key_path, **params), status)


def test_values_compare_reports_both_values(dst):
    result = _compare(dst, 'version.major', 'version.minor', comparison_type='less')
    _assert(result, SUCCESS)
    assert 'version.major' in result.details[0] and "'3'" in result.details[0]


@pytest.mark.parametrize(
    ('key_path', 'other_key_path'), [('missing', 'count'), ('count', 'missing'), ('empty', 'count')]
)
def test_values_compare_missing_side_fails(dst, key_path, other_key_path):
    _assert(_compare(dst, key_path, other_key_path), FAILED)


@pytest.mark.parametrize(
    ('key_path', 'other_key_path'),
    [('items[*].n', 'count'), ('count', 'version.*'), ('items', 'count'), ('items[*].n', 'missing')],
)
def test_values_compare_ambiguous_side_is_error(dst, key_path, other_key_path):
    result = _compare(dst, key_path, other_key_path)
    _assert(result, ERROR)
    assert 'exactly one value' in result.details[0]


@pytest.mark.parametrize(
    ('key_path', 'other_key_path', 'params'),
    [
        ('label', 'count', {}),  # no number or timestamp
        ('count', 'created', {}),  # number vs timestamp
        ('nothing', 'count', {}),
        ('version', 'count', {}),  # an object
        ('count', 'count', {'comparison_type': 'before'}),
        ('count', 'count', {'offset': 'soon'}),
        ('count', 'count', {'comparison_type': 'less', 'tolerance': 1}),
    ],
)
def test_values_compare_uninterpretable_values_and_bad_parameters_are_errors(dst, key_path, other_key_path, params):
    _assert(_compare(dst, key_path, other_key_path, **params), ERROR)


def test_values_compare_missing_file_is_error(tmp_path):
    _assert(_compare(str(tmp_path / 'absent.json'), 'a', 'b'), ERROR)


def test_values_compare_encoding(tmp_path):
    path = tmp_path / 'latin.json'
    path.write_bytes('{"a": "2026-01-02", "b": "2026-01-01", "n": "\xe9"}'.encode('latin-1'))
    _assert(_compare(str(path), 'a', 'b', comparison_type='greater', encoding='latin-1'), SUCCESS)
