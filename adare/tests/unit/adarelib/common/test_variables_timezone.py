"""Time zone, format and error handling of timestamp variables (adarelib.common.variables).

A naive timestamp plus ``timezone:`` metadata becomes a Unix timestamp; an unusable zone, a
timestamp that cannot be parsed or a format that cannot be applied raises ``ValidationError``
instead of leaving a naive datetime or returning the raw text.
"""

import datetime

import pytest

from adarelib.common.variables import (
    TimestampMetadata,
    ValidationError,
    Variable,
    VariableRegistry,
    VariableType,
    _apply_timezone,
)

pytestmark = pytest.mark.unit

NAIVE = "2024-06-01 12:00:00"
UTC = datetime.timezone.utc
NOON_UTC = datetime.datetime(2024, 6, 1, 12, 0, tzinfo=UTC).timestamp()
TEN_UTC = datetime.datetime(2024, 6, 1, 10, 0, tzinfo=UTC).timestamp()
NINE_UTC = datetime.datetime(2024, 6, 1, 9, 0, tzinfo=UTC).timestamp()


def _ts(value, **metadata):
    return Variable(value, VariableType.TIMESTAMP, metadata=metadata)


def _resolved(var: Variable):
    registry = VariableRegistry()
    registry.add("ts", var)
    return registry.to_execution_context()["ts"]


# ---------------------------------------------------------------------------
# Construction (_validate_and_coerce)
# ---------------------------------------------------------------------------


class TestTimestampConstruction:
    def test_named_zone_gives_unix_timestamp(self):
        assert _ts(NAIVE, timezone="Europe/Berlin").value == TEN_UTC  # CEST = UTC+2

    def test_utc_zone(self):
        assert _ts(NAIVE, timezone="UTC").value == NOON_UTC

    def test_no_zone_stays_naive(self):
        assert _ts(NAIVE).value == datetime.datetime(2024, 6, 1, 12, 0)

    @pytest.mark.parametrize("zone", ["+02:00", "+0200", "+02"])
    def test_positive_offset(self, zone):
        assert _ts(NAIVE, timezone=zone).value == TEN_UTC

    @pytest.mark.parametrize("zone", ["-03:00", "-0300"])
    def test_negative_offset(self, zone):
        assert _ts(NAIVE, timezone=zone).value == datetime.datetime(2024, 6, 1, 15, 0, tzinfo=UTC).timestamp()

    def test_offset_with_minutes(self):
        assert _ts(NAIVE, timezone="+05:30").value == datetime.datetime(2024, 6, 1, 6, 30, tzinfo=UTC).timestamp()

    def test_aware_string_ignores_zone_metadata(self):
        # The zone is applied to naive values only; an offset in the text wins
        assert _ts("2024-06-01T12:00:00+02:00", timezone="Europe/London").value == TEN_UTC

    def test_aware_datetime_becomes_unix_timestamp(self):
        assert _ts(datetime.datetime(2024, 6, 1, 12, tzinfo=UTC)).value == NOON_UTC

    def test_naive_datetime_value_is_kept(self):
        naive = datetime.datetime(2024, 6, 1, 12)
        assert _ts(naive, timezone="Europe/Berlin").value == naive

    def test_unknown_zone_raises(self):
        with pytest.raises(ValidationError, match="Mars/Olympus"):
            _ts(NAIVE, timezone="Mars/Olympus")

    @pytest.mark.parametrize("zone", ["+25:00", "+99:99", "+2"])
    def test_bad_offset_raises(self, zone):
        with pytest.raises(ValidationError, match="timezone"):
            _ts(NAIVE, timezone=zone)

    def test_unknown_zone_on_aware_value_raises_at_load(self):
        # The zone is unused for an aware value, but a wrong declaration is still an error
        with pytest.raises(ValidationError, match="Mars/Olympus"):
            _ts("2024-06-01T12:00:00+02:00", timezone="Mars/Olympus")

    def test_non_string_format_raises_at_load(self):
        with pytest.raises(ValidationError, match="format must be a string"):
            _ts(NAIVE, timezone="UTC", format=5)

    def test_unparsable_timestamp_raises(self):
        with pytest.raises(ValidationError, match="Invalid timestamp"):
            _ts("not a date at all")

    def test_validation_error_is_a_value_error(self):
        # Callers that load playbooks catch ValueError, so a bad variable is reported as an
        # ordinary playbook error rather than crashing the run
        assert issubclass(ValidationError, ValueError)

    def test_conversion_error_message_is_not_double_wrapped(self):
        with pytest.raises(ValidationError) as exc:
            Variable("abc", VariableType.INTEGER)
        assert str(exc.value).startswith("Cannot convert 'abc' to integer")
        with pytest.raises(ValidationError) as exc:
            Variable("[unclosed", VariableType.REGEX)
        assert str(exc.value).startswith("Invalid regex")


# ---------------------------------------------------------------------------
# _apply_timezone
# ---------------------------------------------------------------------------


class TestApplyTimezone:
    def test_replaces_tzinfo_of_a_naive_datetime(self):
        result = _apply_timezone(datetime.datetime(2024, 6, 1, 12), "+02:00")
        assert result.utcoffset() == datetime.timedelta(hours=2)
        assert result.replace(tzinfo=None) == datetime.datetime(2024, 6, 1, 12)  # wall time kept

    def test_named_zone(self):
        result = _apply_timezone(datetime.datetime(2024, 1, 1, 12), "Europe/Berlin")
        assert result.utcoffset() == datetime.timedelta(hours=1)  # CET in winter

    def test_aware_datetime_is_returned_unchanged(self):
        aware = datetime.datetime(2024, 6, 1, 12, tzinfo=UTC)
        assert _apply_timezone(aware, "Europe/Berlin") is aware

    def test_unknown_zone_raises(self):
        with pytest.raises(ValidationError, match="Unknown timezone 'Nowhere/Land'"):
            _apply_timezone(datetime.datetime(2024, 6, 1), "Nowhere/Land")

    def test_offset_out_of_range_raises(self):
        with pytest.raises(ValidationError, match="Invalid timezone offset"):
            _apply_timezone(datetime.datetime(2024, 6, 1), "+24:00")


# ---------------------------------------------------------------------------
# Resolution (_get_variable_resolved_value via to_execution_context)
# ---------------------------------------------------------------------------


class TestTimestampResolution:
    def test_unix_timestamp_is_returned_as_is(self):
        assert _resolved(_ts(NAIVE, timezone="Europe/Berlin")) == TEN_UTC

    def test_naive_datetime_is_an_iso_string(self):
        assert _resolved(_ts(NAIVE)) == "2024-06-01T12:00:00"

    def test_format_applies_to_unix_timestamp(self):
        var = _ts(NAIVE, timezone="Europe/Berlin")
        var.structured_metadata = TimestampMetadata(timezone="Europe/Berlin", format_str="%Y-%m-%d %H:%M")
        assert _resolved(var) == "2024-06-01 10:00"  # formatted in UTC

    def test_format_applies_to_naive_datetime(self):
        var = _ts(NAIVE, format="%d.%m.%Y")
        assert _resolved(var) == "01.06.2024"

    def test_string_value_with_named_zone(self):
        var = _ts(NAIVE)
        var.value = NAIVE  # a value assigned after construction is resolved from text
        var.metadata = {"timezone": "Europe/Berlin"}
        assert _resolved(var) == TEN_UTC

    def test_string_value_with_offset(self):
        var = _ts(NAIVE)
        var.value = NAIVE
        var.metadata = {"timezone": "-03:00"}
        assert _resolved(var) == datetime.datetime(2024, 6, 1, 15, 0, tzinfo=UTC).timestamp()

    def test_string_value_zone_from_structured_metadata(self):
        var = _ts(NAIVE)
        var.value = NAIVE
        var.structured_metadata = TimestampMetadata(timezone="+03:00")
        assert _resolved(var) == NINE_UTC

    def test_string_value_without_zone_is_iso(self):
        var = _ts(NAIVE)
        var.value = NAIVE
        assert _resolved(var) == "2024-06-01T12:00:00"

    def test_string_value_unknown_zone_raises(self):
        var = _ts(NAIVE)
        var.value = NAIVE
        var.metadata = {"timezone": "Mars/Olympus"}
        with pytest.raises(ValidationError, match="'ts'.*Mars/Olympus"):
            _resolved(var)

    def test_string_value_bad_offset_raises(self):
        var = _ts(NAIVE)
        var.value = NAIVE
        var.metadata = {"timezone": "+2"}
        with pytest.raises(ValidationError, match="'ts'"):
            _resolved(var)

    def test_unparsable_string_value_raises_instead_of_returning_the_text(self):
        var = _ts(NAIVE)
        var.value = "not a date at all"
        with pytest.raises(ValidationError, match="'ts'.*not a date at all"):
            _resolved(var)

    def test_unix_timestamp_out_of_range_raises(self):
        var = _ts(NAIVE, timezone="UTC")
        var.value = 1e20
        with pytest.raises(ValidationError, match="'ts'"):
            _resolved(var)

    def test_unusable_format_raises(self):
        var = _ts(NAIVE, timezone="UTC")
        var.structured_metadata = TimestampMetadata(timezone="UTC", format_str=5)  # not a str
        with pytest.raises(ValidationError, match="format.*'ts'|'ts'.*format"):
            _resolved(var)


# ---------------------------------------------------------------------------
# Jinja timezone / format filters
# ---------------------------------------------------------------------------


class TestTimestampFilters:
    def _filters(self, var: Variable):
        registry = VariableRegistry()
        registry.add("ts", var)
        return registry, TimestampMetadata().get_jinja_filters(registry)

    def test_good_zone_is_captured(self):
        var = _ts("2024-06-01T12:00:00+00:00")
        _registry, filters = self._filters(var)
        assert filters["timezone"](var.value, "Europe/Berlin") == var.value
        assert var.metadata["timezone"] == "Europe/Berlin"

    def test_bad_zone_raises_and_leaves_the_variable_alone(self):
        var = _ts("2024-06-01T12:00:00+00:00")
        registry, filters = self._filters(var)
        with pytest.raises(ValidationError, match="Mars/Olympus"):
            filters["timezone"](var.value, "Mars/Olympus")
        assert "timezone" not in var.metadata
        assert registry.to_execution_context()["ts"] == NOON_UTC  # later resolutions still work

    def test_non_string_format_raises_and_leaves_the_variable_alone(self):
        var = _ts("2024-06-01T12:00:00+00:00")
        _registry, filters = self._filters(var)
        with pytest.raises(ValidationError, match="format must be a string"):
            filters["format"](var.value, 5)
        assert "format" not in var.metadata

    def test_names_stay_importable_from_variables(self):
        from adarelib.common import timezones, variables

        assert variables.ValidationError is timezones.ValidationError
        assert variables._apply_timezone is timezones._apply_timezone
