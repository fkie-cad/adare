"""Host settings: limits that keep ADARE from overloading this machine.

Each setting resolves ``environment variable > ~/.adare/settings.json > default``.
The file is managed with ``adare system settings set|unset``, so a limit is set
once for the host instead of being exported in every shell. For backward
compatibility a value in the active ``config.json`` profile (where
``ADARE_MAX_VMS`` used to be read from) still counts, below the settings file.

Reads never raise: a missing, corrupt or invalid value falls back to the next
source with a warning.
"""

import json
import logging
import os
from dataclasses import dataclass
from pathlib import Path

from .configdirectory import APPDATA_DIR

log = logging.getLogger(__name__)

_FILENAME = 'settings.json'


@dataclass(frozen=True)
class Setting:
    name: str
    kind: type  # int or float
    default: float | int | None  # None = off
    minimum: float
    description: str
    exclusive_minimum: bool = False


SETTINGS: dict[str, Setting] = {
    s.name: s
    for s in (
        Setting('ADARE_MAX_VMS', int, 20, 1, 'VMs that may run at once across all adare processes'),
        Setting('ADARE_VM_SLOT_TIMEOUT', float, 30.0, 0, 'Seconds a run waits for a free VM slot'),
        Setting(
            'ADARE_MIN_FREE_DISK_GB',
            float,
            10.0,
            0,
            'GiB that must be free on the project and ADARE disks before a run starts (0 = no check)',
        ),
        Setting(
            'ADARE_DEV_SESSION_MAX_AGE_DAYS',
            float,
            None,
            0,
            'Remove stopped dev sessions unused for longer than this many days (unset = never)',
            exclusive_minimum=True,
        ),
        Setting(
            'ADARE_TEST_RUNS_KEEP',
            int,
            10,
            -1,
            'Test-mode (fake) runs kept per experiment and environment; older finished ones are removed after '
            'each test run, at most 5 at a time (the run that just finished counts, so 0 keeps only it; '
            'the newest successful run is always kept; -1 = off)',
        ),
    )
}


def path() -> Path:
    return Path(APPDATA_DIR) / _FILENAME


def _load() -> dict:
    try:
        data = json.loads(path().read_text())
    except FileNotFoundError:
        return {}
    except (OSError, ValueError) as e:
        log.warning(f"Ignoring unreadable {path()}: {e}")
        return {}
    return data if isinstance(data, dict) else {}


def parse(name: str, raw) -> float | int:
    """Convert and check a raw value for ``name``; raises ``ValueError`` with a readable message."""
    setting = SETTINGS[name]
    try:
        number = float(str(raw).strip())
    except ValueError:
        raise ValueError(f"{name} must be a number, got {raw!r}") from None
    if setting.kind is int and not number.is_integer():
        raise ValueError(f"{name} must be a whole number, got {raw!r}")
    value: float | int = int(number) if setting.kind is int else number
    too_small = value <= setting.minimum if setting.exclusive_minimum else value < setting.minimum
    if too_small:
        bound = f"> {setting.minimum:g}" if setting.exclusive_minimum else f">= {setting.minimum:g}"
        raise ValueError(f"{name} must be {bound}, got {raw!r}")
    return value


def _legacy_profile_value(name: str):
    try:
        from . import userconfig

        return userconfig.get(name)
    except (OSError, ValueError, KeyError, TypeError) as e:  # config must never block a run
        log.debug(f"Could not read {name} from config.json: {e}")
        return None


def resolve(name: str) -> tuple[float | int | None, str]:
    """``(value, source)`` with source one of environment, settings, config profile, default."""
    for source, raw in (
        ('environment', os.environ.get(name)),
        ('settings', _load().get(name)),
        ('config profile', _legacy_profile_value(name)),
    ):
        if raw is None or not str(raw).strip():
            continue
        try:
            return parse(name, raw), source
        except ValueError as e:
            log.warning(f"Ignoring {source} value: {e}")
    return SETTINGS[name].default, 'default'


def get(name: str) -> float | int | None:
    return resolve(name)[0]


def get_number(name: str) -> float:
    """For settings that always have a value (a default other than None)."""
    value = get(name)
    if value is None:
        raise KeyError(f"{name} has no default; use get()")
    return float(value)


def set_value(name: str, raw) -> float | int:
    """Validate and store ``name`` in the settings file; returns the stored value."""
    value = parse(name, raw)
    data = _load()
    data[name] = value
    _save(data)
    return value


def unset(name: str) -> bool:
    """Remove ``name`` from the settings file; False if it was not set there."""
    data = _load()
    if name not in data:
        return False
    del data[name]
    _save(data)
    return True


def _save(data: dict) -> None:
    target = path()
    target.parent.mkdir(parents=True, exist_ok=True)
    tmp = target.with_suffix('.json.tmp')
    tmp.write_text(json.dumps(data, indent=2, sort_keys=True) + '\n')
    tmp.replace(target)
