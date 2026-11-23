"""Ordered comparison of two values (numbers or timestamps) for testfunctions.

Value testfunctions compare by equality or regex; this module adds ``greater``/``less``
style comparisons, a tolerance and an offset, for numbers and for points in time:

* ``value 3 greater 2``
* ``value 2026-01-01T10:00:05Z equals 2026-01-01T10:00:00Z`` with ``tolerance=10`` (seconds)
* ``A less B`` (A earlier than B) when both sides come from the same file

Standard library only and importable on Python 3.10 (the guest's floor). Every problem with
the parameters or with a value that is no number or timestamp raises :class:`OrderingError`
(a ``ValueError``), which callers report as ERROR: a value of the wrong kind says the check
looked at the wrong field, not that the claim is false.
"""

import datetime
import decimal
import email.utils
import re
from dataclasses import dataclass
from typing import Any

ORDER_COMPARISONS = ('equals', 'not_equals', 'greater', 'less', 'greater_equal', 'less_equal')
VALUE_TYPES = ('auto', 'number', 'timestamp')
_SYMBOLS = {
    'equals': '==',
    'not_equals': '!=',
    'greater': '>',
    'less': '<',
    'greater_equal': '>=',
    'less_equal': '<=',
}
_NUMBER = re.compile(r'[+-]?(\d+(\.\d*)?|\.\d+)([eE][+-]?\d+)?')


class OrderingError(ValueError):
    """A parameter or value the comparison cannot interpret."""


@dataclass(frozen=True)
class TimeFormat:
    """How to read a timestamp value.

    :param time_format: ``strptime`` format; without it ISO 8601 (``Z`` allowed) and RFC 2822
                        dates (``Tue, 03 Feb 2026 10:00:00 GMT``) are read
    :param epoch: read a number as a count of ``unit`` since 1 January of this year
                  (1970, 1601 or 2001); without it a number is no timestamp
    :param unit: ``s``, ``ms``, ``us``, ``ns`` or ``100ns`` (with ``epoch``)
    :param utc_offset: zone of a value without one, e.g. ``+02:00``; default UTC
    """

    time_format: str | None = None
    epoch: int | None = None
    unit: str = 's'
    utc_offset: str | None = None

    @property
    def is_set(self) -> bool:
        return self.time_format is not None or self.epoch is not None


def _is_number_type(value: Any) -> bool:
    return isinstance(value, (int, float, decimal.Decimal)) and not isinstance(value, bool)


def to_number(value: Any) -> decimal.Decimal:
    """``value`` as an exact decimal (an int, a float or a numeric string).

    :raises OrderingError: a bool, NaN/infinity or anything that is no number
    """
    if isinstance(value, bool):
        raise OrderingError(f'{value!r} is no number')
    if _is_number_type(value):
        number = decimal.Decimal(repr(value)) if isinstance(value, float) else decimal.Decimal(value)
    elif isinstance(value, (str, bytes)):
        text = value.decode('ascii', 'replace') if isinstance(value, bytes) else value
        if not _NUMBER.fullmatch(text.strip()):
            raise OrderingError(f'{value!r} is no number')
        number = decimal.Decimal(text.strip())
    else:
        raise OrderingError(f'{value!r} is no number')
    if not number.is_finite():
        raise OrderingError(f'{value!r} is no finite number')
    return number


def _zone(utc_offset: str | None) -> datetime.timezone:
    if utc_offset is None:
        return datetime.timezone.utc
    from adarelib.testset.timeinterval import parse_utc_offset

    zone = parse_utc_offset(utc_offset)
    if zone is None:
        raise OrderingError(f'invalid utc_offset {utc_offset!r} (expected e.g. +02:00)')
    return zone


def to_datetime(value: Any, fmt: TimeFormat | None = None) -> datetime.datetime:
    """``value`` as a zone-aware datetime.

    :raises OrderingError: the value is no timestamp in the given format
    """
    fmt = fmt or TimeFormat()
    zone = _zone(fmt.utc_offset)
    if isinstance(value, datetime.datetime):
        dt = value
    elif isinstance(value, datetime.date):
        dt = datetime.datetime(value.year, value.month, value.day)
    elif fmt.epoch is not None and (
        _is_number_type(value) or (isinstance(value, str) and _NUMBER.fullmatch(value.strip()))
    ):
        from adarelib.testset.yaml.customtags import numeric_timestamp_to_datetime

        value = format(value, 'f') if isinstance(value, decimal.Decimal) else value
        try:
            dt = numeric_timestamp_to_datetime(value, fmt.epoch, fmt.unit)
        except ValueError as e:
            raise OrderingError(str(e)) from e
    elif isinstance(value, str):
        dt = _parse_text_timestamp(value.strip(), fmt.time_format)
    else:
        raise OrderingError(f'{value!r} is no timestamp (a number needs timestamp_epoch)')
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=zone)
    return dt


def _parse_text_timestamp(text: str, time_format: str | None) -> datetime.datetime:
    if time_format is not None:
        try:
            return datetime.datetime.strptime(text, time_format)
        except ValueError as e:
            raise OrderingError(f'{text!r} does not match time_format {time_format!r}: {e}') from e
    iso = text[:-1] + '+00:00' if text.endswith(('Z', 'z')) else text
    try:
        return datetime.datetime.fromisoformat(iso)
    except ValueError:
        pass
    try:
        dt = email.utils.parsedate_to_datetime(text)
    except (TypeError, ValueError, IndexError):
        dt = None
    if dt is None:
        raise OrderingError(f'{text!r} is no ISO 8601 or RFC 2822 timestamp (set time_format for other forms)')
    return dt


def _resolve_type(value_type: str, actual: Any, expected: Any, fmt: TimeFormat) -> str:
    if value_type not in VALUE_TYPES:
        raise OrderingError(f"invalid value_type {value_type!r} (allowed: {', '.join(VALUE_TYPES)})")
    if value_type != 'auto':
        return value_type
    if fmt.is_set:
        return 'timestamp'
    try:
        to_number(actual)
        to_number(expected)
        return 'number'
    except OrderingError:
        pass
    try:
        to_datetime(actual, fmt)
        to_datetime(expected, fmt)
        return 'timestamp'
    except OrderingError:
        pass
    raise OrderingError(f'cannot compare {actual!r} with {expected!r}: not both numbers or both timestamps')


def parameter_errors(
    comparison_type: str, value_type: str = 'auto', tolerance: Any = None, offset: Any = None
) -> list[str]:
    """Problems with the comparison parameters; empty when they are valid."""
    errors = []
    if comparison_type not in ORDER_COMPARISONS:
        errors.append(f"invalid comparison_type {comparison_type!r} (allowed: {', '.join(ORDER_COMPARISONS)})")
    if value_type not in VALUE_TYPES:
        errors.append(f"invalid value_type {value_type!r} (allowed: {', '.join(VALUE_TYPES)})")
    for name, number in (('tolerance', tolerance), ('offset', offset)):
        if number is None:
            continue
        try:
            parsed = to_number(number)
        except OrderingError:
            errors.append(f'{name} must be a number, got {number!r}')
            continue
        if name == 'tolerance' and parsed < 0:
            errors.append(f'tolerance must not be negative, got {number!r}')
    if tolerance is not None and comparison_type not in ('equals', 'not_equals'):
        errors.append(f'tolerance only applies to equals/not_equals, not {comparison_type!r}')
    return errors


def compare(
    actual: Any,
    expected: Any,
    comparison_type: str = 'equals',
    value_type: str = 'auto',
    tolerance: Any = None,
    offset: Any = None,
    time_format: TimeFormat | None = None,
) -> tuple[bool, str]:
    """Whether ``actual <comparison_type> expected + offset`` holds, with a message.

    Numbers compare exactly (as decimals); timestamps compare as points in time, with
    ``offset`` and ``tolerance`` in seconds. ``equals`` with ``tolerance`` holds when the
    difference is at most ``tolerance``; ``not_equals`` when it is larger.

    :raises OrderingError: invalid parameters, or a value that is not of the compared kind
    """
    errors = parameter_errors(comparison_type, value_type, tolerance, offset)
    if errors:
        raise OrderingError('; '.join(errors))
    fmt = time_format or TimeFormat()
    kind = _resolve_type(value_type, actual, expected, fmt)
    shift = to_number(offset) if offset is not None else decimal.Decimal(0)
    tol = to_number(tolerance) if tolerance is not None else decimal.Decimal(0)

    if kind == 'number':
        a, b = to_number(actual), to_number(expected) + shift
        diff = a - b
        shown_a, shown_b = format(a, 'f'), format(b, 'f')
    else:
        a_dt = to_datetime(actual, fmt)
        b_dt = to_datetime(expected, fmt) + datetime.timedelta(seconds=float(shift))
        diff = decimal.Decimal(repr((a_dt - b_dt).total_seconds()))
        shown_a, shown_b = a_dt.isoformat(), b_dt.isoformat()

    holds = {
        'equals': abs(diff) <= tol,
        'not_equals': abs(diff) > tol,
        'greater': diff > 0,
        'less': diff < 0,
        'greater_equal': diff >= 0,
        'less_equal': diff <= 0,
    }[comparison_type]
    unit = ' s' if kind == 'timestamp' else ''
    detail = f'{shown_a} {_SYMBOLS[comparison_type]} {shown_b}'
    if tolerance is not None:
        detail += f' (tolerance {format(tol, "f")}{unit}, difference {format(diff, "f")}{unit})'
    return holds, f'{kind} {detail} {"holds" if holds else "does not hold"}'
