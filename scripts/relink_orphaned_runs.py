#!/usr/bin/env python3
"""One-off maintenance: relink experiment runs that were detached from their experiment.

Background
----------
A bug caused successful runs to be saved with ``experiment_id = NULL`` whenever the
environment they ran in was not listed in the experiment's env indicator. Those runs
executed fine but became invisible in ``adare run list``.

The forward fix (link-by-name in ``set_experiment_run_base_info``) means new runs no
longer detach, so this is a *one-time* cleanup for databases that already contain
detached runs. It is intentionally NOT an ``adare`` subcommand.

What it does, for every run with ``experiment_id IS NULL``:
  * derives the experiment name from the run path (``run/<name>/<timestamp>``),
  * links the run to that experiment,
  * registers the run's environment as a "can run here" indicator (DB + metadata.yml).

Runs interrupted before their ``path`` was set cannot be recovered and are left as-is.

Usage
-----
    python scripts/relink_orphaned_runs.py /path/to/project
    python scripts/relink_orphaned_runs.py /path/to/project --dry-run
"""

import argparse
import sys
from pathlib import Path


def _summarize_dry_run(project_path: Path) -> dict:
    """Report what would be relinked without writing anything."""
    from adare.database.api.base import experiment_name_from_run_path
    from adare.database.api.experiment import ExperimentApi

    summary = {'relinked': 0, 'skipped_no_path': 0, 'skipped_no_experiment': 0, 'total': 0}
    with ExperimentApi(project_path) as api:
        unlinked = api.get_unlinked_runs()
        summary['total'] = len(unlinked)
        for run in unlinked:
            name = experiment_name_from_run_path(run.path)
            if not name:
                summary['skipped_no_path'] += 1
            elif api.get_experiment_by_project_and_name(project_path, name) is None:
                summary['skipped_no_experiment'] += 1
            else:
                summary['relinked'] += 1
    return summary


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('project', type=Path, help='Path to the ADARE project directory (contains .adare/)')
    parser.add_argument('--dry-run', action='store_true', help='Report what would change without writing')
    args = parser.parse_args(argv)

    project_path = args.project.resolve()
    if not (project_path / '.adare').is_dir():
        parser.error(f'not an ADARE project (no .adare/ directory): {project_path}')

    if args.dry_run:
        summary = _summarize_dry_run(project_path)
        prefix = '[dry-run] would relink'
    else:
        from adare.backend.experiment import database as experiment_database
        summary = experiment_database.relink_unlinked_runs(project_path)
        prefix = 'relinked'

    if summary['total'] == 0:
        print(f'No unlinked runs found in {project_path.name} - nothing to do.')
        return 0

    print(f"{prefix} {summary['relinked']} of {summary['total']} unlinked run(s) in project '{project_path.name}'.")
    if summary['skipped_no_path']:
        print(f"  {summary['skipped_no_path']} run(s) had no path (interrupted early) - left unlinked.")
    if summary['skipped_no_experiment']:
        print(f"  {summary['skipped_no_experiment']} run(s) referenced an experiment that no longer exists.")
    if not args.dry_run:
        print("Done. Run 'adare run list' to see the recovered runs.")
    return 0


if __name__ == '__main__':
    sys.exit(main())
