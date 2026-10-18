"""Timing of the synthetic mouse click sent over QMP."""

import logging
import os

log = logging.getLogger(__name__)

CLICK_SETTLE_ENV = "ADARE_CLICK_SETTLE_MS"
DEFAULT_CLICK_SETTLE_MS = 10.0  # the long-standing gap between pointer move and button press
MAX_CLICK_SETTLE_MS = 5000.0


def click_settle_seconds() -> float:
    """Gap between the pointer move and the button press, in seconds.

    Read from ``ADARE_CLICK_SETTLE_MS`` on every click (so a dev session can change it).
    Unset, empty, non-numeric or out-of-range values give the default of 10 ms.
    """
    raw = os.environ.get(CLICK_SETTLE_ENV, "").strip()
    if not raw:
        return DEFAULT_CLICK_SETTLE_MS / 1000.0
    try:
        ms = float(raw)
    except ValueError:
        log.warning(f"{CLICK_SETTLE_ENV}={raw!r} is not a number; using {DEFAULT_CLICK_SETTLE_MS} ms")
        return DEFAULT_CLICK_SETTLE_MS / 1000.0
    if not 0.0 <= ms <= MAX_CLICK_SETTLE_MS:
        log.warning(
            f"{CLICK_SETTLE_ENV}={raw!r} is outside 0-{MAX_CLICK_SETTLE_MS:g} ms; using {DEFAULT_CLICK_SETTLE_MS} ms"
        )
        return DEFAULT_CLICK_SETTLE_MS / 1000.0
    return ms / 1000.0
