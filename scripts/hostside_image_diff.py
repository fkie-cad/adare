#!/usr/bin/env python3
"""Offline filesystem diff of two disk images (host-side backend's differ, standalone).

    python scripts/hostside_image_diff.py <base.qcow2> <final.qcow2|final.raw> [--out diff.json]

Both images must be quiesced (VM stopped). Prints added/removed/modified counts and the share of
paths that match the in-guest agent's footprint patterns (adarevm/adarelib, /adare, guest Python
dependencies, /tmp/adare_*). Use it on the ``--export-disk-image`` output of an agent run to get a
base-vs-end footprint comparable with a host-side run's ``artifacts/diff``.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / 'adare'))

from adare.backend.hostside import fsdiff  # noqa: E402
from adare.backend.hostside.guestfs import OfflineDiskGuestFS  # noqa: E402


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    ap.add_argument('base', type=Path)
    ap.add_argument('final', type=Path)
    ap.add_argument('--out', type=Path)
    args = ap.parse_args()
    with OfflineDiskGuestFS(args.base) as base, OfflineDiskGuestFS(args.final) as final:
        result = fsdiff.diff(base, final)
    paths = [e['path'] for k in ('added', 'modified') for e in result[k]]
    groups = fsdiff.classify_agent_footprint(paths)
    summary = {
        'added': len(result['added']),
        'removed': len(result['removed']),
        'modified': len(result['modified']),
        'agent_paths': sum(len(v) for v in groups.values()),
        'agent_groups': {k: len(v) for k, v in groups.items()},
        'agent_examples': {k: v[:4] for k, v in groups.items()},
    }
    print(json.dumps(summary, indent=2))
    if args.out:
        args.out.write_text(json.dumps({'summary': summary, 'changes': result}, indent=1))


if __name__ == '__main__':
    main()
