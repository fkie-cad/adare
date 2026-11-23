"""Tests for interval timestamp checks and guest-timezone handling in adarelib."""

import datetime

import attrs
import pytest
import yaml

from adarelib.testset.basictest import BasicTest, Parameter
from adarelib.testset.timeinterval import check_interval, parse_timestamp_text, parse_utc_offset
from adarelib.testset.yaml.customloader import get_custom_loader
from adarelib.testset.yaml.customtags import YamlTimestamp

pytestmark = pytest.mark.unit

UTC = datetime.timezone.utc
T0 = datetime.datetime(2026, 10, 24, 12, 0, 0, tzinfo=UTC)


@attrs.define
class _Param(Parameter):
    pass


def _test_with(metadata: dict) -> BasicTest:
    return BasicTest(name='t', parameter=_Param(), description='', variable_metadata={'ts_resolved': metadata})


def _interval_metadata(**extra) -> dict:
    lower, upper = T0.timestamp(), T0.timestamp() + 10
    return {
        'type': 'timestamp',
        'raw_value': str(lower),
        'resolved_value': str(lower),
        'interval': [lower, upper],
        **extra,
    }


class TestParseUtcOffset:
    @pytest.mark.parametrize(
        ('text', 'minutes'),
        [('+02:00', 120), ('-05:30', -330), ('+0100', 60), ('UTC', 0), ('Z', 0), ('+5', 300)],
    )
    def test_offsets(self, text, minutes):
        assert parse_utc_offset(text).utcoffset(None) == datetime.timedelta(minutes=minutes)

    @pytest.mark.parametrize('text', [None, '', 'Europe/Berlin', 'local'])
    def test_not_an_offset(self, text):
        assert parse_utc_offset(text) is None


class TestCheckInterval:
    def test_inside(self):
        ok, msg = check_interval(T0 + datetime.timedelta(seconds=3), T0, T0 + datetime.timedelta(seconds=10))
        assert ok and 'Within interval' in msg

    def test_bounds_are_inclusive(self):
        assert check_interval(T0, T0, T0)[0]

    def test_before_and_after(self):
        lower, upper = T0, T0 + datetime.timedelta(seconds=10)
        ok, msg = check_interval(T0 - datetime.timedelta(seconds=1), lower, upper)
        assert not ok and 'Before interval' in msg
        ok, msg = check_interval(upper + datetime.timedelta(seconds=1), lower, upper)
        assert not ok and 'After interval' in msg

    def test_precision_admits_truncated_value(self):
        # A whole-second artifact written at 12:00:00.4 reads 12:00:00, before a lower bound of 12:00:00.3.
        lower = T0 + datetime.timedelta(milliseconds=300)
        upper = T0 + datetime.timedelta(seconds=2)
        assert not check_interval(T0, lower, upper)[0]
        assert check_interval(T0, lower, upper, precision=1)[0]

    def test_inverted_interval_fails(self):
        ok, msg = check_interval(T0, T0 + datetime.timedelta(seconds=5), T0)
        assert not ok and 'Invalid interval' in msg


class TestYamlTimestampInterval:
    def _load(self, text: str):
        return yaml.load(text, Loader=get_custom_loader())

    def test_interval_tag(self):
        tag = self._load("!timestamp {after: '{{ t0 }}', before: '{{ t1 }}', precision: 1, localtime: true}")
        assert isinstance(tag, YamlTimestamp)
        assert tag.has_interval
        assert tag.string == '{{ t0 }}'
        assert tag.metadata == {'interval': ['{{ t0 }}', '{{ t1 }}'], 'precision': 1, 'localtime': True}

    def test_point_tag_unchanged(self):
        tag = self._load("!timestamp {timestamp: '{{ t }}', tolerance: 5}")
        assert not tag.has_interval
        assert tag.metadata == {'tolerance': [-5, 5]}

    def test_interval_needs_both_bounds(self):
        with pytest.raises(ValueError, match='both after and before'):
            YamlTimestamp(after='{{ t0 }}')


class TestBasicTestIntervalComparison:
    def test_utc_artifact_inside(self):
        ok, msg = _test_with(_interval_metadata()).compare_with_placeholder('ts_resolved', '2026-10-24T12:00:04Z')
        assert ok, msg

    def test_utc_artifact_outside(self):
        ok, msg = _test_with(_interval_metadata()).compare_with_placeholder('ts_resolved', '2026-10-24T12:00:30Z')
        assert not ok and 'After interval' in msg

    def test_unix_artifact(self):
        ok, msg = _test_with(_interval_metadata()).compare_with_placeholder('ts_resolved', str(T0.timestamp() + 1.5))
        assert ok, msg

    def test_unresolved_bound_is_an_error(self):
        # nothing was compared, so an absence test must not pass on it: PlaceholderError = ERROR
        from adarelib.testset.basictest import PlaceholderError

        metadata = _interval_metadata(interval=['{{ t0 }}', '{{ t1 }}'])
        with pytest.raises(PlaceholderError, match='save_timestamp'):
            _test_with(metadata).compare_with_placeholder('ts_resolved', '2026-10-24T12:00:04Z')

    def test_local_artifact_read_in_guest_timezone(self):
        # The artifact stores guest local time without an offset (like .trashinfo DeletionDate).
        metadata = _interval_metadata(localtime=True, format='%Y-%m-%dT%H:%M:%S', guest_utc_offset='+02:00')
        ok, msg = _test_with(metadata).compare_with_placeholder('ts_resolved', '2026-10-24T14:00:04')
        assert ok, msg

    def test_local_artifact_in_other_guest_timezone_fails(self):
        # Same wall time, but the guest was at UTC-5: the artifact is 19 hours off.
        metadata = _interval_metadata(localtime=True, format='%Y-%m-%dT%H:%M:%S', guest_utc_offset='-05:00')
        ok, _ = _test_with(metadata).compare_with_placeholder('ts_resolved', '2026-10-24T14:00:04')
        assert not ok

    def test_tolerance_path_uses_guest_timezone(self):
        metadata = {
            'type': 'timestamp',
            'raw_value': str(T0.timestamp()),
            'resolved_value': str(T0.timestamp()),
            'tolerance': [-5, 5],
            'localtime': True,
            'format': '%Y-%m-%d %H:%M:%S',
            'guest_utc_offset': '+09:00',
        }
        ok, msg = _test_with(metadata).compare_with_placeholder('ts_resolved', '2026-10-24 21:00:02')
        assert ok, msg


class TestExifDateForm:
    """``2024:01:02 03:04:06`` (EXIF) is read with its real date, never as a time of day today."""

    @pytest.mark.parametrize(
        ('text', 'expected'),
        [
            ('2024:01:02 03:04:06', datetime.datetime(2024, 1, 2, 3, 4, 6)),
            ('2024:01:02 03:04:06.250', datetime.datetime(2024, 1, 2, 3, 4, 6, 250000)),
            (
                '2024:01:02 03:04:06+02:00',
                datetime.datetime(2024, 1, 2, 3, 4, 6, tzinfo=datetime.timezone(datetime.timedelta(hours=2))),
            ),
            ('2024:01:02 03:04:06Z', datetime.datetime(2024, 1, 2, 3, 4, 6, tzinfo=UTC)),
            ('2024:01:02', datetime.datetime(2024, 1, 2)),
        ],
    )
    def test_exif_form_keeps_its_date(self, text, expected):
        assert parse_timestamp_text(text) == expected

    @pytest.mark.parametrize('text', ['2024:13:45 03:04:06', '2024:1:2 03:04:06', '2024:01:02 25:00:00'])
    def test_malformed_colon_date_is_an_error(self, text):
        with pytest.raises(ValueError, match='EXIF'):
            parse_timestamp_text(text)

    def test_other_forms_are_unchanged(self):
        assert parse_timestamp_text('2024-01-02 03:04:06') == datetime.datetime(2024, 1, 2, 3, 4, 6)
        assert parse_timestamp_text('03:04:06').time() == datetime.time(3, 4, 6)  # a bare time is still a time

    def test_placeholder_without_format_matches_the_real_date(self):
        metadata = {
            'type': 'timestamp',
            'raw_value': '2024-01-02T03:04:06Z',
            'resolved_value': '2024-01-02T03:04:06Z',
            'tolerance': [-2, 2],
        }
        ok, msg = _test_with(metadata).compare_with_placeholder('ts_resolved', '2024:01:02 03:04:06')
        assert ok, msg

    def test_placeholder_for_another_date_does_not_match(self):
        # before the fix the actual became today 03:04:06, so a test written for today passed wrongly
        today = datetime.datetime.now(UTC).replace(hour=3, minute=4, second=6, microsecond=0).isoformat()
        metadata = {'type': 'timestamp', 'raw_value': today, 'resolved_value': today, 'tolerance': [-2, 2]}
        ok, _ = _test_with(metadata).compare_with_placeholder('ts_resolved', '2024:01:02 03:04:06')
        assert not ok

    def test_malformed_actual_is_not_a_silent_wrong_date(self):
        metadata = {
            'type': 'timestamp',
            'raw_value': '2024-01-02T03:04:06Z',
            'resolved_value': '2024-01-02T03:04:06Z',
            'tolerance': [-2, 2],
        }
        ok, msg = _test_with(metadata).compare_with_placeholder('ts_resolved', '2024:13:45 03:04:06')
        assert not ok

    def test_yaml_tag_compare_reads_exif_date(self):
        tag = YamlTimestamp(timestamp='2024-01-02 03:04:06', tolerance=1)
        assert tag.compare('2024:01:02 03:04:06').success
        assert not tag.compare('2024:13:45 03:04:06').success
