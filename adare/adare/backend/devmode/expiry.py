"""Opt-in expiry of forgotten dev sessions.

A stopped dev session keeps its VM disk (an overlay, or a full copy for sessions
from before per-run overlays) until ``adare dev remove``. With
``ADARE_DEV_SESSION_MAX_AGE_DAYS`` set (environment, else the same key in the user
config), every experiment run and ``adare vm prune --force`` remove stopped or
crashed sessions unused for longer than that. Unset (the default), nothing expires:
a stopped session can still be resumed, so removing it is otherwise the user's call.

Never removed: running sessions, and any session whose VM is still running.
"""

import logging
import os
from datetime import UTC, datetime, timedelta

log = logging.getLogger(__name__)

MAX_AGE_ENV = 'ADARE_DEV_SESSION_MAX_AGE_DAYS'


def max_age() -> timedelta | None:
    """The configured age limit, or None when expiry is off."""
    raw = os.environ.get(MAX_AGE_ENV)
    source = MAX_AGE_ENV
    if raw is None or not str(raw).strip():
        try:
            from adare.config import userconfig

            raw = userconfig.get(MAX_AGE_ENV)
            source = f"{MAX_AGE_ENV} (user config)"
        except (OSError, ValueError, KeyError, TypeError) as exc:  # config must never block a run
            log.debug(f"Could not read {MAX_AGE_ENV} from user config: {exc}")
            return None
    if raw is None or not str(raw).strip():
        return None
    try:
        days = float(str(raw).strip())
    except ValueError:
        log.warning(f"{source}={raw!r} is not a number of days; dev sessions do not expire")
        return None
    if days <= 0:
        log.warning(f"{source}={raw!r} must be > 0; dev sessions do not expire")
        return None
    return timedelta(days=days)


def _vm_running(vm_name: str | None) -> bool:
    if not vm_name:
        return False
    from adare.hypervisor.qemu.run_resources import is_domain_running

    return is_domain_running(vm_name)


def expired_sessions(limit: timedelta) -> list:
    """Stopped/crashed sessions unused for longer than ``limit`` whose VM is not running."""
    from adare.database.api.devmode import DevModeApi

    # updated_at is stored as naive UTC (SQLite CURRENT_TIMESTAMP)
    cutoff = datetime.now(UTC).replace(tzinfo=None) - limit
    with DevModeApi() as api:
        candidates = [
            s
            for s in api.list_sessions()
            if s.status in ('stopped', 'crashed') and (s.updated_at or s.created_at) <= cutoff
        ]
    return [s for s in candidates if not _vm_running(s.vm_name)]


def remove_expired_dev_sessions(dry_run: bool = False) -> list[str]:
    """Remove expired dev sessions (no-op unless the limit is set). Returns their ids.

    Synchronous: it goes through the devmode service, which runs its own event loop,
    so async callers use ``asyncio.to_thread``.
    """
    limit = max_age()
    if limit is None:
        return []
    from adare.database.exceptions import DatabaseError

    try:
        sessions = expired_sessions(limit)
    except DatabaseError as e:
        log.warning(f"Could not read dev sessions, none expired: {e}")
        return []
    if dry_run or not sessions:
        return [s.session_id for s in sessions]

    from adare.api import AdareAPI
    from adare.core.dto.devmode import DevSessionStopRequest

    api = AdareAPI()
    removed = []
    for s in sessions:
        result = api.devmode.stop_session(DevSessionStopRequest(session_id=s.session_id, remove_resources=True))
        if result.success:
            removed.append(s.session_id)
            log.info(f"Removed dev session {s.session_id}: unused for more than {limit.days} day(s) ({MAX_AGE_ENV})")
        else:
            log.warning(f"Could not remove expired dev session {s.session_id}: {result.error}")
    return removed
