"""Tests for numeric artifact timestamps (`epoch` / `unit` options of the !timestamp tag)."""

import datetime

import attrs
import pytest
import yaml

from adarelib.testset.basictest import BasicTest, Parameter
from adarelib.testset.yaml.customloader import get_custom_loader
from adarelib.testset.yaml.customtags import YamlTimestamp, numeric_timestamp_to_datetime

pytestmark = pytest.mark.unit

UTC = datetime.timezone.utc
INSTANT = datetime.datetime(2024, 1, 2, 3, 4, 5, tzinfo=UTC)
UNIX_S = 1704164645  # INSTANT as Unix seconds
SECONDS_1601_TO_1970 = 11644473600
SECONDS_1970_TO_2001 = 978307200

# INSTANT in every supported epoch/unit combination.
FORMATS = [
    pytest.param(1970, 's', UNIX_S, id='unix-s'),
    pytest.param(1970, 'ms', UNIX_S * 1000, id='unix-ms'),
    pytest.param(1970, 'us', UNIX_S * 1_000_000, id='unix-us'),
    pytest.param(1970, 'ns', UNIX_S * 1_000_000_000, id='unix-ns'),
    pytest.param(1601, '100ns', (UNIX_S + SECONDS_1601_TO_1970) * 10_000_000, id='filetime'),
    pytest.param(1601, 'us', (UNIX_S + SECONDS_1601_TO_1970) * 1_000_000, id='1601-us'),
    pytest.param(2001, 's', UNIX_S - SECONDS_1970_TO_2001, id='2001-s'),
]


@attrs.define
class _Param(Parameter):
    pass


def _test_with(metadata: dict) -> BasicTest:
    return BasicTest(name='t', parameter=_Param(), description='', variable_metadata={'ts_resolved': metadata})


def _tolerance_metadata(epoch, unit, **extra) -> dict:
    return {
        'type': 'timestamp',
        'raw_value': str(UNIX_S),
        'resolved_value': str(UNIX_S),
        'tolerance': [-1, 1],
        'epoch': epoch,
        'unit': unit,
        **extra,
    }


def _interval_metadata(epoch, unit, lower=-1.0, upper=1.0, **extra) -> dict:
    return {
        'type': 'timestamp',
        'raw_value': str(UNIX_S + lower),
        'resolved_value': str(UNIX_S + lower),
        'interval': [UNIX_S + lower, UNIX_S + upper],
        'epoch': epoch,
        'unit': unit,
        **extra,
    }


def _load(text: str):
    return yaml.load(text, Loader=get_custom_loader())


class TestConversion:
    @pytest.mark.parametrize(('epoch', 'unit', 'value'), FORMATS)
    def test_known_instant(self, epoch, unit, value):
        assert numeric_timestamp_to_datetime(value, epoch, unit) == INSTANT.replace(tzinfo=None)
        assert numeric_timestamp_to_datetime(str(value), epoch, unit) == INSTANT.replace(tzinfo=None)

    def test_ns_keeps_sub_second_digits(self):
        value = UNIX_S * 1_000_000_000 + 123_456_789
        assert numeric_timestamp_to_datetime(value, 1970, 'ns') == datetime.datetime(2024, 1, 2, 3, 4, 5, 123456)

    def test_100ns_keeps_sub_second_digits(self):
        value = (UNIX_S + SECONDS_1601_TO_1970) * 10_000_000 + 1_234_567
        assert numeric_timestamp_to_datetime(value, 1601, '100ns') == datetime.datetime(2024, 1, 2, 3, 4, 5, 123456)

    def test_fractional_seconds(self):
        # A REAL column counting seconds since 2001.
        value = UNIX_S - SECONDS_1970_TO_2001 + 0.5
        expected = datetime.datetime(2024, 1, 2, 3, 4, 5, 500000)
        assert numeric_timestamp_to_datetime(value, 2001, 's') == expected
        assert numeric_timestamp_to_datetime(str(value), 2001, 's') == expected

    def test_negative_value_counts_back(self):
        assert numeric_timestamp_to_datetime('-1', 1970, 's') == datetime.datetime(1969, 12, 31, 23, 59, 59)

    @pytest.mark.parametrize('value', ['2024-01-02', 'abc', '', '1e5', True, None, float('nan'), [1]])
    def test_non_numeric_raises(self, value):
        with pytest.raises(ValueError):
            numeric_timestamp_to_datetime(value, 1601, '100ns')

    def test_out_of_range_raises_value_error(self):
        with pytest.raises(ValueError, match='out of range'):
            numeric_timestamp_to_datetime(10**30, 1970, 's')


class TestTag:
    def test_options_stored(self):
        tag = _load("!timestamp {timestamp: '{{ t }}', tolerance: 2, epoch: 1601, unit: 100ns}")
        assert isinstance(tag, YamlTimestamp)
        assert tag.metadata == {'tolerance': [-2, 2], 'epoch': 1601, 'unit': '100ns'}

    def test_epoch_as_string(self):
        tag = _load("!timestamp {after: '{{ a }}', before: '{{ b }}', epoch: '2001'}")
        assert tag.metadata['epoch'] == 2001
        assert 'unit' not in tag.metadata

    def test_defaults_not_stored(self):
        tag = _load("!timestamp {timestamp: '{{ t }}', tolerance: 2}")
        assert 'epoch' not in tag.metadata and 'unit' not in tag.metadata

    @pytest.mark.parametrize('epoch', ['1900', 1600, 'unix', 'true', '1970.0'])
    def test_bad_epoch(self, epoch):
        with pytest.raises(ValueError, match='epoch must be one of'):
            _load(f"!timestamp {{timestamp: '{{{{ t }}}}', tolerance: 2, epoch: {epoch}}}")

    @pytest.mark.parametrize('unit', ['sec', 'MS', 'µs', '10ns', '1'])
    def test_bad_unit(self, unit):
        with pytest.raises(ValueError, match='unit must be one of'):
            _load(f"!timestamp {{timestamp: '{{{{ t }}}}', tolerance: 2, unit: '{unit}'}}")

    def test_bool_epoch_rejected(self):
        with pytest.raises(ValueError, match='epoch must be one of'):
            YamlTimestamp(timestamp='{{ t }}', tolerance=2, epoch=True)

    def test_needs_tolerance_or_interval(self):
        with pytest.raises(ValueError, match='tolerance or an after/before interval'):
            _load("!timestamp {timestamp: '{{ t }}', epoch: 1601}")


class TestToleranceComparison:
    @pytest.mark.parametrize(('epoch', 'unit', 'value'), FORMATS)
    def test_int_value(self, epoch, unit, value):
        ok, msg = _test_with(_tolerance_metadata(epoch, unit)).compare_with_placeholder('ts_resolved', value)
        assert ok, msg

    @pytest.mark.parametrize(('epoch', 'unit', 'value'), FORMATS)
    def test_digit_string_value(self, epoch, unit, value):
        ok, msg = _test_with(_tolerance_metadata(epoch, unit)).compare_with_placeholder('ts_resolved', str(value))
        assert ok, msg

    def test_outside_tolerance(self):
        value = (UNIX_S + SECONDS_1601_TO_1970 + 5) * 10_000_000
        ok, msg = _test_with(_tolerance_metadata(1601, '100ns')).compare_with_placeholder('ts_resolved', value)
        assert not ok and 'Outside tolerance' in msg

    @pytest.mark.parametrize('tolerance', [0, [0, 0]])
    def test_zero_tolerance_still_converts(self, tolerance):
        """``tolerance: 0`` with epoch/unit compares the converted instant, not the raw string."""
        value = (UNIX_S + SECONDS_1601_TO_1970) * 10_000_000
        metadata = _tolerance_metadata(1601, '100ns', tolerance=tolerance)
        ok, msg = _test_with(metadata).compare_with_placeholder('ts_resolved', value)
        assert ok, msg
        ok, _ = _test_with(metadata).compare_with_placeholder('ts_resolved', value + 10_000_000)
        assert not ok

    def test_value_read_with_wrong_unit_fails(self):
        # Unix ms read as seconds lands far in the future.
        ok, _ = _test_with(_tolerance_metadata(1970, 's')).compare_with_placeholder('ts_resolved', UNIX_S * 1000)
        assert not ok

    def test_localtime_value_read_in_guest_timezone(self):
        # The artifact counts from the epoch in guest local wall time (guest at UTC+02:00).
        value = (UNIX_S + 2 * 3600 + SECONDS_1601_TO_1970) * 10_000_000
        metadata = _tolerance_metadata(1601, '100ns', localtime=True, guest_utc_offset='+02:00')
        ok, msg = _test_with(metadata).compare_with_placeholder('ts_resolved', value)
        assert ok, msg

    def test_non_numeric_value_fails(self):
        metadata = _tolerance_metadata(1601, '100ns')
        ok, _ = _test_with(metadata).compare_with_placeholder('ts_resolved', '2024-01-02T03:04:05Z')
        assert not ok


class TestIntervalComparison:
    @pytest.mark.parametrize(('epoch', 'unit', 'value'), FORMATS)
    def test_int_value(self, epoch, unit, value):
        ok, msg = _test_with(_interval_metadata(epoch, unit)).compare_with_placeholder('ts_resolved', value)
        assert ok, msg

    @pytest.mark.parametrize(('epoch', 'unit', 'value'), FORMATS)
    def test_digit_string_value(self, epoch, unit, value):
        ok, msg = _test_with(_interval_metadata(epoch, unit)).compare_with_placeholder('ts_resolved', str(value))
        assert ok, msg

    def test_sub_second_ns_inside_narrow_interval(self):
        value = UNIX_S * 1_000_000_000 + 123_456_789
        metadata = _interval_metadata(1970, 'ns', lower=0.1234, upper=0.1235)
        ok, msg = _test_with(metadata).compare_with_placeholder('ts_resolved', value)
        assert ok, msg

    def test_sub_second_100ns_outside_narrow_interval(self):
        value = (UNIX_S + SECONDS_1601_TO_1970) * 10_000_000 + 1_234_567
        metadata = _interval_metadata(1601, '100ns', lower=0.2, upper=0.3)
        ok, msg = _test_with(metadata).compare_with_placeholder('ts_resolved', value)
        assert not ok and 'Before interval' in msg

    def test_non_numeric_value_fails_with_parse_message(self):
        metadata = _interval_metadata(1601, '100ns')
        ok, msg = _test_with(metadata).compare_with_placeholder('ts_resolved', 'not a number')
        assert not ok and 'could not parse' in msg

    def test_bool_value_is_not_a_number(self):
        ok, msg = _test_with(_interval_metadata(1970, 's')).compare_with_placeholder('ts_resolved', True)
        assert not ok and 'could not parse' in msg


class TestDefaultUnixPath:
    def test_int_actual_without_options(self):
        # A numeric column without epoch/unit is read as Unix seconds, as a digit string is.
        metadata = _interval_metadata(1970, 's')
        del metadata['epoch'], metadata['unit']
        ok, msg = _test_with(metadata).compare_with_placeholder('ts_resolved', UNIX_S)
        assert ok, msg
