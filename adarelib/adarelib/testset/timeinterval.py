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
