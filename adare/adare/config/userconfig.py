"""Persisted per-machine user configuration.

A small JSON key/value store at ``~/.adare/config.json`` that supplies defaults
for selected ``ADARE_*`` settings without exporting environment variables in
every shell. Keys mirror the env-var names exactly, so the file is
self-documenting and :func:`adare.config.server` can resolve a setting with a
one-liner (``env var > config file > code default``).

The file may hold secrets (e.g. ``ADARE_VLLM_API_KEY``), so it is written
``0600``. Reads never raise: a missing or corrupt file resolves to ``{}`` and the
caller falls through to the code default.

Written by ``adare vlm use ...``; read at import time by ``config/server.py``.
"""

import json
import logging
import os

from .configdirectory import APPDATA_DIR
from .exceptions import ConfigDirectoryError

log = logging.getLogger(__name__)

_CONFIG_FILENAME = 'config.json'
# Cache the parsed file for the life of the process. A CLI call is a fresh
# process, so writes from `adare vlm use` are always seen by the next command;
# within one process the config does not change under us.
_cache: dict | None = None


def path():
    """Absolute path of the config file (``~/.adare/config.json``)."""
    if not APPDATA_DIR:
        raise ConfigDirectoryError(log, 'the config directory could not be set')
    return APPDATA_DIR / _CONFIG_FILENAME


def load() -> dict:
    """Return the parsed config (cached). ``{}`` if absent or unreadable."""
    global _cache
    if _cache is not None:
        return _cache
    _cache = {}
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
    if isinstance(data, dict):
        # Store only string values keyed by string — the store is flat.
        _cache = {str(k): str(v) for k, v in data.items()}
    else:
        log.warning('Ignoring config file %s: expected a JSON object', config_path)
    return _cache


def get(name: str):
    """Value for a single ``ADARE_*`` key, or ``None`` if not set."""
    return load().get(name)


def set_values(mapping: dict) -> None:
    """Merge ``mapping`` into the config file and write it ``0600``."""
    global _cache
    if not APPDATA_DIR:
        raise ConfigDirectoryError(log, 'the config directory could not be set')
    APPDATA_DIR.mkdir(parents=True, exist_ok=True)
    data = load().copy()
    data.update({str(k): str(v) for k, v in mapping.items()})
    _write(data)
    _cache = data


def unset(keys) -> None:
    """Remove ``keys`` from the config file (drops the file if it empties)."""
    global _cache
    data = load().copy()
    for key in keys:
        data.pop(key, None)
    config_path = path()
    if not data:
        if config_path.exists():
            config_path.unlink()
        _cache = {}
        return
    _write(data)
    _cache = data


def _write(data: dict) -> None:
    """Serialise ``data`` to the config file with owner-only permissions."""
    config_path = path()
    config_path.write_text(json.dumps(data, indent=2, sort_keys=True) + '\n')
    os.chmod(config_path, 0o600)
