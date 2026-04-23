"""
CLI handler for diff mode command.

Executes experiments in visual diff mode (QEMU only, no agent).
"""

import asyncio
import logging
from pathlib import Path

from adare.backend.basics import determine_projectdirectory
from adare.console import print_error_message, print_success_message
from adare.exceptions import NoProjectFoundError
from adare.helperfunctions.path_resolution import resolve_environment_path, resolve_experiment_path

log = logging.getLogger(__name__)


def exec_experiment_diff(arguments):
    """
    Execute experiment in visual diff mode (QEMU only, no agent).

    Args:
        arguments: SimpleNamespace with experiment, environment, and project attributes
    """
    # Get project path
    project = getattr(arguments, 'project', None)
    project_directory = determine_projectdirectory(project)
    if not project_directory:
        raise NoProjectFoundError(log, specified_project=project)

    # Resolve paths
    experiment_name = resolve_experiment_path(arguments.experiment, project_directory)
    environment_name = resolve_environment_path(arguments.environment, project_directory)

    log.info(f"Diff mode: {experiment_name} on {environment_name}")

    # Run diff mode
    from adare.backend.experiment.diff_run import experiment_diff_run

    result = asyncio.run(experiment_diff_run(
        project_path=Path(project_directory),
        experiment_name=experiment_name,
        environment_name=environment_name
    ))

    # Display results
    if result.success:
        next_steps = [
            f"Total actions: {result.actions_executed}",
            f"  ✓ Successful: {result.successful_actions}",
            f"  ✗ Failed: {result.failed_actions}",
            f"Actions skipped (non-visual): {result.actions_skipped}",
            f"Execution time: {result.execution_time:.2f}s"
        ]

        # Add diff artifact information if available
        if result.diff_run_directory:
            screenshots_dir = result.diff_run_directory / 'reporting' / 'screenshots'
            diff_dir = result.diff_run_directory / 'artifacts' / 'diff'
            next_steps.extend([
                f"Screenshots: {screenshots_dir}",
                f"Filesystem diff: {diff_dir}",
                "  - filesystem_diffs.json (machine-readable)",
                "  - filesystem_diffs.csv (human-readable)"
            ])

        print_success_message(
            title='Diff mode completed successfully',
            next_steps=next_steps
        )
    else:
        error_steps = [
            result.error if result.error else "Unknown error occurred",
            "",
            f"Total actions: {result.actions_executed}",
            f"  ✓ Successful: {result.successful_actions}",
            f"  ✗ Failed: {result.failed_actions}",
            f"Actions skipped (non-visual): {result.actions_skipped}",
            f"Execution time: {result.execution_time:.2f}s",
            "",
            "Check logs for details"
        ]
        print_error_message(
            title='Diff mode failed',
            next_steps=error_steps
        )
        exit(1)
