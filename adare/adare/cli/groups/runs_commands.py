from types import SimpleNamespace

import click

from adare.cli.output import output_options


def register(cli, AliasedGroup, exec_with_error_printing):
    """Register the ``runs`` command group with the CLI; returns the group."""

    @cli.group(name='runs', cls=AliasedGroup)
    def runs():
        """Experiment runs: list, inspect, remove and prune them (start one with `adare experiment run`)."""

    @runs.command(name='list')
    @output_options
    @click.option('--filter', help='Filter by dotnotation: [project][.environment][.experiment]')
    def list_runs(filter):
        """List all experiment runs. Use --filter with dotnotation for advanced filtering."""
        from adare.cli.show import exec_show_runs

        args = SimpleNamespace(filter=filter)
        exec_with_error_printing(exec_show_runs, args)

    @runs.command(name='info')
    @output_options
    @click.argument('ulid', required=False)
    def run_info(ulid):
        """Show detailed information about a run. Shows latest run if no ULID provided."""
        from adare.cli.show import exec_show_run

        args = SimpleNamespace(ulid=ulid)
        exec_with_error_printing(exec_show_run, args)

    @runs.command(name='remove')
    @click.argument('ulid', required=True)
    @click.option('--keep-files', is_flag=True, help='Keep the run folder on disk (only remove the database rows)')
    def run_remove(ulid, keep_files):
        """Remove a single experiment run by its ULID: its database rows and its run folder.

        The folder (run/<experiment>/<timestamp>) is only deleted when it is clearly
        an ADARE run folder; otherwise it is kept and the reason is printed.
        """
        from adare.cli.show import exec_remove_run

        args = SimpleNamespace(ulid=ulid, keep_files=keep_files)
        exec_with_error_printing(exec_remove_run, args)

    @runs.command(name='prune')
    @output_options
    @click.option(
        '--fake',
        is_flag=True,
        help='Also remove finished fake (test-mode) runs, except dev sessions\' runs: rows + folders',
    )
    @click.option(
        '--older-than',
        'older_than',
        type=click.FloatRange(min=0),
        metavar='DAYS',
        help='Only targets last changed (fake runs: started) at least DAYS days ago',
    )
    @click.option('--yes', '-y', is_flag=True, help='Delete the listed targets (default: dry run, deletes nothing)')
    def run_prune(fake, older_than, yes):
        """Free disk space in the current project's run/ directory.

        Lists run folders (run/<experiment>/<timestamp>) that nothing refers to, with
        their sizes and a total. Nothing is deleted without --yes. A folder is kept
        when a run or dev session has it as its folder, when a run that failed before
        recording a folder started within 16 h of its timestamp name, or when another
        registered project sharing this run/ directory uses it (if such a project
        cannot be read, nothing is pruned).

        \b
        A folder is only ever listed when it is clearly an ADARE run folder: inside
        run/ (no symlinks), of a known experiment, named like a run timestamp, with a
        logs/ or reporting/ subdirectory, and unchanged for at least an hour. Anything
        else in run/ (your own files) is never touched.

        \b
        Examples:
            adare runs prune                      # dry run: what would be removed
            adare runs prune --fake --older-than 7
            adare runs prune --fake --yes
        """
        from adare.cli.show import exec_prune_runs

        args = SimpleNamespace(fake=fake, older_than=older_than, yes=yes)
        exec_with_error_printing(exec_prune_runs, args)

    # Add aliases for run commands
    runs.add_alias('l', 'list')
    runs.add_alias('rm', 'remove')
    return runs
