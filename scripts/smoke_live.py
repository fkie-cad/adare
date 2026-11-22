#!/usr/bin/env python3
"""Live-VM smoke test: boot a real environment and run a small experiment in it.

Run by ``make smoke-live`` (CI: live-smoke.yml on the self-hosted ``adare-live``
runner). It drives the *installed* ``adare`` CLI, so it tests what ``make install``
just installed, and needs a host with KVM/libvirt and the environment's image:

1. A fresh project ``<projects-dir>/ci-smoke-<run-id>``.
2. ``adare env verify <env> -p <project>``: boots the VM, installs the agent and replays
   the built-in ``verify_vm`` playbook (exits non-zero on failure).
3. The bundled ``test_loop_simple`` example (shell commands, loops, ``file_exists``
   tests and pulls; no GUI), attached to the environment.
4. ``adare --output-file smoke-result.json experiment run``. It must exit 0 (it exits 1
   when a run did not pass), and as a second check every ``results[].status`` in the
   JSON must be SUCCESS or WARNING.

The whole sequence runs under ``adare vm slots exclusive``, so it waits for (and then
blocks) the host's other ADARE runs instead of competing with them; busy slots past
``--slot-timeout`` exit 75. On success the project is removed; on failure it is kept
(CI uploads it) and removed by a later run after ``KEEP_DAYS``. Standard library only.
"""

import argparse
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

EXPERIMENT = 'test_loop_simple'
PREFIX = 'ci-smoke-'
KEEP_DAYS = 7
OK_STATUSES = frozenset({'SUCCESS', 'WARNING'})
INNER_FLAG = '--inner'


class SmokeError(Exception):
    pass


def run(cmd: list[str], cwd: Path | None = None) -> None:
    print(f'+ {" ".join(cmd)}', flush=True)
    code = subprocess.call(cmd, cwd=cwd)
    if code != 0:
        raise SmokeError(f'{" ".join(cmd[:4])} ... exited {code}')


def result_failures(result: dict) -> list[str]:
    """Problems in an ``--output-file`` run summary; empty when every run passed."""
    results = result.get('results')
    if not results:
        return ['the run summary has no results']
    return [
        f'{r.get("experiment")} on {r.get("environment")}: {r.get("status")}'
        + (f' ({r["error_message"]})' if r.get('error_message') else '')
        for r in results
        if r.get('status') not in OK_STATUSES
    ]


def remove_project(adare: str, project: Path) -> None:
    """Remove a smoke project from the DB and disk (``adare project remove``), or just the dir."""
    if subprocess.call([adare, 'project', 'remove', project.name], stdout=subprocess.DEVNULL) != 0:
        print(f'{project.name} not registered; deleting the directory', flush=True)
    shutil.rmtree(project, ignore_errors=True)


def clean_stale(adare: str, projects_dir: Path, keep_days: float, now: float) -> list[Path]:
    """Remove smoke projects older than ``keep_days`` (the ones kept after a failure)."""
    removed = []
    for project in sorted(projects_dir.glob(f'{PREFIX}*')):
        if project.is_dir() and now - project.stat().st_mtime > keep_days * 86400:
            remove_project(adare, project)
            removed.append(project)
    return removed


def smoke(adare: str, env: str, projects_dir: Path, run_id: str) -> Path:
    """Run the smoke sequence; returns the project dir (kept on failure)."""
    project = projects_dir / f'{PREFIX}{run_id}'
    if project.exists():
        raise SmokeError(f'{project} already exists; pick another --run-id')

    projects_dir.mkdir(parents=True, exist_ok=True)
    run([adare, 'project', 'create', project.name, '-d', 'ADARE live-VM smoke test (CI)'], cwd=projects_dir)
    # verify_vm goes into the same project, so a failure keeps all logs in one place.
    run([adare, 'env', 'verify', env, '-p', str(project)])
    run([adare, 'experiment', 'example', EXPERIMENT, '-p', str(project)])
    run([adare, 'experiment', 'add-env', EXPERIMENT, env, '-p', str(project)])

    result_file = project / 'smoke-result.json'
    cmd = [adare, '--output-file', str(result_file), 'experiment', 'run', EXPERIMENT, '-e', env, '-p', str(project)]
    print(f'+ {" ".join(cmd)}', flush=True)
    code = subprocess.call(cmd)
    if not result_file.is_file():
        raise SmokeError(f'experiment run exited {code} without writing {result_file}')
    failures = result_failures(json.loads(result_file.read_text(encoding='utf-8')))
    if code != 0:
        failures.insert(0, f'experiment run exited {code}')
    if failures:
        raise SmokeError('experiment run failed: ' + '; '.join(failures))
    return project


def default_run_id() -> str:
    if run_id := os.environ.get('GITHUB_RUN_ID'):
        return f'{run_id}-{os.environ.get("GITHUB_RUN_ATTEMPT", "1")}'
    return time.strftime('%Y%m%d-%H%M%S')


def parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--env', required=True, help='environment to boot, e.g. ubuntu2404-x86')
    parser.add_argument('--adare', default=shutil.which('adare') or 'adare', help='adare CLI (default: on PATH)')
    parser.add_argument('--projects-dir', type=Path, default=Path.home() / 'adare-projects')
    parser.add_argument('--run-id', default=default_run_id(), help='project suffix (CI: <run id>-<attempt>)')
    parser.add_argument('--slot-timeout', type=float, default=900, help='seconds to wait for the host VM slots')
    parser.add_argument(INNER_FLAG, action='store_true', help=argparse.SUPPRESS)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    if not args.inner:
        # Re-run this script while holding every VM slot; the exit status passes through.
        argv = sys.argv[1:] if argv is None else argv
        cmd = [args.adare, 'vm', 'slots', 'exclusive', '--timeout', str(args.slot_timeout), '--']
        return subprocess.call([*cmd, sys.executable, str(Path(__file__).resolve()), INNER_FLAG, *argv])

    for stale in clean_stale(args.adare, args.projects_dir, KEEP_DAYS, time.time()):
        print(f'removed stale smoke project {stale}', flush=True)
    project = args.projects_dir / f'{PREFIX}{args.run_id}'
    try:
        smoke(args.adare, args.env, args.projects_dir, args.run_id)
    except SmokeError as exc:
        print(f'live smoke FAILED: {exc}', file=sys.stderr)
        if project.exists():
            print(f'kept {project} for inspection (removed after {KEEP_DAYS} days)', file=sys.stderr)
        return 1
    remove_project(args.adare, project)
    print(f'live smoke passed on {args.env}', flush=True)
    return 0


if __name__ == '__main__':
    sys.exit(main())
