"""Sidecar cache for the SHA256 of large, rarely-changing files (installer ISOs).

Hashing a 5 GB ISO takes tens of seconds, and ``vm create`` / ``env load`` used to
do it on every run for an ISO that had not changed since it was downloaded. The
digest is stored next to the file in ``<file>.sha256`` (or in a caller-chosen cache
file) together with the file's size, ``mtime_ns``, ``ctime_ns`` and inode, and is
reused only while all of them still match, so any rewrite, truncation or
replacement of the file forces a fresh hash. ``ctime`` matters for integrity
checks: unlike ``mtime`` it cannot be set back with ``utime`` after an in-place
edit.

A ``.sha256`` file that is not one of ours (e.g. the plain-text checksum a
distribution publishes next to its ISO) is never read as a cache entry and never
overwritten.
"""

import json
import logging
import os
from collections.abc import Callable
from pathlib import Path

from adare.helperfunctions.hash import hash_file_sha256

log = logging.getLogger(__name__)

SIDECAR_SUFFIX = '.sha256'
_FORMAT = 'adare-sha256-cache/1'


def sidecar_path(path: Path) -> Path:
    """Return the sidecar file that caches ``path``'s digest."""
    path = Path(path)
    return path.with_name(path.name + SIDECAR_SUFFIX)


def _fingerprint(st: os.stat_result) -> dict:
    return {'size': st.st_size, 'mtime_ns': st.st_mtime_ns, 'ctime_ns': st.st_ctime_ns, 'inode': st.st_ino}


def _load_sidecar(sidecar: Path) -> tuple[bool, dict | None]:
    """Return ``(exists, entry)``; ``entry`` is None when missing or not ours."""
    try:
        raw = sidecar.read_text(encoding='utf-8')
    except FileNotFoundError:
        return False, None
    except (OSError, UnicodeDecodeError):
        return True, None
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return True, None
    if not isinstance(data, dict) or data.get('format') != _FORMAT or not isinstance(data.get('sha256'), str):
        return True, None
    return True, data


def _write_sidecar(path: Path, st: os.stat_result, digest: str, sidecar: Path | None = None) -> None:
    sidecar = sidecar or sidecar_path(path)
    exists, entry = _load_sidecar(sidecar)
    if exists and entry is None:
        log.debug(f'Not caching digest of {path}: {sidecar} exists and is not an adare digest cache')
        return
    payload = {'format': _FORMAT, 'sha256': digest, **_fingerprint(st)}
    tmp = sidecar.with_name(sidecar.name + '.tmp')
    try:
        sidecar.parent.mkdir(parents=True, exist_ok=True)
        tmp.write_text(json.dumps(payload), encoding='utf-8')
        os.replace(tmp, sidecar)
    except OSError as e:
        # Best effort: a read-only ISO directory just means no cache.
        log.debug(f'Could not write digest cache {sidecar}: {e}')
        tmp.unlink(missing_ok=True)


def record_file_sha256(
    path: Path, digest: str, cache_file: Path | None = None, st: os.stat_result | None = None
) -> None:
    """Cache an already-known digest of ``path`` (e.g. computed while downloading it).

    Pass ``st`` -- the stat taken *before* the digest was computed -- so a change
    made while hashing invalidates the entry instead of being cached as clean.
    """
    path = Path(path)
    _write_sidecar(path, st or path.stat(), digest.lower(), cache_file)


def fresh_cached_sha256(path: Path, cache_file: Path | None = None) -> str | None:
    """The cached digest of ``path`` if the file is unchanged since it was cached, else None."""
    path = Path(path)
    _, entry = _load_sidecar(cache_file or sidecar_path(path))
    if entry is not None and all(entry.get(k) == v for k, v in _fingerprint(path.stat()).items()):
        cached: str = entry['sha256']
        return cached
    return None


def cached_file_sha256(
    path: Path, compute: Callable[[Path], str] = hash_file_sha256, cache_file: Path | None = None
) -> str:
    """Return the SHA256 hex digest of ``path``, reusing the sidecar cache when valid.

    Args:
        path: File to hash.
        compute: Hash function used on a cache miss (e.g. one with a progress bar).
        cache_file: Where to keep the cache entry instead of ``<path>.sha256`` --
            for files whose directory ADARE must not write to (a user's disk image).

    Returns:
        Lowercase SHA256 hex digest.
    """
    path = Path(path)
    # Fingerprint taken BEFORE hashing: if the file changes while it is being read,
    # the recorded fingerprint no longer matches and the next call re-hashes.
    st = path.stat()
    sidecar = cache_file or sidecar_path(path)
    _, entry = _load_sidecar(sidecar)
    if entry is not None and all(entry.get(k) == v for k, v in _fingerprint(st).items()):
        log.debug(f'Using cached SHA256 of {path}')
        cached: str = entry['sha256']
        return cached
    digest = compute(path).lower()
    _write_sidecar(path, st, digest, sidecar)
    return digest
