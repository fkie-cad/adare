"""Persisted per-machine user configuration, organised into named profiles.

A JSON store at ``~/.adare/config.json`` holding several named profiles of
``ADARE_*`` settings plus an ``active`` pointer, so a provider can be configured
once and swapped without exporting environment variables::

    {
      "active": "cloud-235b",
      "profiles": {
        "cloud-235b": {"ADARE_VLLM_BASE_URL": "...", "ADARE_VLLM_MODEL": "..."},
        "local":      {"ADARE_VLLM_BASE_URL": "http://localhost:8000/v1"}
      }
    }

:func:`get` returns a key from the **active** profile, so ``config/server.py``
keeps its one-line ``env var > config file > code default`` resolution unchanged.

Profiles may hold secrets (e.g. ``ADARE_VLLM_API_KEY``), so the file is written
``0600``. Reads never raise: a missing or corrupt file resolves to an empty store
and callers fall through to code defaults.

The flat ``{ADARE_*: value}`` format written by earlier versions is migrated on
first read into ``profiles={"default": <those keys>}`` with ``active="default"``.
"""

import json
import logging
import os

from .configdirectory import APPDATA_DIR
from .exceptions import ConfigDirectoryError

log = logging.getLogger(__name__)

_CONFIG_FILENAME = 'config.json'
# Cache the parsed store for the life of the process. A CLI call is a fresh
# process, so writes are always seen by the next command.
_cache: dict | None = None


def path():
    """Absolute path of the config file (``~/.adare/config.json``)."""
    if not APPDATA_DIR:
        raise ConfigDirectoryError(log, 'the config directory could not be set')
    return APPDATA_DIR / _CONFIG_FILENAME


def _empty() -> dict:
    return {'active': None, 'profiles': {}}


def _normalise(data) -> dict:
    """Coerce any parsed JSON into the ``{active, profiles}`` shape.

    Migrates the legacy flat ``{ADARE_*: value}`` format into a single
    ``default`` profile so older config files keep working.
    """
    if not isinstance(data, dict):
        return _empty()
    if 'profiles' in data and isinstance(data['profiles'], dict):
        profiles = {
            str(name): {str(k): str(v) for k, v in values.items()}
            for name, values in data['profiles'].items()
            if isinstance(values, dict)
        }
        active = data.get('active')
        active = str(active) if active in profiles else None
        return {'active': active, 'profiles': profiles}
    # Legacy flat format: keys are ADARE_* settings.
    flat = {str(k): str(v) for k, v in data.items()}
    if not flat:
        return _empty()
    log.info('Migrating flat config to a "default" profile')
    return {'active': 'default', 'profiles': {'default': flat}}


def _load() -> dict:
    """Return the store ``{active, profiles}`` (cached)."""
    global _cache
    if _cache is not None:
        return _cache
    _cache = _empty()
    if not APPDATA_DIR:
        return _cache
    config_path = APPDATA_DIR / _CONFIG_FILENAME
    if not config_path.exists():
        return _cache
    try:
        data = json.loads(config_path.read_text())
    except (OSError, ValueError) as exc:  # ValueError covers JSONDecodeError
        log.warning('Ignoring unreadable config file %s: %s', config_path, exc)
        return _cache
    _cache = _normalise(data)
    return _cache


# ── read API (used by config/server.py) ──────────────────────────────────────

def get(name: str):
    """Value for a single ``ADARE_*`` key from the active profile, or ``None``."""
    store = _load()
    active = store['active']
    if not active:
        return None
    return store['profiles'].get(active, {}).get(name)


def active_name():
    """Name of the active profile, or ``None`` if none is set."""
    return _load()['active']


def profiles() -> dict:
    """Mapping of ``{profile_name: {ADARE_*: value}}`` (a copy)."""
    return {name: dict(values) for name, values in _load()['profiles'].items()}


def get_profile(name: str):
    """The named profile's settings, or ``None`` if it does not exist."""
    values = _load()['profiles'].get(name)
    return dict(values) if values is not None else None


# ── write API (used by `adare vlm ...`) ──────────────────────────────────────

def set_profile(name: str, values: dict, activate: bool = True) -> None:
    """Create or replace a profile and (by default) make it active."""
    store = _copy(_load())
    store['profiles'][name] = {str(k): str(v) for k, v in values.items()}
    if activate:
        store['active'] = name
    _save(store)


def set_active(name: str) -> None:
    """Point ``active`` at an existing profile (raises ``KeyError`` if missing)."""
    store = _copy(_load())
    if name not in store['profiles']:
        raise KeyError(name)
    store['active'] = name
    _save(store)


def remove_profile(name: str) -> bool:
    """Delete a profile. Returns ``False`` if it did not exist.

    Clears ``active`` if the removed profile was the active one.
    """
    store = _copy(_load())
    if name not in store['profiles']:
        return False
    del store['profiles'][name]
    if store['active'] == name:
        store['active'] = None
    _save(store)
    return True


def _copy(store: dict) -> dict:
    return {'active': store['active'],
            'profiles': {n: dict(v) for n, v in store['profiles'].items()}}


def _save(store: dict) -> None:
    """Persist the store ``0600`` (drops the file when empty) and refresh cache."""
    global _cache
    if not APPDATA_DIR:
        raise ConfigDirectoryError(log, 'the config directory could not be set')
    config_path = path()
    if not store['profiles']:
        if config_path.exists():
            config_path.unlink()
        _cache = _empty()
        return
    APPDATA_DIR.mkdir(parents=True, exist_ok=True)
    config_path.write_text(json.dumps(store, indent=2, sort_keys=True) + '\n')
    os.chmod(config_path, 0o600)
    _cache = store
