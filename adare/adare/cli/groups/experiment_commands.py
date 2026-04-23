from types import SimpleNamespace

import click


def register(cli, AliasedGroup, exec_with_error_printing):
    """Register experiment commands with the CLI."""

    # ------------------------------
    # Experiment commands
    # ------------------------------
    @cli.group(name='experiment', cls=AliasedGroup)
    def experiment():
        """Experiment-related commands."""
        pass

    # Add aliases for experiment commands
    experiment.add_alias('l', 'list')
    experiment.add_alias('rm', 'remove')
    experiment.add_alias('rm-env', 'remove-env')

    @experiment.command()
    @click.argument('experiment', type=click.Path(exists=False))
    @click.option('--project', '-p', help='Name of the project')
    def create(experiment, project):
        """Create a new experiment skeleton.

        EXPERIMENT can be:
        - Simple name: test_csv
        - Relative path: experiments/test_csv
        """
        from adare.cli.experiment import exec_experiment_create
        args = SimpleNamespace(experiment=experiment, project=project)
        exec_with_error_printing(exec_experiment_create, args)

    @experiment.command()
    @click.argument('experiment', type=click.Path(exists=False))
    @click.option('-e', '--environment', type=click.Path(exists=False), help='Name of the environment')
    @click.option('--force', '-f', is_flag=True, help='Force update of the experiment')
    @click.option('--project', '-p', help='Name of the project')
    def load(experiment, environment, force, project):
        """Load an experiment.

        EXPERIMENT can be:
        - Simple name: test_csv
        - Relative path: experiments/test_csv
        - Relative path: ./experiments/test_csv
        """
        from adare.cli.experiment import exec_experiment_load
        args = SimpleNamespace(
            experiment=experiment,
            environment=environment,
            force=force,
            project=project
        )
        exec_with_error_printing(exec_experiment_load, args)

    @experiment.command()
    @click.argument('experiment', type=click.Path(exists=False))
    @click.option('-e', '--environment', type=click.Path(exists=False), help='Name of the environment (if not specified, runs on all environments in project)')
    @click.option('--production', '--prod', is_flag=True, help='Run the experiment in production mode - creates real runs with integrity checks (default: test mode)')
    @click.option('--debug-screenshots', is_flag=True, help='Save screenshots to experiment run directory for debugging')
    @click.option('--preserve-snapshot', '-s', is_flag=True, help='Create experiment snapshot for preservation (default: only reset to base snapshot)')
    @click.option('--no-runlog', is_flag=True, help='Do not save adare log to the run/logs directory')
    @click.option('--vm-memory', type=int, help='VM RAM in MB (default: 4096 for Linux, 8192 for Windows)')
    @click.option('--vm-cpus', type=int, help='VM CPU count (default: 4)')
    @click.option('--gui-mode', type=click.Choice(['auto', 'agent', 'host']), help='GUI execution mode: auto (default), agent (WebSocket), or host (QMP for QEMU only)')
    @click.option('--test-mode', type=click.Choice(['auto', 'agent', 'host']), help='Test execution mode: auto (default), agent (WebSocket), or host (QGA for QEMU only)')
    @click.option('--diff/--no-diff', default=None, help='Enable/disable filesystem diff (overrides playbook setting)')
    @click.option('--diff-mode', type=click.Choice(['auto', 'guest', 'host']), default='auto', help='Diff mode: auto (smart selection), guest (VM-based), host (QEMU virt-diff)')
    @click.option('--project', help='Name of the project')
    @click.pass_context
    def run(ctx, experiment, environment, production, debug_screenshots, preserve_snapshot, no_runlog, vm_memory, vm_cpus, gui_mode, test_mode, diff, diff_mode, project):
        """Run an experiment in a given environment or all environments if none specified.

        By default, runs in TEST mode (creates fake runs, skips integrity checks, allows modifications).
        Use --production/--prod for real production runs with full integrity validation.

        EXPERIMENT can be:
        - Simple name: test_csv
        - Relative path: experiments/test_csv
        - Relative path: ./experiments/test_csv

        ENVIRONMENT can be:
        - Simple name: ubuntu24
        - Relative path: environments/ubuntu24.yml
        - Relative path: ./environments/ubuntu24.yaml
        """
        from adare.cli.experiment import exec_experiment_run
        args = SimpleNamespace(
            experiment=experiment,
            environment=environment,
            test=not production,  # Invert: production flag OFF means test mode ON
            debug_screenshots=debug_screenshots,
            preserve_snapshot=preserve_snapshot,
            runlog=not no_runlog,
            vm_memory=vm_memory,
            vm_cpus=vm_cpus,
            gui_mode=gui_mode,
            test_mode=test_mode,
            diff=diff,
            diff_mode=diff_mode,
            project=project,
            verbose=ctx.obj.verbose,
            very_verbose=ctx.obj.very_verbose
        )
        exec_with_error_printing(exec_experiment_run, args)

    @experiment.command()
    @click.argument('name', default='TrashBinDeleteFile', required=False)
    @click.option('--project', '-p', help='Name of the project')
    def example(name, project):
        """Create the example experiment."""
        from adare.cli.experiment import exec_experiment_example
        args = SimpleNamespace(
            experiment=name,
            project=project
        )
        exec_with_error_printing(exec_experiment_example, args)

    @experiment.command(name='list')
    def list_experiments():
        """List all experiments in an environment."""
        from adare.cli.show import exec_show_experiments
        args = SimpleNamespace()
        exec_with_error_printing(exec_show_experiments, args)

    @experiment.command()
    @click.argument('name', required=False)
    @click.option('--ulid', '-u', help='ULID of the experiment')
    @click.option('--dotnotation', '-d', help='Dotnotation in format: project_name.environment_name.experiment_name')
    def info(name, ulid, dotnotation):
        """Show detailed information about a specific experiment.

        Usage:
        - adare experiment info NAME (find experiment by name in current project)
        - adare experiment info -u ULID (find experiment by ULID)
        - adare experiment info -d project.env.experiment (find by dotnotation)
        """
        from adare.cli.show import exec_show_experiment
        args = SimpleNamespace(
            name=name,
            ulid=ulid,
            dotnotation=dotnotation
        )
        exec_with_error_printing(exec_show_experiment, args)

    @experiment.command()
    @click.argument('experiment')
    @click.option('--project', '-p', help='Name of the project')
    def clean(experiment, project):
        """Remove all fake experiment runs for the specified experiment.

        Fake runs are created during testing and development. This command
        permanently deletes all fake runs associated with the experiment.
        """
        from adare.cli.experiment import exec_experiment_clean
        args = SimpleNamespace(
            experiment=experiment,
            project=project
        )
        exec_with_error_printing(exec_experiment_clean, args)


    @experiment.command()
    @click.argument('experiment', type=click.Path(exists=False))
    @click.option('--project', '-p', help='Name of the project')
    @click.option('--force', '-f', is_flag=True, help='Force removal even if experiment has productive runs')
    @click.option('--keep-files', is_flag=True, help='Keep experiment directory on filesystem (only remove from database)')
    def remove(experiment, project, force, keep_files):
        """Remove an experiment from the database and optionally from filesystem.

        This command permanently deletes the experiment, all its runs (both productive
        and fake), and optionally the experiment directory. Use with caution!

        By default, the command will:
        - Fail if the experiment has productive runs (use --force to override)
        - Delete the experiment directory from filesystem (use --keep-files to preserve)

        EXPERIMENT can be:
        - Simple name: test_csv
        - Relative path: experiments/test_csv

        Examples:
        - adare experiment remove test_csv (fails if has runs)
        - adare experiment remove test_csv --force (removes with all runs)
        - adare experiment remove test_csv --force --keep-files (DB only)
        """
        from adare.cli.experiment import exec_experiment_remove
        args = SimpleNamespace(
            experiment=experiment,
            project=project,
            force=force,
            keep_files=keep_files
        )
        exec_with_error_printing(exec_experiment_remove, args)


    @experiment.command(name='add-env')
    @click.argument('experiment_pattern')
    @click.argument('environments', nargs=-1, required=True)
    @click.option('--force', '-f', is_flag=True, help='Force operation even if it would remove all environments')
    @click.option('--project', '-p', help='Name of the project')
    def add_env(experiment_pattern, environments, force, project):
        """Add environments to experiments matching the pattern.

        EXPERIMENT_PATTERN can be an exact name or glob pattern (e.g., test_*, *_linux).
        ENVIRONMENTS are the environment names to add.

        Examples:
        - adare experiment add-env "test_*" ubuntu24
        - adare experiment add-env "*_linux" ubuntu22 ubuntu24
        - adare experiment add-env specific_experiment ubuntu24
        """
        from adare.cli.experiment import exec_experiment_add_env
        args = SimpleNamespace(
            experiment_pattern=experiment_pattern,
            environments=list(environments),
            force=force,
            project=project
        )
        exec_with_error_printing(exec_experiment_add_env, args)


    @experiment.command(name='remove-env')
    @click.argument('experiment_pattern')
    @click.argument('environments', nargs=-1, required=True)
    @click.option('--force', '-f', is_flag=True, help='Force operation even if it would remove all environments')
    @click.option('--project', '-p', help='Name of the project')
    def remove_env(experiment_pattern, environments, force, project):
        """Remove environments from experiments matching the pattern.

        EXPERIMENT_PATTERN can be an exact name or glob pattern (e.g., test_*, *_linux).
        ENVIRONMENTS are the environment names to remove.

        Examples:
        - adare experiment remove-env "win_*" ubuntu22
        - adare experiment remove-env "*_test" old_env
        - adare experiment remove-env specific_experiment ubuntu22
        """
        from adare.cli.experiment import exec_experiment_remove_env
        args = SimpleNamespace(
            experiment_pattern=experiment_pattern,
            environments=list(environments),
            force=force,
            project=project
        )
        exec_with_error_printing(exec_experiment_remove_env, args)


    @experiment.command()
    @click.argument('source_experiment')
    @click.argument('target_experiment')
    @click.option('-e', '--environments', multiple=True, help='Override environments for the cloned experiment (can specify multiple)')
    @click.option('--project', '-p', help='Name of the project')
    def clone(source_experiment, target_experiment, environments, project):
        """Clone an existing experiment to create a variation.

        Creates a copy of an experiment, optionally with different environments.
        Useful for creating variations of production experiments.

        SOURCE_EXPERIMENT is the name of the experiment to clone from.
        TARGET_EXPERIMENT is the name for the new cloned experiment.

        Examples:
        - adare experiment clone firefox_test firefox_test_v2
        - adare experiment clone prod_exp dev_exp -e ubuntu22 -e debian12
        - adare experiment clone test1 test1_variant --project myproject
        """
        from adare.cli.experiment import exec_experiment_clone
        args = SimpleNamespace(
            source_experiment=source_experiment,
            target_experiment=target_experiment,
            environments=list(environments) if environments else None,
            project=project
        )
        exec_with_error_printing(exec_experiment_clone, args)


    @experiment.command()
    @click.argument('experiment', type=click.Path(exists=False))
    @click.option('-e', '--environment', type=click.Path(exists=False), required=True,
                  help='Name of the environment (must be QEMU-based)')
    @click.option('--project', '-p', help='Name of the project')
    def diff(experiment, environment, project):
        """Run experiment in visual diff mode for manual comparison.

        Diff mode is designed for visual comparison between different OS/software versions.
        It runs experiments in QEMU with GUI mode without agent installation.

        Features:
        - QEMU only (no agent installation)
        - Executes visual actions only (click, keyboard, screenshot)
        - Skips forensic actions (save_timestamp, pull, tests)
        - No database records (ephemeral)
        - For manual visual comparison between OS/software versions

        EXPERIMENT is the experiment name.

        Examples:
        - adare experiment diff test_csv -e ubuntu24
        - adare experiment diff firefox_test -e windows11 --project myproject
        """
        from adare.cli.diff import exec_experiment_diff
        args = SimpleNamespace(
            experiment=experiment,
            environment=environment,
            project=project
        )
        exec_with_error_printing(exec_experiment_diff, args)

    return experiment
