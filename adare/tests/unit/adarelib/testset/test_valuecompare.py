"""Ordered-comparison parameters and values_compare bodies (adarelib.testset.valuecompare)."""

import pytest

from adarelib.constants import StatusEnum
from adarelib.testset.ordering import OrderingError
from adarelib.testset.valuecompare import (
    build_comparison,
    compare_pair,
    expected_conflicts,
    ordered_comparison,
    ordered_setup,
    saved_value,
)
from adarelib.testset.yaml.customtags import YamlRegexString

pytestmark = pytest.mark.unit


class _Ctx:
    def __init__(self, metadata=None):
        self.metadata = metadata or {}

    @staticmethod
    def has_placeholders(text):
        return '{{' in text and '}}' in text

    def get_placeholder_metadata(self, name):
        return self.metadata.get(name, {})

    @staticmethod
    def parse_expected_timestamp(value, metadata):
        import datetime

        return datetime.datetime.fromisoformat(value)


def test_defaults_mean_plain_equality():
    assert ordered_comparison() is None
    assert ordered_comparison('equals', 'auto') is None


@pytest.mark.parametrize(
    'params',
    [
        {'comparison_type': 'greater'},
        {'value_type': 'number'},
        {'tolerance': 0},
        {'time_format': '%Y'},
        {'timestamp_epoch': 1601},
        {'utc_offset': '+01:00'},
    ],
)
def test_any_parameter_switches_to_ordered_mode(params):
    assert ordered_comparison(**params) is not None


def test_time_parameters_reach_the_time_format():
    comparison = build_comparison(timestamp_epoch=2001, timestamp_unit='ms', utc_offset='+02:00', offset=3)
    assert (comparison.time.epoch, comparison.time.unit, comparison.time.utc_offset) == (2001, 'ms', '+02:00')
    assert comparison.offset == 3
    assert build_comparison(timestamp_epoch=1970).time.unit == 's'


@pytest.mark.parametrize(
    ('params', 'message'),
    [
        ({'comparison_type': 'after'}, 'comparison_type'),
        ({'value_type': 'date'}, 'value_type'),
        ({'tolerance': 'x'}, 'tolerance'),
        ({'offset': 'x'}, 'offset'),
        ({'timestamp_epoch': 1900}, 'timestamp_epoch'),
        ({'timestamp_epoch': True}, 'timestamp_epoch'),
        ({'timestamp_unit': 'ms'}, 'needs timestamp_epoch'),
        ({'timestamp_epoch': 1970, 'timestamp_unit': 'min'}, 'timestamp_unit'),
        ({'utc_offset': 'Mars'}, 'utc_offset'),
        ({'time_format': 5}, 'time_format'),
        ({'value_type': 'number', 'utc_offset': '+01:00'}, 'value_type number'),
    ],
)
def test_bad_parameters_raise(params, message):
    with pytest.raises(OrderingError, match=message):
        build_comparison(**params)


def test_expected_conflicts():
    ctx = _Ctx()
    assert expected_conflicts(ctx, '5') == []
    assert expected_conflicts(ctx, 5) == []
    assert 'regex_match' in expected_conflicts(ctx, '5', regex_match=True)[0]
    assert '!re' in expected_conflicts(ctx, YamlRegexString('^5'))[0]
    assert expected_conflicts(ctx, '{{start}}') == []  # placeholders: saved_value decides


def test_ordered_setup_returns_errors_as_results():
    ctx = _Ctx()
    assert ordered_setup(ctx, '5', True) == (None, '5', None)  # defaults: regex_match is fine
    ordered, _, problem = ordered_setup(ctx, '5', True, 'greater')
    assert ordered is None and problem.status == StatusEnum.ERROR
    ordered, _, problem = ordered_setup(ctx, '5', False, 'sideways')
    assert ordered is None and problem.status == StatusEnum.ERROR
    ordered, expected, problem = ordered_setup(ctx, '5', False, 'greater')
    assert problem is None and expected == '5' and ordered.compare(6, expected)[0]


def test_ordered_setup_resolves_a_lone_saved_variable():
    ctx = _Ctx(
        {
            'n': {'type': 'integer', 'resolved_value': '5'},
            't': {'type': 'timestamp', 'resolved_value': '2026-01-01T00:00:00+00:00'},
        }
    )
    ordered, expected, problem = ordered_setup(ctx, '{{ n }}', False, 'greater')
    assert problem is None and expected == '5' and ordered.compare(6, expected)[0]
    _, expected, problem = ordered_setup(ctx, '{{t}}', False, 'less')
    assert problem is None and expected.year == 2026
    # equality mode: the placeholder stays for the placeholder comparison
    assert ordered_setup(ctx, '{{ n }}', False) == (None, '{{ n }}', None)


@pytest.mark.parametrize(
    ('value', 'metadata', 'message'),
    [
        ('{{ n }}', {}, 'not set before the test'),
        ('{{ n }}', {'n': {'type': 'regex', 'resolved_value': '^5'}}, 'type regex'),
        ('{{ n }}', {'n': {'type': 'timestamp', 'resolved_value': '2026-01-01', 'tolerance': 5}}, 'tolerance'),
        ('a{{ n }}', {'n': {'type': 'integer', 'resolved_value': '5'}}, 'mixes text'),
    ],
)
def test_saved_value_errors(value, metadata, message):
    resolved, errors = saved_value(_Ctx(metadata), value)
    assert resolved == value and message in errors[0]


def test_saved_value_without_timestamps():
    ctx = _Ctx({'t': {'type': 'timestamp', 'resolved_value': '2026-01-01T00:00:00+00:00'}})
    _, errors = saved_value(ctx, '{{ t }}', 'offset', timestamps=False)
    assert 'offset' in errors[0] and 'a number' in errors[0]
    assert saved_value(ctx, 5) == (5, [])


@pytest.mark.parametrize(
    ('values', 'other', 'status'),
    [
        ([3], [2], StatusEnum.SUCCESS),
        ([[3]], [2], StatusEnum.SUCCESS),  # one array with one element
        ([1], [2], StatusEnum.FAILED),
        ([], [2], StatusEnum.FAILED),
        ([[]], [2], StatusEnum.FAILED),
        ([1, 2], [2], StatusEnum.ERROR),
        ([[1, 2]], [2], StatusEnum.ERROR),
        ([], [1, 2], StatusEnum.ERROR),  # ambiguity is reported before absence
        (['x'], [2], StatusEnum.ERROR),
        ([None], [2], StatusEnum.ERROR),
    ],
)
def test_compare_pair(values, other, status):
    result = compare_pair('a', values, 'b', other, build_comparison('greater'))
    assert result.status == status, result.details
