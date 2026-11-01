#!/usr/bin/env python3
"""Compare an agent-backend run with a host-side-backend run of the same experiment.

    python scripts/hostside_compare.py <agent run dir> <hostside run dir> [--markdown]

Reads, from each run directory: the test results logged in ``logs/adare.log``, the filesystem diff
(``artifacts/filesystem_diffs.json`` for the agent's in-guest ``find`` diff,
``artifacts/diff/filesystem_diffs.json`` for the host-side offline diff), the footprint of the
agent in each diff, and the host-side timings (``hostside/hostside-report.json``).
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / 'adare'))

from adare.backend.hostside.fsdiff import classify_agent_footprint  # noqa: E402

_TEST = re.compile(r"Test '([^']+)' completed: (\w+)")
_STAMP = re.compile(r'^\[(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}),(\d+)\]')


def tests(run: Path) -> dict[str, str]:
    out: dict[str, str] = {}
    log = run / 'logs' / 'adare.log'
    if log.exists():
        for line in log.read_text(errors='replace').splitlines():
            m = _TEST.search(line)
            if m and 'test_result_processor' in line:
                out[m.group(1)] = m.group(2)
    return out


def duration(run: Path) -> float | None:
    log = run / 'logs' / 'adare.log'
    if not log.exists():
        return None
    stamps = []
    for line in log.read_text(errors='replace').splitlines():
        m = _STAMP.match(line)
        if m:
            stamps.append(datetime.strptime(m.group(1), '%Y-%m-%d %H:%M:%S'))
    return (stamps[-1] - stamps[0]).total_seconds() if len(stamps) > 1 else None


def diff_summary(path: Path) -> dict | None:
    if not path.exists():
        return None
    doc = json.loads(path.read_text())
    changes = doc.get('changes', doc)
    paths = [e['path'] for k in ('added', 'modified') for e in changes.get(k, [])]
    groups = classify_agent_footprint(paths)
    return {
        'added': len(changes.get('added', [])),
        'removed': len(changes.get('removed', [])),
        'modified': len(changes.get('modified', [])),
        'agent_paths': sum(len(v) for v in groups.values()),
        'agent_groups': {k: len(v) for k, v in groups.items()},
        'agent_examples': {k: v[:3] for k, v in groups.items()},
    }


def compare(agent: Path, hostside: Path) -> dict:
    a_tests, h_tests = tests(agent), tests(hostside)
    names = sorted(set(a_tests) | set(h_tests))
    report = {
        'tests': {n: {'agent': a_tests.get(n), 'hostside': h_tests.get(n)} for n in names},
        'tests_agree': all(a_tests.get(n) == h_tests.get(n) for n in names),
        'log_duration_s': {'agent': duration(agent), 'hostside': duration(hostside)},
        'diff': {
            'agent (in-guest find, before/after the playbook)': diff_summary(
                agent / 'artifacts' / 'filesystem_diffs.json'
            ),
            'hostside (offline, base image vs final overlay)': diff_summary(
                hostside / 'artifacts' / 'diff' / 'filesystem_diffs.json'
            ),
        },
    }
    hs = hostside / 'hostside' / 'hostside-report.json'
    if hs.exists():
        data = json.loads(hs.read_text())
        report['hostside_timings'] = data.get('timings')
        report['hostside_footprint'] = data.get('footprint')
    return report


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    ap.add_argument('agent_run', type=Path)
    ap.add_argument('hostside_run', type=Path)
    ap.add_argument('--markdown', action='store_true')
    args = ap.parse_args()
    report = compare(args.agent_run, args.hostside_run)
    if not args.markdown:
        print(json.dumps(report, indent=2, default=str))
        return
    print('| test | agent | hostside |\n|---|---|---|')
    for name, r in report['tests'].items():
        print(f"| {name} | {r['agent']} | {r['hostside']} |")
    print('\ntests agree:', report['tests_agree'])
    print('log duration (s):', report['log_duration_s'])
    for label, d in report['diff'].items():
        print(f'\n{label}:', json.dumps(d, indent=1, default=str) if d else 'n/a')
    if 'hostside_timings' in report:
        print('\nhostside timings:', report['hostside_timings'])


if __name__ == '__main__':
    main()
