"""Offline filesystem diff: base image vs the run's overlay, no guest process involved.

The agent backend diffs with an in-guest ``find`` before and after the run
(``adarevm/platforms/linux_fs_snapshot.py``), which makes the agent's own file
activity part of the result. This module walks both disks from the host through
:class:`~adare.backend.hostside.guestfs.GuestFS` and reports
``added / removed / modified`` in the same shape as
``adare.hypervisor.qemu.disk_diff.DiskDiffComparator`` so the existing exporters
(JSON / CSV / bodyfile) apply unchanged.
"""

from __future__ import annotations

import logging
import re
import time
from datetime import datetime
from typing import Any

from adare.backend.hostside.guestfs import GuestFS, GuestStat

log = logging.getLogger(__name__)

#: Pseudo filesystems and volatile trees that are not part of a disk comparison.
DEFAULT_EXCLUDES = ('/proc', '/sys', '/dev', '/run')

#: Path patterns that identify the in-guest agent's own footprint.
AGENT_PATTERNS = {
    'adarevm / adarelib packages': re.compile(r'(^|/)(adarevm|adarelib)([-_./]|$)', re.I),
    'agent install dir (/adare)': re.compile(r'^/adare(/|$)'),
    'agent Python dependencies (/usr/local dist-packages, pip/uv/conda caches)': re.compile(
        r'(^/usr/local/lib/python[^/]*/(dist|site)-packages/|/\.cache/(pip|uv)|/\.miniforge3|/\.local/(lib|share/uv)|/\.venv)'
    ),
    'agent temp files (/tmp/adare_*)': re.compile(r'^/tmp/adare_'),
    'agent log / config': re.compile(r'(adarevm\.log|/adare/run/|config\.json$)'),
}


def _readable(epoch: float) -> str:
    return datetime.fromtimestamp(epoch).isoformat() if epoch else ''


def snapshot(fs: GuestFS, excludes: tuple[str, ...] = DEFAULT_EXCLUDES) -> dict[str, GuestStat]:
    """Every non-excluded path of the filesystem (lstat), keyed by path."""
    files: dict[str, GuestStat] = {}
    started = time.monotonic()
    for st in fs.iter_tree('/'):
        if any(st.path == ex or st.path.startswith(ex + '/') for ex in excludes):
            continue
        files[st.path] = st
    log.info(
        f"CLAUDE: hostside fsdiff scanned {len(files)} entries of {fs.origin} in {time.monotonic() - started:.1f}s"
    )
    return files


def _differs(a: GuestStat, b: GuestStat) -> list[str]:
    changed = []
    if a.size != b.size:
        changed.append('size')
    if a.mtime != b.mtime:
        changed.append('mtime')
    if a.mode != b.mode:
        changed.append('mode')
    if (a.uid, a.gid) != (b.uid, b.gid):
        changed.append('owner')
    if a.link_target != b.link_target:
        changed.append('link')
    return changed


def diff(
    base: GuestFS, final: GuestFS, excludes: tuple[str, ...] = DEFAULT_EXCLUDES
) -> dict[str, list[dict[str, Any]]]:
    """Added / removed / modified entries between two filesystems (directories included)."""
    before = snapshot(base, excludes)
    after = snapshot(final, excludes)
    result: dict[str, list[dict[str, Any]]] = {'added': [], 'removed': [], 'modified': []}
    for path, st in after.items():
        old = before.get(path)
        if old is None:
            result['added'].append(
                {
                    'path': path,
                    'size': st.size,
                    'mtime': st.mtime,
                    'mtime_readable': _readable(st.mtime),
                    'is_dir': st.is_dir,
                    'timestamps': {'modified': st.mtime, 'accessed': st.atime, 'changed': st.ctime},
                }
            )
            continue
        what = _differs(old, st)
        if what and not (st.is_dir and what == ['mtime']):  # a directory's mtime moves with every child change
            result['modified'].append(
                {
                    'path': path,
                    'size_before': old.size,
                    'size_after': st.size,
                    'mtime_before': old.mtime,
                    'mtime_after': st.mtime,
                    'mtime_before_readable': _readable(old.mtime),
                    'mtime_after_readable': _readable(st.mtime),
                    'changed': what,
                }
            )
    for path, st in before.items():
        if path not in after:
            result['removed'].append(
                {'path': path, 'size': st.size, 'mtime': st.mtime, 'mtime_readable': _readable(st.mtime)}
            )
    return result


def classify_agent_footprint(paths: list[str]) -> dict[str, list[str]]:
    """Group paths by the agent-footprint pattern they match (paths matching none are not listed)."""
    groups: dict[str, list[str]] = {name: [] for name in AGENT_PATTERNS}
    for path in paths:
        for name, rx in AGENT_PATTERNS.items():
            if rx.search(path):
                groups[name].append(path)
                break
    return {k: v for k, v in groups.items() if v}
