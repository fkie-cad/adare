"""Run report of the host-side backend: what ran, how long it took, and the guest footprint.

The footprint is read from the *quiesced final image*, with no guest involvement:

* which of the in-guest agent's own artifacts exist (``/adare`` contents, adarevm/adarelib
  packages, guest Python environments), classified from the offline base-vs-overlay diff when
  there is one, else probed directly;
* what the guest's own log says about the guest agents of this boot (``/var/log/syslog``:
  ``qemu-ga`` / ``qemu-guest-agent`` / ``adarevm`` lines).
"""

from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING

from adare.backend.hostside import fsdiff
from adare.backend.hostside.guestfs import GuestFS, GuestFSError

if TYPE_CHECKING:
    from adare.backend.hostside.session import HostsideSession

_AGENT_LOG = re.compile(r'qemu-ga|qemu-guest-agent|adarevm|adare-agent', re.I)
_AGENT_PROBES = ('/adare', '/home/adare/.cache/pip', '/home/adare/.miniforge3', '/root/.cache/pip')


def _line_epoch(line: str) -> float | None:
    """Epoch of an rsyslog RFC 3339 line (``2026-07-24T23:50:58.635313+00:00 host prog: ...``)."""
    try:
        return datetime.fromisoformat(line.split(' ', 1)[0]).timestamp()
    except ValueError:
        return None


def agent_log_lines(fs: GuestFS, since: float | None = None, limit: int = 20) -> dict:
    """Lines of the guest's syslog that mention a guest agent, optionally only those since ``since`` (epoch).

    The image's syslog also holds what happened when the base image was built, so a run's evidence
    is only the lines newer than the run's start.
    """
    for path in ('/var/log/syslog', '/var/log/messages'):
        if fs.exists(path):
            try:
                all_lines = fs.read_text(path).splitlines()
            except GuestFSError as e:
                return {'log': path, 'error': str(e)}
            agent = [ln for ln in all_lines if _AGENT_LOG.search(ln)]
            recent = [ln for ln in agent if since is None or (_line_epoch(ln) or 0) >= since]
            return {
                'log': path,
                'since_epoch': since,
                'matches_this_run': len(recent),
                'matches_in_whole_log': len(agent),
                'first_this_run': recent[:limit],
                'lines_this_run': sum(1 for ln in all_lines if since is None or (_line_epoch(ln) or 0) >= since),
            }
    return {'log': None, 'matches_this_run': 0, 'note': 'no text syslog in the image'}


def agent_artifacts(fs: GuestFS, diff_result: dict | None) -> dict:
    """The in-guest agent's files present in the final image (and, when diffed, those the run added)."""
    probes = {}
    for path in _AGENT_PROBES:
        if fs.lexists(path):
            try:
                n = sum(1 for _ in fs.iter_tree(path)) if fs.is_dir(path) else 1
            except GuestFSError:
                n = -1
            probes[path] = n
    out: dict = {'probe_entries': probes}
    if diff_result is not None:
        paths = [e['path'] for key in ('added', 'modified') for e in diff_result.get(key, [])]
        out['classified'] = {k: len(v) for k, v in fsdiff.classify_agent_footprint(paths).items()}
        out['classified_examples'] = {k: v[:5] for k, v in fsdiff.classify_agent_footprint(paths).items()}
        out['diff_counts'] = {k: len(v) for k, v in diff_result.items()}
    return out


def write_run_report(session: HostsideSession) -> Path:
    """Write ``hostside/hostside-report.json`` and ``hostside/footprint.json`` for this run."""
    footprint: dict = {'backend': 'hostside', 'image_state': 'not read (guest not quiesced)'}
    if session.quiesced:
        fs = session.final_fs()
        footprint = {
            'backend': 'hostside',
            'image_state': 'quiesced',
            'clean_shutdown': bool((session.shutdown or {}).get('clean')),
            'agent_artifacts': agent_artifacts(fs, session.last_diff),
            'guest_agent_log': agent_log_lines(fs, since=session.stage_time),
            'process_list': getattr(session, 'pslist', None),
            'guest_agent_channel_in_domain': bool(getattr(session.vm.config, 'guest_agent_channel', True)),
        }
    (session.hs_dir / 'footprint.json').write_text(json.dumps(footprint, indent=2, default=str))
    return session.write_report({'footprint': footprint, 'markers': getattr(session.markers, 'count', 0)})
