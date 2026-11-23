"""Timestamp checks against an observed time interval, and guest timezones.

An artifact written by an action carries a time from the guest clock while the
action ran. Reading the guest clock right before and right after the action
(``save_timestamp``) bounds that time: ``after <= artifact <= before``. This
replaces a guessed ``tolerance`` with an interval that was measured, so a pass
means the artifact's time is consistent with the action, and a fail means it
was written outside the action (or by another clock).

``precision`` widens the interval by the artifact's storage granularity: a value
stored in whole seconds (or FAT's two seconds) can fall up to that much before
the lower bound once truncated, or after the upper bound once rounded.
"""

from __future__ import annotations

import datetime
import re

_OFFSET_RE = re.compile(r'^(?P<sign>[+-])(?P<hours>\d{1,2}):?(?P<minutes>\d{2})?$')


# EXIF / colon-date form: ``2024:01:02 03:04:06``, optionally with subseconds and a zone.
_COLON_DATE_RE = re.compile(
    r'^\s*(?P<date>\d{4}:\d{2}:\d{2})(?:[ T]+(?P<time>\d{2}:\d{2}(?::\d{2}(?:[.,]\d+)?)?)\s*(?P<zone>Z|[+-]\d{2}(?::?\d{2})?)?)?\s*$'
)
_COLON_DATE_PREFIX_RE = re.compile(r'^\s*\d{4}:\d{1,2}:\d{1,2}')


def parse_timestamp_text(text: str) -> datetime.datetime:
    """Parse a free-form timestamp string; never reads a date as "today".

    Same as ``dateutil.parser.parse`` except for the EXIF form ``YYYY:MM:DD HH:MM:SS`` (optionally
    with subseconds ``.123`` and a zone ``+02:00`` / ``Z``), which dateutil reads as a bare
    time of day on today's date. That form is parsed with its real date; a string that starts like
    such a colon date but is not a valid one (``2024:1:2 3:04``, ``2024:13:45 03:04:06``) is an error. A naive result stays naive (the caller decides which zone it is).

    :raises ValueError: the text is no timestamp, or a colon date that cannot be read safely
    """
    from dateutil import parser as _parser

    match = _COLON_DATE_RE.match(text)
    if match:
        date = match.group('date').replace(':', '-')
        time = (match.group('time') or '00:00:00').replace(',', '.')
        iso = f'{date}T{time}{match.group("zone") or ""}'
        try:
            return _parser.isoparse(iso)
        except ValueError as e:
            raise ValueError(f'cannot read {text!r} as an EXIF-style date (YYYY:MM:DD HH:MM:SS): {e}') from e
    if _COLON_DATE_PREFIX_RE.match(text):
        raise ValueError(
            f'cannot read {text!r}: it looks like an EXIF date (YYYY:MM:DD HH:MM:SS) but is malformed; '
            'a date read as a time of day would be silently wrong'
        )
    return _parser.parse(text)


def parse_utc_offset(text: str | None) -> datetime.timezone | None:
    """Parse a fixed UTC offset such as '+02:00', '-0530', 'UTC' or 'Z'; None if not an offset."""
    if not text:
        return None
    value = str(text).strip()
    if value.upper() in ('UTC', 'Z', 'GMT'):
        return datetime.timezone.utc
    match = _OFFSET_RE.match(value)
    if not match:
        return None
    delta = datetime.timedelta(hours=int(match['hours']), minutes=int(match['minutes'] or 0))
    if match['sign'] == '-':
        delta = -delta
    return datetime.timezone(delta)


def check_interval(
    actual: datetime.datetime,
    lower: datetime.datetime,
    upper: datetime.datetime,
    precision: float = 0.0,
) -> tuple[bool, str]:
    """Check ``lower - precision <= actual <= upper + precision`` (all tz-aware)."""
    if upper < lower:
        return False, f"Invalid interval: upper bound {upper.isoformat()} is before lower bound {lower.isoformat()}"
    slack = datetime.timedelta(seconds=abs(precision))
    before_lower = (lower - actual).total_seconds()
    after_upper = (actual - upper).total_seconds()
    interval = f"[{lower.isoformat()}, {upper.isoformat()}] (precision {abs(precision)}s)"
    if actual < lower - slack:
        return False, f"Before interval: {actual.isoformat()} is {before_lower:.3f}s before {interval}"
    if actual > upper + slack:
        return False, f"After interval: {actual.isoformat()} is {after_upper:.3f}s after {interval}"
    return True, f"Within interval: {actual.isoformat()} in {interval}"
