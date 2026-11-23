"""Time zones of timestamp variables, and the error a bad variable raises.

Split out of :mod:`adarelib.common.variables`, which re-exports everything here.
"""

from __future__ import annotations

import datetime
import re
from typing import Any

import dateutil.tz


class ValidationError(ValueError):
    """Raised when variable validation fails.

    A ``ValueError`` so that callers loading a playbook (which already report ``ValueError`` as a
    playbook error) report a bad variable too instead of crashing.
    """


_UTC_OFFSET_RE = re.compile(r'([+-])(\d{2})(?::?(\d{2}))?')


def _apply_timezone(dt: datetime.datetime, timezone_str: str) -> datetime.datetime:
    """Give a naive datetime the time zone ``timezone_str`` (the wall-clock time is kept).

    ``timezone_str`` is a UTC offset (``+02:00``, ``-0500``, ``+02``) or a zone name
    (``Europe/Berlin``, ``UTC``). An aware datetime already has its zone and is returned unchanged.

    :raises ValidationError: the offset is malformed or out of range, or the zone name is unknown
    """
    if dt.tzinfo is not None:
        return dt
    if timezone_str.startswith(('+', '-')):
        match = _UTC_OFFSET_RE.fullmatch(timezone_str)
        if not match:
            raise ValidationError(f"Invalid timezone offset '{timezone_str}' (expected e.g. +02:00 or -0500)")
        sign, hours, minutes = match.groups()
        offset = datetime.timedelta(hours=int(hours), minutes=int(minutes or 0))
        try:
            tz = datetime.timezone(-offset if sign == '-' else offset)
        except ValueError as e:  # the offset must be strictly between -24h and +24h
            raise ValidationError(f"Invalid timezone offset '{timezone_str}': {e}") from e
    else:
        tz = dateutil.tz.gettz(timezone_str)
        if tz is None:
            raise ValidationError(f"Unknown timezone '{timezone_str}'")
    return dt.replace(tzinfo=tz)


def check_timezone(timezone_str: Any) -> None:
    """:raises ValidationError: ``timezone_str`` is not a UTC offset or known zone name"""
    if not isinstance(timezone_str, str):
        raise ValidationError(f"Timezone must be a string, got {timezone_str!r}")
    _apply_timezone(datetime.datetime(2000, 1, 1), timezone_str)


def check_timestamp_format(format_str: Any) -> None:
    """:raises ValidationError: ``format_str`` is not a string"""
    if not isinstance(format_str, str):
        raise ValidationError(f"Timestamp format must be a string, got {format_str!r}")
