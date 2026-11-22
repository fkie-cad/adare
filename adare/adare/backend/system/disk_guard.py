"""Refuse to start a run when a disk it writes to is nearly full.

A run grows its VM overlay and writes its artifacts while it executes; on a full
disk QEMU pauses the guest or the run dies half-way, and the host suffers with it.
The limit is the ``ADARE_MIN_FREE_DISK_GB`` setting (``adare system settings``,
default 10 GiB free per filesystem; 0 switches the check off).
"""

import logging
import shutil
from pathlib import Path

from adare.exceptions import LoggedErrorException

log = logging.getLogger(__name__)

MIN_FREE_ENV = 'ADARE_MIN_FREE_DISK_GB'


class LowDiskSpaceError(LoggedErrorException):
    """A filesystem a run writes to has less free space than ADARE_MIN_FREE_DISK_GB."""


def min_free_bytes() -> int:
    """``ADARE_MIN_FREE_DISK_GB`` (environment > ``adare system settings`` > 10) in bytes."""
    from adare.config import settings

    return int(settings.get_number(MIN_FREE_ENV) * 1024**3)


def ensure_free_disk(paths: list[Path]) -> None:
    """Raise :class:`LowDiskSpaceError` if a filesystem holding one of ``paths`` is below the limit."""
    limit = min_free_bytes()
    if not limit:
        return
    low: list[str] = []
    seen: set[int] = set()
    for path in paths:
        probe = path
        while not probe.exists() and probe != probe.parent:
            probe = probe.parent
        try:
            device = probe.stat().st_dev
            free = shutil.disk_usage(probe).free
        except OSError as e:
            log.debug(f"free space of {probe} unavailable: {e}")
            continue
        if device in seen:
            continue
        seen.add(device)
        if free < limit:
            low.append(f"{path} ({free / 1024**3:.1f} GiB free)")
    if low:
        raise LowDiskSpaceError(
            log,
            f"Not starting the run: less than {limit / 1024**3:g} GiB free on " + ', '.join(low),
            possible_solutions=[
                'See where the space goes: adare system storage',
                'Remove old stopped dev sessions (each keeps a full VM disk): '
                'adare dev remove --stopped --older-than 14d',
                'Reclaim what crashed runs left behind: adare vm prune --force',
                f'Lower or disable the limit: adare system settings set {MIN_FREE_ENV} 0',
            ],
        )
