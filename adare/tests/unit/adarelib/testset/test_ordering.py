"""Ordered comparison of numbers and timestamps (adarelib.testset.ordering)."""

import datetime

import pytest

from adarelib.testset.ordering import OrderingError, TimeFormat, compare, parameter_errors, to_datetime, to_number

pytestmark = pytest.mark.unit


@pytest.mark.parametrize(
    ('actual', 'expected', 'comparison', 'holds'),
    [
        (3, 2, 'greater', True),
        ('3', 2, 'greater', True),
        ('2.0', 2, 'equals', True),
        ('10', '9', 'greater', True),  # numeric, not lexical
        (2, 2, 'greater', False),
        (2, 2, 'greater_equal', True),
        (1, 2, 'less', True),
        (2, 2, 'less_equal', True),
        (2, 3, 'not_equals', True),
        ('1e3', 1000, 'equals', True),
        (0.1 + 0.2, '0.3', 'equals', False),  # exact: 0.30000000000000004
    ],
)
def test_numbers(actual, expected, comparison, holds):
    assert compare(actual, expected, comparison)[0] is holds


def test_number_tolerance_and_offset():
    assert compare(10.4, 10, 'equals', tolerance=0.5)[0]
    assert not compare(10.6, 10, 'equals', tolerance=0.5)[0]
    assert compare(10.6, 10, 'not_equals', tolerance=0.5)[0]
    # a = b + 1
    assert compare(6, 5, 'equals', offset=1)[0]
    assert not compare(6, 5, 'equals')[0]


def test_timestamps_iso_and_rfc2822():
    assert compare('2026-01-01T10:00:00Z', '2026-01-01T11:00:00+02:00', 'greater')[0]
    assert compare('Thu, 01 Jan 2026 10:00:00 GMT', '2026-01-01T10:00:00Z', 'equals')[0]
    assert compare('2026-01-01T10:00:05', '2026-01-01T10:00:00', 'equals', tolerance=10)[0]
    assert not compare('2026-01-01T10:00:15', '2026-01-01T10:00:00', 'equals', tolerance=10)[0]
    # offset in seconds: a is one hour after b
    assert compare('2026-01-01T11:00:00Z', '2026-01-01T10:00:00Z', 'equals', offset=3600)[0]


def test_numeric_timestamps_need_epoch():
    fmt = TimeFormat(epoch=1970, unit='ms')
    ok, message = compare(1767261600000, '2026-01-01T10:00:00Z', 'equals', time_format=fmt)
    assert ok, message
    # the same epoch applies to both sides
    assert compare(1767261600000, 1767261599000, 'greater', value_type='timestamp', time_format=fmt)[0]
    with pytest.raises(OrderingError):
        to_datetime(1767261600, TimeFormat())


def test_time_format_and_offset_zone():
    fmt = TimeFormat(time_format='%d.%m.%Y %H:%M', utc_offset='+01:00')
    assert to_datetime('01.01.2026 11:00', fmt) == datetime.datetime(2026, 1, 1, 10, 0, tzinfo=datetime.timezone.utc)
    with pytest.raises(OrderingError, match='time_format'):
        to_datetime('2026-01-01', fmt)


@pytest.mark.parametrize('value', [True, None, 'abc', 'nan', float('inf'), [1]])
def test_no_number(value):
    with pytest.raises(OrderingError):
        to_number(value)


def test_auto_refuses_mixed_kinds():
    with pytest.raises(OrderingError, match='not both numbers or both timestamps'):
        compare('abc', 3, 'greater')
    with pytest.raises(OrderingError):
        compare('abc', 3, 'greater', value_type='number')


@pytest.mark.parametrize(
    ('kwargs', 'fragment'),
    [
        ({'comparison_type': 'bigger'}, 'invalid comparison_type'),
        ({'comparison_type': 'equals', 'value_type': 'text'}, 'invalid value_type'),
        ({'comparison_type': 'greater', 'tolerance': 1}, 'only applies'),
        ({'comparison_type': 'equals', 'tolerance': -1}, 'negative'),
        ({'comparison_type': 'equals', 'offset': 'x'}, 'offset must be a number'),
    ],
)
def test_parameter_errors(kwargs, fragment):
    errors = parameter_errors(**kwargs)
    assert any(fragment in e for e in errors), errors
    with pytest.raises(OrderingError):
        compare(1, 1, **kwargs)


def test_message_names_values_and_verdict():
    ok, message = compare(3, 2, 'less')
    assert not ok
    assert message == 'number 3 < 2 does not hold'
