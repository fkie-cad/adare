import sys
import time
import logging
from types import SimpleNamespace
import click
from trogon import tui


class AliasedGroup(click.Group):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.aliases = {}

    def add_alias(self, alias, command_name):
        self.aliases[alias] = command_name

    def get_command(self, ctx, cmd_name):
        real = self.aliases.get(cmd_name, cmd_name)
        return super().get_command(ctx, real)

    def list_commands(self, ctx):
        # Only the canonical command names
        return sorted(super().list_commands(ctx))

    def format_commands(self, ctx, formatter):
        rows = []
        for name in self.list_commands(ctx):
            cmd = self.get_command(ctx, name)
            if cmd is None or cmd.hidden:
                continue
            # collect aliases pointing to this command
            alias_list = [a for a, target in self.aliases.items() if target == name]
            suffix = f" (aliases: {', '.join(alias_list)})" if alias_list else ""
            rows.append((name, cmd.get_short_help_str() + suffix))
        with formatter.section("Commands"):
            formatter.write_dl(rows)


# Internal imports - NOW LAZY LOADED inside functions
from adare.setup_logging import setup_logging
from adare.exceptions import LoggedException, LoggedErrorException
from adare.helperfunctions.output_formatter import get_formatter


def get_formatter_from_context():
    """Get output formatter from current Click context."""
    import click
    try:
        ctx = click.get_current_context()
        output_format = ctx.obj.output_format
        output_file = ctx.obj.output_file

        # Determine if dual output is desired:
        # When output-file is specified, user wants Rich console + structured file
        # (regardless of the format specified)
        dual_output = (output_file is not None)

        return get_formatter(output_format), output_file, dual_output
    except (RuntimeError, AttributeError):
        # Fallback if no context or missing attributes
        return get_formatter('rich'), None, False


def exec_with_error_printing(func, args):
    import asyncio
    import inspect
    
    try:
        if inspect.iscoroutinefunction(func):
            asyncio.run(func(args))
        else:
            func(args)
    except LoggedException as e:
        e.print()
        if isinstance(e, LoggedErrorException):
            sys.exit(-1)
        else:
            sys.exit(0)


# Global start time for runtime logging
START_TIME = time.time()


# Global CLI group with logging and version options
@tui()
@click.group(cls=AliasedGroup)
@click.option('--logfile', type=click.Path(), help='Path to logfile')
@click.option('--verbose', is_flag=True, help='Verbose output (loglevel=INFO)')
@click.option('--very-verbose', is_flag=True, help='Very verbose output (loglevel=DEBUG)')
@click.option('--log-level', help='Log level for logfile')
@click.option('--output-format', '--format', 'output_format',
              type=click.Choice(['rich', 'json', 'yaml'], case_sensitive=False),
              default='rich', show_default=True,
              help='Output format for commands that support structured data')
@click.option('--output-file', type=click.Path(),
              help='Save output to file instead of printing to console')
@click.version_option()  # Uses the package version if configured
@click.pass_context
def cli(ctx, logfile, verbose, very_verbose, log_level, output_format, output_file):
    """
    ADARE - the Automated Desktop Analysis framework for Reproducible Experiments.
    """
    ctx.ensure_object(SimpleNamespace)
    ctx.obj.logfile = logfile
    ctx.obj.verbose = verbose
    ctx.obj.very_verbose = very_verbose
    ctx.obj.log_level = log_level
    ctx.obj.output_format = output_format
    ctx.obj.output_file = output_file
    setup_logging(ctx.obj, sys.argv)


# Add aliases after CLI group is defined
cli.add_alias('exp', 'experiment')
cli.add_alias('environment', 'env')
cli.add_alias('tf', 'test')
cli.add_alias('testfunction', 'test')


# ------------------------------
# Database commands (was: manage *-db)
# ------------------------------
@cli.group(cls=AliasedGroup)
def db():
    """Database management commands."""
    pass

@db.command(name='init')
def db_init():
    """Initialize the database system."""
    from adare.cli.manage import exec_manage_init_db
    args = SimpleNamespace()
    exec_with_error_printing(exec_manage_init_db, args)

@db.command(name='status')
def db_status():
    """Check database system status."""
    from adare.cli.manage import exec_manage_db_status
    args = SimpleNamespace()
    exec_with_error_printing(exec_manage_db_status, args)

@db.command(name='reset')
def db_reset():
    """Reset the database (use with caution)."""
    from adare.cli.manage import exec_manage_reset_db
    args = SimpleNamespace()
    exec_with_error_printing(exec_manage_reset_db, args)

@db.command(name='repair')
def db_repair():
    """Repair the database system."""
    from adare.cli.manage import exec_manage_repair_db
    args = SimpleNamespace()
    exec_with_error_printing(exec_manage_repair_db, args)

@db.command(name='clean-install')
@click.option('--force', '-f', is_flag=True, help='Force clean installation without confirmation')
def db_clean_install(force):
    """Perform clean database installation (DANGER: deletes all data)."""
    from adare.cli.manage import exec_manage_clean_install_db
    args = SimpleNamespace(force=force)
    exec_with_error_printing(exec_manage_clean_install_db, args)


# ------------------------------
# OS Profile commands (was: manage os-profile)
# ------------------------------
@cli.group(name='os-profile', cls=AliasedGroup)
def os_profile():
    """OS profile management for VM creation."""
    pass

@os_profile.command(name='list')
def os_profile_list():
    """List all available OS profiles."""
    from adare.cli.manage_os_profile import exec_os_profile_list
    exec_with_error_printing(exec_os_profile_list, SimpleNamespace())

@os_profile.command(name='add')
@click.argument('profile_file', type=click.Path(exists=True))
def os_profile_add(profile_file):
    """Add a custom OS profile from a YAML file."""
    from adare.cli.manage_os_profile import exec_os_profile_add
    exec_with_error_printing(exec_os_profile_add, SimpleNamespace(profile_file=profile_file))

@os_profile.command(name='show')
@click.argument('name')
def os_profile_show(name):
    """Show detailed information about an OS profile."""
    from adare.cli.manage_os_profile import exec_os_profile_show
    exec_with_error_printing(exec_os_profile_show, SimpleNamespace(name=name))

@os_profile.command(name='remove')
@click.argument('name')
def os_profile_remove(name):
    """Remove a custom OS profile."""
    from adare.cli.manage_os_profile import exec_os_profile_remove
    exec_with_error_printing(exec_os_profile_remove, SimpleNamespace(name=name))

os_profile.add_alias('l', 'list')
os_profile.add_alias('rm', 'remove')


# ------------------------------
# Runtime commands (was: manage vm-runtime)
# ------------------------------
@cli.group(cls=AliasedGroup)
def runtime():
    """VM runtime management for current project."""
    pass

@runtime.command(name='refresh')
def runtime_refresh():
    """Refresh VM runtime files in current project, ensuring they are up-to-date."""
    from adare.cli.manage import exec_manage_vm_runtime_refresh
    args = SimpleNamespace()
    exec_with_error_printing(exec_manage_vm_runtime_refresh, args)

@runtime.command(name='build')
def runtime_build():
    """Build fresh VM runtime wheels (adarelib, adarevm) for current project."""
    from adare.cli.manage import exec_manage_vm_runtime_build
    args = SimpleNamespace()
    exec_with_error_printing(exec_manage_vm_runtime_build, args)


# ------------------------------
# Project commands
# ------------------------------
@cli.group(cls=AliasedGroup)
def project():
    """Project-related commands."""
    pass

@project.command()
@click.argument('name')
@click.option('--description', '-d', help='Description of the project')
def create(name, description):
    """Create a new project."""
    from adare.cli.project import exec_create_project
    args = SimpleNamespace(name=name, description=description)
    exec_with_error_printing(exec_create_project, args)

@project.command()
@click.argument('name')
def remove(name):
    """Remove a project."""
    from adare.cli.project import exec_remove_project
    args = SimpleNamespace(name=name)
    exec_with_error_printing(exec_remove_project, args)

@project.command(name='list')
def list_projects():
    """List all projects."""
    from adare.cli.project import exec_list_projects
    args = SimpleNamespace()
    exec_with_error_printing(exec_list_projects, args)

# Add aliases for project commands
project.add_alias('l', 'list')
project.add_alias('rm', 'remove')


# ------------------------------
# Environment commands
# ------------------------------
@cli.group(name='env', cls=AliasedGroup)
def env():
    """Environment management commands."""
    pass

@env.command()
@click.argument('environment', type=click.Path(exists=False))
@click.option('--project', '-p', help='Name of the project')
@click.option('--force', '-f', is_flag=True, help='Force update of the environment')
@click.option('--no-copy', is_flag=True, help='Keep VM file at original location instead of copying to managed storage (local files only). WARNING: Do not move or delete the original file!')
def load(environment, project, force, no_copy):
    """Load an environment.

    ENVIRONMENT can be:
    - Simple name: ubuntu24
    - Relative path: environments/ubuntu24.yml
    - Relative path: ./environments/ubuntu24.yaml

    The --no-copy flag prevents copying VM files to managed storage (~/.adare/state/vms).
    This is useful for large VMs or when disk space is limited.
    Note: The VM file must remain at the original location for experiments to work.
    """
    from adare.cli.environment import exec_environment_load
    args = SimpleNamespace(environment=environment, project=project, force=force, no_copy=no_copy)
    exec_with_error_printing(exec_environment_load, args)

@env.command()
@click.argument('name', type=click.Path(exists=False))
@click.option('--project', '-p', help='Name of the project')
@click.option('--with-vm', type=click.Path(exists=True), help='VM file path (OVA) to load automatically during environment creation')
def create(name, project, with_vm):
    """Create an environment.

    NAME can be:
    - Simple name: ubuntu24
    - Relative path: environments/ubuntu24
    """
    from adare.cli.environment import exec_environment_create
    args = SimpleNamespace(name=name, project=project, with_vm=with_vm)
    exec_with_error_printing(exec_environment_create, args)

@env.command()
@click.argument('identifier')
@click.option('--force', '-f', is_flag=True, help='Force deletion of the environment and any orphaned experiments')
def remove(identifier, force):
    """Remove an environment.

    IDENTIFIER can be:
    - Environment name: ubuntu24
    - Environment ULID: 01K72Q25GDNHWMEZB97N9RDPG0

    WARNING: If this environment is the only one used by experiments,
    those experiments will become orphaned and be removed when using --force.
    Without --force, removal will fail to prevent data loss."""
    from adare.cli.environment import exec_environment_delete
    args = SimpleNamespace(identifier=identifier, force=force)
    exec_with_error_printing(exec_environment_delete, args)


@env.command(name='list')
def list_environments():
    """List all environments in a project."""
    from adare.cli.show import exec_show_environments
    args = SimpleNamespace()
    exec_with_error_printing(exec_show_environments, args)

@env.command()
@click.argument('environment_name')
def info(environment_name):
    """Show detailed information about a specific environment."""
    from adare.cli.show import exec_show_environment
    args = SimpleNamespace(
        environment_name=environment_name,
    )
    exec_with_error_printing(exec_show_environment, args)

# Add aliases for environment commands
env.add_alias('l', 'list')
env.add_alias('rm', 'remove')


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

    # Resolve --log-level to a file_log_level int for the experiment run
    file_log_level = None
    if ctx.obj.log_level:
        from adare.config import ABBREV_DEBUG, ABBREV_INFO, ABBREV_WARNING, ABBREV_ERROR, ABBREV_CRITICAL
        level_mapping = {
            **{level: logging.DEBUG for level in ABBREV_DEBUG},
            **{level: logging.INFO for level in ABBREV_INFO},
            **{level: logging.WARNING for level in ABBREV_WARNING},
            **{level: logging.ERROR for level in ABBREV_ERROR},
            **{level: logging.CRITICAL for level in ABBREV_CRITICAL},
        }
        file_log_level = level_mapping.get(ctx.obj.log_level.strip().lower())

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
        very_verbose=ctx.obj.very_verbose,
        file_log_level=file_log_level
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
@click.option('--tags', '-t', help='Filter by tags (comma-separated, e.g. tool:Autopsy,goal:tool-test)')
def list_experiments(tags):
    """List all experiments in an environment."""
    from adare.cli.show import exec_show_experiments
    args = SimpleNamespace(tags=tags)
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
@click.option('-e', '--environment', type=click.Path(exists=False), help='Environment to check compatibility with')
@click.option('--project', '-p', help='Name of the project')
def validate(experiment, environment, project):
    """Validate experiment configuration and integrity without starting a VM.

    Performs fast pre-flight checks: directory structure, YAML schema,
    variable references, test references, environment compatibility,
    and integrity hashes.

    EXPERIMENT can be:
    - Simple name: test_csv
    - Relative path: experiments/test_csv
    """
    from adare.cli.experiment import exec_experiment_validate
    args = SimpleNamespace(
        experiment=experiment,
        environment=environment,
        project=project
    )
    exec_with_error_printing(exec_experiment_validate, args)


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


# ------------------------------
# Development mode commands
# ------------------------------
@cli.group(name='dev', cls=AliasedGroup)
def dev():
    """Development mode commands for interactive playbook development."""
    pass

@dev.command()
@click.option('-e', '--environment', required=True, help='Environment name')
@click.option('--project', '-p', help='Project name/path')
@click.option('--gui-mode', type=click.Choice(['auto', 'agent', 'host']),
              help='GUI execution mode: auto (default), agent (WebSocket), or host (QMP for QEMU)')
@click.option('--test-mode', type=click.Choice(['auto', 'agent', 'host']),
              help='Test execution mode: auto (default), agent (WebSocket), or host (QGA for QEMU)')
@click.option('--vm-memory', type=int, help='VM RAM in MB (default: 4096 for Linux, 8192 for Windows)')
@click.option('--vm-cpus', type=int, help='VM CPU count (default: 4)')
@click.option('--shared-dir', multiple=True, help='Shared directories in format HOST_PATH:VM_PATH')
@click.option('--debug-screenshots', is_flag=True, help='Save screenshots for debugging')
def start(environment, project, gui_mode, test_mode, vm_memory, vm_cpus, shared_dir, debug_screenshots):
    """Start a new dev mode session."""
    from adare.cli.dev import exec_dev_start
    args = SimpleNamespace(
        environment=environment,
        project=project,
        gui_mode=gui_mode,
        test_mode=test_mode,
        vm_memory=vm_memory,
        vm_cpus=vm_cpus,
        shared_dir=shared_dir,
        debug_screenshots=debug_screenshots
    )
    exec_with_error_printing(exec_dev_start, args)

@dev.command()
@click.argument('session_id', required=False)
@click.option('--project', '-p', help='Project name/path')

def resume(session_id, project):
    """Resume a stopped dev mode session.

    If SESSION_ID is provided, resumes that specific session.
    If SESSION_ID is omitted, resumes the most recently stopped session.

    Examples:
        adare dev resume                      # Resume most recent stopped session
        adare dev resume 01K72Q...            # Resume specific session by ID
    """
    from adare.cli.dev import exec_dev_resume
    args = SimpleNamespace(
        session_id=session_id,
        project=project
    )
    exec_with_error_printing(exec_dev_resume, args)

@dev.command()
@click.option('-s', '--session', 'session_id', default=None, help='Session ID (auto-detected if only one running)')
@click.option('--rm', is_flag=True, help='Remove all resources (VM, snapshots, database entries)')
def stop(session_id, rm):
    """Stop a dev mode session.

    Without --rm: Stops the VM but keeps all resources for future restart.
    With --rm: Completely removes the session and all associated resources.
    """
    from adare.cli.dev import exec_dev_stop
    args = SimpleNamespace(session_id=session_id, remove_resources=rm)
    exec_with_error_printing(exec_dev_stop, args)

@dev.command()
@click.option('-s', '--session', 'session_id', default=None, help='Session ID (auto-detected if only one running)')
def remove(session_id):
    """Remove a dev mode session and all resources (alias for 'stop --rm')."""
    from adare.cli.dev import exec_dev_stop
    args = SimpleNamespace(session_id=session_id, remove_resources=True)
    exec_with_error_printing(exec_dev_stop, args)

@dev.command()
@click.option('--project', '-p', help='Filter by project')
def list(project):
    """List active dev mode sessions."""
    from adare.cli.dev import exec_dev_list
    args = SimpleNamespace(project=project)
    exec_with_error_printing(exec_dev_list, args)

@dev.command()
@click.option('-s', '--session', 'session_id', default=None, help='Session ID (auto-detected if only one running)')
@click.option('-i', '--input', 'action_file', help='Action YAML file')
@click.option('-y', '--yaml', 'action_yaml', help='Inline YAML string')
@click.option('--stdin', is_flag=True, help='Read from stdin')
def action(session_id, action_file, action_yaml, stdin):
    """Execute a single action."""
    from adare.cli.dev import exec_dev_action
    args = SimpleNamespace(
        session_id=session_id,
        action_file=action_file,
        action_yaml=action_yaml,
        stdin=stdin
    )
    exec_with_error_printing(exec_dev_action, args)

@dev.command()
@click.option('-s', '--session', 'session_id', default=None, help='Session ID (auto-detected if only one running)')
@click.option('-f', '--file', 'playbook_file', help='Playbook YAML file')
@click.option('-u', '--url', help='Playbook URL')
@click.option('--stdin', is_flag=True, help='Read from stdin')
@click.option('--restore', is_flag=True, help='Restore to initial checkpoint before execution')
@click.option('--indices', help='Select specific action indices to execute (e.g. 1-3,5,7-9,S-5,7,23-E). S=start, E=end')
def playbook(session_id, playbook_file, url, stdin, restore, indices):
    """Execute a playbook."""
    from adare.cli.dev import exec_dev_playbook
    args = SimpleNamespace(
        session_id=session_id,
        playbook_file=playbook_file,
        url=url,
        stdin=stdin,
        restore=restore,
        indices=indices
    )
    exec_with_error_printing(exec_dev_playbook, args)

@dev.group(name='cv')
def dev_cv():
    """CV Server management commands."""
    pass

@dev_cv.command(name='start')
@click.option('-s', '--session', 'session_id', default=None, help='Session ID (auto-detected if only one running)')
@click.option('--debug/--no-debug', default=None, help='Enable/disable CV debug logging (default: keep existing)')
@click.option('--debug-output', '-o', type=click.Path(), help='Directory for debug screenshots')
def dev_cv_start(session_id, debug, debug_output):
    """Start/Restart CV server with logging options."""
    from adare.cli.dev import exec_dev_cv_start
    args = SimpleNamespace(
        session_id=session_id,
        debug=debug is True,
        no_debug=debug is False,
        debug_output=debug_output
    )
    exec_with_error_printing(exec_dev_cv_start, args)

@dev_cv.command(name='stop')
@click.option('-s', '--session', 'session_id', default=None, help='Session ID (auto-detected if only one running)')
def dev_cv_stop(session_id):
    """Stop CV server."""
    from adare.cli.dev import exec_dev_cv_stop
    args = SimpleNamespace(
        session_id=session_id
    )
    exec_with_error_printing(exec_dev_cv_stop, args)

@dev.group()
def reset():
    """Reset commands for dev session."""
    pass

@reset.command(name='soft')
@click.option('-s', '--session', 'session_id', default=None, help='Session ID (auto-detected if only one running)')
def reset_soft(session_id):
    """Soft reset: Reset variables only (<1 second)."""
    from adare.cli.dev import exec_dev_reset_soft
    args = SimpleNamespace(session_id=session_id)
    exec_with_error_printing(exec_dev_reset_soft, args)

@reset.command(name='hard')
@click.option('-s', '--session', 'session_id', default=None, help='Session ID (auto-detected if only one running)')
def reset_hard(session_id):
    """Hard reset: Full VM restore (10-30 seconds)."""
    from adare.cli.dev import exec_dev_reset_hard
    args = SimpleNamespace(session_id=session_id)
    exec_with_error_printing(exec_dev_reset_hard, args)

@dev.group()
def checkpoint():
    """Checkpoint management commands."""
    pass

@checkpoint.command(name='create')
@click.option('-s', '--session', 'session_id', default=None, help='Session ID (auto-detected if only one running)')
@click.argument('name')
@click.option('-d', '--description', default='', help='Checkpoint description')
def checkpoint_create(session_id, name, description):
    """Create a named checkpoint (live snapshot)."""
    from adare.cli.dev import exec_dev_checkpoint_create
    args = SimpleNamespace(session_id=session_id, name=name, description=description)
    exec_with_error_printing(exec_dev_checkpoint_create, args)

@checkpoint.command(name='restore')
@click.option('-s', '--session', 'session_id', default=None, help='Session ID (auto-detected if only one running)')
@click.argument('name')
def checkpoint_restore(session_id, name):
    """Restore to a named checkpoint."""
    from adare.cli.dev import exec_dev_checkpoint_restore
    args = SimpleNamespace(session_id=session_id, name=name)
    exec_with_error_printing(exec_dev_checkpoint_restore, args)

@checkpoint.command(name='list')
@click.option('-s', '--session', 'session_id', default=None, help='Session ID (auto-detected if only one running)')
def checkpoint_list(session_id):
    """List available checkpoints."""
    from adare.cli.dev import exec_dev_checkpoint_list
    args = SimpleNamespace(session_id=session_id)
    exec_with_error_printing(exec_dev_checkpoint_list, args)

@checkpoint.command(name='remove')
@click.option('-s', '--session', 'session_id', default=None, help='Session ID (auto-detected if only one running)')
@click.argument('name')
def checkpoint_remove(session_id, name):
    """Remove a checkpoint."""
    from adare.cli.dev import exec_dev_checkpoint_delete
    args = SimpleNamespace(session_id=session_id, name=name)
    exec_with_error_printing(exec_dev_checkpoint_delete, args)

@dev.command()
@click.option('-s', '--session', 'session_id', default=None, help='Session ID (auto-detected if only one running)')
def state(session_id):
    """Show session state (variables, stats, snapshots)."""
    from adare.cli.dev import exec_dev_state
    args = SimpleNamespace(session_id=session_id)
    exec_with_error_printing(exec_dev_state, args)

@dev.command()
@click.option('--project', '-p', help='Filter by project')
def cleanup(project):
    """Cleanup stale sessions."""
    from adare.cli.dev import exec_dev_cleanup
    args = SimpleNamespace(project=project)
    exec_with_error_printing(exec_dev_cleanup, args)

# Add dev command aliases
# Add dev command aliases
dev.add_alias('l', 'list')
dev.add_alias('res', 'reset')
dev.add_alias('cp', 'checkpoint')


@dev.command(name='update-testfunctions')
@click.option('-s', '--session', 'session_id', default=None, help='Session ID (auto-detected if only one running)')
def update_testfunctions(session_id):
    """Reload test functions in the running VM.

    This packages the current test files from the host and uploads them to the VM again.
    The adarevm agent will extract them to a new location and use them for subsequent tests.
    """
    from adare.cli.dev import exec_dev_update_testfunctions
    args = SimpleNamespace(session_id=session_id)
    exec_with_error_printing(exec_dev_update_testfunctions, args)


@dev.command(name='playbook-batch')
@click.argument('playbook_patterns', nargs=-1, required=True)
@click.option('-s', '--session', 'session_id', default=None, help='Session ID (auto-detected if only one running)')
@click.option('--checkpoint-name', default='batch_base', help='Base checkpoint name')
@click.option('--timeout', default=120, type=int, help='Checkpoint restore timeout in seconds')
def playbook_batch(session_id, playbook_patterns, checkpoint_name, timeout):
    """Execute multiple playbooks with checkpoint restoration.

    Supports both explicit paths and glob patterns:
    - adare dev playbook-batch playbook1.yml playbook2.yml
    - adare dev playbook-batch experiments/*/playbook.yml
    - adare dev playbook-batch playbooks/test_*.yml

    A base checkpoint is created before execution, and the VM is restored
    to this checkpoint after each playbook completes.
    """
    from adare.cli.dev import exec_dev_playbook_batch
    args = SimpleNamespace(
        session_id=session_id,
        playbook_patterns=list(playbook_patterns),
        checkpoint_name=checkpoint_name,
        timeout=timeout
    )
    exec_with_error_printing(exec_dev_playbook_batch, args)

# ------------------------------
# Test commands (was: testfunction)
# ------------------------------
@cli.group(name='test', cls=AliasedGroup)
def test():
    """Test function management commands."""
    pass

@test.command()
@click.argument('name', type=click.Path(exists=False))
@click.option('--project', '-p', help='Name of the project')
def create(name, project):
    """Create a new testfunction.

    NAME can be:
    - Simple name: my_test
    - Relative path: testfunctions/my_test
    """
    from adare.cli.testfunction import exec_create_testfunction
    args = SimpleNamespace(name=name, project=project)
    exec_with_error_printing(exec_create_testfunction, args)

@test.command()
@click.argument('name')
@click.option('--project', '-p', help='Name of the project')
def remove(name, project):
    """Remove a testfunction file by name.

    NAME is the testfunction file name (e.g., xml, json, csv).
    This will remove the entire testfunction file and all functions within it.
    """
    from adare.cli.testfunction import exec_remove_testfunction
    args = SimpleNamespace(name=name, project=project)
    exec_with_error_printing(exec_remove_testfunction, args)

@test.command()
@click.argument('name', type=click.Path(exists=False))
@click.option('--force', '-f', is_flag=True, help='Force overwrite if testfunction is used in experiments (will delete associated runs)')
def load(name, force):
    """Load a testfunction.

    NAME can be:
    - Testfunction name from appdata: standard, json, csv
    - Absolute path: /path/to/testfunction
    - Relative path: ./testfunctions/my_test

    By default, loading will skip testfunctions that are currently used in experiment runs.
    Use --force to overwrite and delete associated experiment runs.
    """
    from adare.cli.testfunction import exec_load_testfunction
    args = SimpleNamespace(name=name, force=force)
    exec_with_error_printing(exec_load_testfunction, args)

@test.command(name='list')
@click.option('--set', help='Filter testfunctions by set (e.g., standard)')
def list_testfunctions(set):
    """List all testfunctions."""
    from adare.cli.testfunction import exec_list_testfunctions
    args = SimpleNamespace(set=set)
    exec_with_error_printing(exec_list_testfunctions, args)

@test.command()
@click.option('--file-name', '-n', help='File name')
def show(file_name):
    """Show testfunctions with optional file filtering."""
    from adare.cli.show import exec_show_testfunctions
    args = SimpleNamespace(file_name=file_name)
    exec_with_error_printing(exec_show_testfunctions, args)

@test.command()
@click.argument('dotnotation')
def info(dotnotation):
    """Show detailed information about a specific testfunction."""
    from adare.cli.show import exec_show_testfunction
    args = SimpleNamespace(dotnotation=dotnotation)
    exec_with_error_printing(exec_show_testfunction, args)

# Add aliases for test commands
test.add_alias('l', 'list')
test.add_alias('rm', 'remove')


# ------------------------------
# VM management commands
# ------------------------------
@cli.group(cls=AliasedGroup)
def vm():
    """VM management commands."""
    pass

@vm.command(name='list')
def vm_list():
    """List all VMs in the system."""
    from adare.cli.vm import exec_vm_list
    args = SimpleNamespace()
    exec_with_error_printing(exec_vm_list, args)

@vm.command()
@click.argument('vm_id')
def info(vm_id):
    """Get detailed information about a VM."""
    from adare.cli.vm import exec_vm_info
    args = SimpleNamespace(vm_id=vm_id)
    exec_with_error_printing(exec_vm_info, args)

@vm.command()
@click.option('--id', 'instance_id', help='Remove specific instance by ULID')
@click.option('--stopped', is_flag=True, help='Remove all stopped instances')
@click.option('--experiment', 'experiment_id', help='Remove instances for specific experiment')
@click.option('--all', is_flag=True, help='Remove ALL instances including running (requires --force)')
@click.option('--env', 'environment_ulid', help='Remove all VMs for a specific environment (requires --force)')
@click.option('--force', is_flag=True, help='Force removal of running instances')
def remove(instance_id, stopped, experiment_id, all, environment_ulid, force):
    """Remove VM instances.

    Examples:
        adare vm remove --id <ulid>              # specific instance
        adare vm remove --stopped                 # all stopped instances
        adare vm remove --experiment <id>         # instances for experiment
        adare vm remove --all --force             # ALL instances (running or not)
        adare vm remove --env <ulid> --force      # all VMs for environment
    """
    from adare.cli.vm import exec_vm_instance_remove
    args = SimpleNamespace(
        instance_id=instance_id,
        stopped=stopped,
        experiment_id=experiment_id,
        all=all,
        environment_ulid=environment_ulid,
        force=force
    )
    exec_with_error_printing(exec_vm_instance_remove, args)

@vm.command()
def usage():
    """Show VM instance usage statistics."""
    from adare.cli.vm import exec_vm_instance_usage
    args = SimpleNamespace()
    exec_with_error_printing(exec_vm_instance_usage, args)

@vm.command()
@click.argument('ova_file', type=click.Path(exists=True))
@click.option('--platform', '-p', required=True, type=click.Choice(['linux', 'windows']), help='VM platform (required)')
@click.option('--verbose', '-v', is_flag=True, help='Enable verbose output with detailed error information')
@click.option('--keep-vm', is_flag=True, help='Keep the test VM after completion (for further testing)')
@click.option('--remove-vm', is_flag=True, help='Automatically remove the test VM after completion')
def test(ova_file, platform, verbose, keep_vm, remove_vm):
    """Test OVA file compatibility with ADARE.
    
    This command validates an .ova file by:
    - Importing the VM temporarily 
    - Setting up shared directories and mounting them
    - Installing dependencies and starting adarevm
    - Establishing WebSocket connection
    - Taking a screenshot and performing a test click
    - Cleaning up all temporary resources
    
    Example: adare vm test ubuntu22.ova --platform linux
    Example: adare vm test windows11.ova --platform windows --verbose
    Example: adare vm test ubuntu22.ova --platform linux --keep-vm
    Example: adare vm test ubuntu22.ova --platform linux --remove-vm
    """
    # Handle cleanup options
    if keep_vm and remove_vm:
        click.echo("Error: Cannot specify both --keep-vm and --remove-vm", err=True)
        return
    
    vm_cleanup_mode = 'prompt'  # Default
    if keep_vm:
        vm_cleanup_mode = 'keep'
    elif remove_vm:
        vm_cleanup_mode = 'remove'
    
    from adare.cli.vm import exec_vm_test
    args = SimpleNamespace(
        ova_file=ova_file, 
        platform=platform, 
        verbose=verbose,
        vm_cleanup_mode=vm_cleanup_mode
    )
    exec_with_error_printing(exec_vm_test, args)

# Nested group for snapshot management
@vm.group(cls=AliasedGroup)
def snapshot():
    """Snapshot management commands."""
    pass

@snapshot.command(name='list')
@click.option('--instance', '-i', 'instance_id', help='Filter by specific VM instance ID')
def snapshot_list(instance_id):
    """List all snapshots. Use --instance to filter by specific VM instance."""
    from adare.cli.vm import exec_vm_list_snapshots
    args = SimpleNamespace(instance_id=instance_id)
    exec_with_error_printing(exec_vm_list_snapshots, args)

@snapshot.command()
@click.argument('instance_id')
@click.argument('snapshot_name')
def remove(instance_id, snapshot_name):
    """Delete a single snapshot from a specific VM instance."""
    from adare.cli.vm import exec_vm_delete_snapshot
    args = SimpleNamespace(instance_id=instance_id, snapshot_name=snapshot_name)
    exec_with_error_printing(exec_vm_delete_snapshot, args)

@vm.command(name='create')
@click.argument('os_name')
@click.option('--iso', type=click.Path(exists=True), help='Path to OS ISO (required for Windows)')
@click.option('--name', help='VM name (auto-generated if not set)')
@click.option('--disk-size', default=None, help='Disk size (default: 60G Linux, 80G Windows)')
@click.option('--ram', type=int, default=None, help='RAM in MB')
@click.option('--cpus', type=int, default=None, help='CPU count')
@click.option('--force', is_flag=True, default=False, help='Overwrite existing VM disk image')
@click.option('--vm-dir', type=click.Path(), default=None, help='Directory for VM disk image (default: ~/.adare/state/vms/)')
@click.option('--setup', type=click.Choice(['bare', 'base', 'full', 'agent'], case_sensitive=False),
              default='full', help='Setup level: bare (OS only), base (+ guest tools), full (+ Python, default), agent (+ adarevm, deferred)')
@click.option('--env-name', default=None, help='Environment file name (defaults to VM name)')
@click.option('--interactive', is_flag=True, default=False, help='Boot VM after install for manual software installation')
@click.option('--arch', type=click.Choice(['x86_64', 'aarch64']), default=None, help='Override CPU architecture (default: from OS profile)')
def vm_create(os_name, iso, name, disk_size, ram, cpus, force, vm_dir, setup, env_name, interactive, arch):
    """Create a new ADARE-ready VM from scratch.

    OS_NAME is the target OS: ubuntu2404, ubuntu2204, windows11, windows11arm64, windows10

    \b
    Examples:
      adare vm create ubuntu2404
      adare vm create ubuntu2404 --setup bare
      adare vm create ubuntu2404 --setup base
      adare vm create ubuntu2404 --interactive
      adare vm create windows11 --iso /path/to/Win11.iso
      adare vm create windows11arm64 --iso /path/to/Win11_ARM64.iso
      adare vm create windows11 --arch aarch64 --iso /path/to/Win11_ARM64.iso
      adare vm create ubuntu2204 --name my-ubuntu --disk-size 100G --ram 8192
      adare vm create ubuntu2404 --name my-vm --env-name my-env
      adare vm create ubuntu2404 --vm-dir /tmp/my-vms
    """
    from adare.cli.vm_create import exec_vm_create
    args = SimpleNamespace(os_name=os_name, iso=iso, name=name, disk_size=disk_size, ram=ram, cpus=cpus, force=force, vm_dir=vm_dir, setup_level=setup, env_name=env_name, interactive=interactive, arch=arch)
    exec_with_error_printing(exec_vm_create, args)

@vm.command(name='reset')
@click.option('--force', '-f', is_flag=True, help='Force reset of all VMs (required for confirmation)')
def vm_reset(force):
    """Reset all VMs in the system (use with caution)."""
    from adare.cli.manage import exec_manage_reset_vm
    args = SimpleNamespace(force=force)
    exec_with_error_printing(exec_manage_reset_vm, args)

# Add aliases for vm commands
vm.add_alias('l', 'list')
vm.add_alias('rm', 'remove')

# Add aliases for snapshot commands
snapshot.add_alias('l', 'list')
snapshot.add_alias('rm', 'remove')


# ------------------------------
# Run management commands
# ------------------------------
@cli.group(cls=AliasedGroup)
def run():
    """Experiment run management commands."""
    pass

@run.command(name='list')
@click.option('--filter', help='Filter by dotnotation: [project][.environment][.experiment]')
def list_runs(filter):
    """List all experiment runs. Use --filter with dotnotation for advanced filtering."""
    from adare.cli.show import exec_show_runs
    args = SimpleNamespace(filter=filter)
    exec_with_error_printing(exec_show_runs, args)

@run.command()
@click.argument('ulid', required=False)
def info(ulid):
    """Show detailed information about a run. Shows latest run if no ULID provided."""
    from adare.cli.show import exec_show_run
    args = SimpleNamespace(ulid=ulid)
    exec_with_error_printing(exec_show_run, args)

@run.command()
@click.argument('ulid', required=True)
def remove(ulid):
    """Remove a single experiment run by its ULID."""
    from adare.cli.show import exec_remove_run
    args = SimpleNamespace(ulid=ulid)
    exec_with_error_printing(exec_remove_run, args)

# Add aliases for run commands
run.add_alias('l', 'list')
run.add_alias('rm', 'remove')

# ------------------------------
# Web interface commands
# ------------------------------
@cli.group()
def web():
    """Web interface commands."""
    pass

@web.command()
def login():
    """Login to the web interface."""
    from adare.cli.web import exec_web_login
    args = SimpleNamespace()
    exec_with_error_printing(exec_web_login, args)

@web.command()
def logout():
    """Logout from the web interface."""
    from adare.cli.web import exec_web_logout
    args = SimpleNamespace()
    exec_with_error_printing(exec_web_logout, args)

@web.command()
def status():
    """Show the web login status."""
    from adare.cli.web import exec_web_status
    args = SimpleNamespace()
    exec_with_error_printing(exec_web_status, args)

# Nested group for web download commands
@web.group()
def download():
    """Download experiments, testfunctions, or environments from the web."""
    pass

@download.command(name='experiment')
@click.argument('ulid')
def download_experiment(ulid):
    """Download an experiment."""
    from adare.cli.web import exec_download_experiment
    args = SimpleNamespace(ulid=ulid)
    exec_with_error_printing(exec_download_experiment, args)

@download.command(name='testfunction')
@click.argument('name')
@click.option('--version', '-v', type=int, default=None, help='Specific version to download (default: latest)')
def download_testfunction(name, version):
    """Download a testfunction."""
    from adare.cli.web import exec_download_testfunction
    args = SimpleNamespace(name=name, version=version)
    exec_with_error_printing(exec_download_testfunction, args)

@download.command(name='environment')
@click.argument('name')
def download_environment(name):
    """Download an environment."""
    from adare.cli.web import exec_download_environment
    args = SimpleNamespace(name=name)
    exec_with_error_printing(exec_download_environment, args)

@download.command(name='bundle')
@click.argument('ulid')
@click.option('--include-disk-images', is_flag=True, default=False, help='Also download disk images')
@click.option('--project', '-p', help='Name of the project')
def download_bundle(ulid, include_disk_images, project):
    """Download an experiment bundle (experiment + all dependencies)."""
    from adare.cli.web import exec_download_bundle
    args = SimpleNamespace(ulid=ulid, include_disk_images=include_disk_images, project=project)
    exec_with_error_printing(exec_download_bundle, args)

@web.command()
@click.argument('ulid')
@click.option('--project', '-p', help='Name of the project')
def publish(ulid, project):
    """Publish an experiment run to the server with progress tracking."""
    from adare.cli.web import exec_web_publish_run
    args = SimpleNamespace(ulid=ulid, project=project)
    exec_with_error_printing(exec_web_publish_run, args)

# Nested group for web check commands
@web.group()
def check():
    """Check if resources exist on the server."""
    pass

@check.command(name='experiment')
@click.argument('ulid')
def check_experiment(ulid):
    """Check if an experiment exists on the server."""
    from adare.cli.web import exec_web_check_experiment
    args = SimpleNamespace(ulid=ulid)
    exec_with_error_printing(exec_web_check_experiment, args)

@check.command(name='run')
@click.argument('ulid')
def check_run(ulid):
    """Check if an experiment run exists on the server."""
    from adare.cli.web import exec_web_check_run
    args = SimpleNamespace(ulid=ulid)
    exec_with_error_printing(exec_web_check_run, args)

@web.command()
@click.option('--project', '-p', help='Name of the project')
def sync(project):
    """Sync all environments and experiments with the web interface."""
    from adare.cli.web import exec_web_sync
    args = SimpleNamespace(project=project)
    exec_with_error_printing(exec_web_sync, args)

# Nested group for web submit commands
@web.group()
def submit():
    """Submit experiments, testfunctions, or environments as PRs."""
    pass

@submit.command(name='experiment')
@click.argument('name')
@click.option('--project', '-p', help='Name of the project')
def submit_experiment(name, project):
    """Submit an experiment as a PR to the shared repository."""
    from adare.cli.web import exec_submit_experiment
    args = SimpleNamespace(name=name, project=project)
    exec_with_error_printing(exec_submit_experiment, args)

@submit.command(name='testfunction')
@click.argument('name')
@click.option('--project', '-p', help='Name of the project')
def submit_testfunction(name, project):
    """Submit a testfunction as a PR to the shared repository."""
    from adare.cli.web import exec_submit_testfunction
    args = SimpleNamespace(name=name, project=project)
    exec_with_error_printing(exec_submit_testfunction, args)

@submit.command(name='environment')
@click.argument('name')
@click.option('--project', '-p', help='Name of the project')
def submit_environment(name, project):
    """Submit an environment as a PR to the shared repository."""
    from adare.cli.web import exec_submit_environment
    args = SimpleNamespace(name=name, project=project)
    exec_with_error_printing(exec_submit_environment, args)

# Web UI commands (start, build, services)
from adare.cli.web_cmd import web_start, web_build, web_services
web.add_command(web_start, "start")
web.add_command(web_build, "build")
web.add_command(web_services, "services")


# ------------------------------
# CV Server testing commands (was: dev mcp)
# ------------------------------
@cli.group(cls=AliasedGroup)
def cv():
    """CV server testing commands for icon/text recognition."""
    pass

@cv.command(name='test-icon')
@click.option('--icon', required=True, type=click.Path(exists=True), help='Path to icon image file')
@click.option('--screenshot', required=True, type=click.Path(exists=True), help='Path to screenshot image file')
@click.option('--output', type=click.Path(), help='Path to save marked image with found locations')
@click.option('--host', default='localhost', help='CV server host (default: localhost)')
@click.option('--port', type=int, default=13109, help='CV server port (default: 13109)')
@click.option('--threshold', type=float, default=0.6, help='Match threshold (0.0-1.0, default: 0.6)')
@click.option('--mcplog', type=click.Path(), help='Path to save CV server logs')
def cv_test_icon(icon, screenshot, output, host, port, threshold, mcplog):
    """Test CV server icon finding functionality.

    Automatically starts CV server, finds an icon in a screenshot,
    prints coordinates of all matches, and stops the server.
    Optionally saves a marked image showing found locations.
    """
    from adare.cli.mcp import exec_mcp_test_icon
    args = SimpleNamespace(
        icon_path=icon,
        screenshot_path=screenshot,
        output_path=output,
        host=host,
        port=port,
        threshold=threshold,
        mcplog_path=mcplog
    )
    exec_with_error_printing(exec_mcp_test_icon, args)

@cv.command(name='test-text')
@click.argument('text')
@click.option('--screenshot', required=True, type=click.Path(exists=True), help='Path to screenshot image file')
@click.option('--format', default='json', help='Output format: json or csv (default: json)')
@click.option('--host', default='localhost', help='CV server host (default: localhost)')
@click.option('--port', type=int, default=13109, help='CV server port (default: 13109)')
def cv_test_text(text, screenshot, format, host, port):
    """Test CV server text finding functionality.

    TEXT is the text string to search for in the screenshot.
    Automatically starts CV server, finds text matches,
    prints coordinates, and stops the server.
    """
    from adare.cli.mcp import exec_mcp_test_text
    args = SimpleNamespace(
        text=text,
        screenshot_path=screenshot,
        format=format,
        host=host,
        port=port
    )
    exec_with_error_printing(exec_mcp_test_text, args)

@cv.command(name='get-all-text')
@click.option('--screenshot', required=True, type=click.Path(exists=True), help='Path to screenshot image file')
@click.option('--format', default='json', help='Output format: json or csv (default: json)')
@click.option('--host', default='localhost', help='CV server host (default: localhost)')
@click.option('--port', type=int, default=13109, help='CV server port (default: 13109)')
def cv_get_all_text(screenshot, format, host, port):
    """Get all detected text from screenshot using OCR.

    Automatically starts CV server, runs OCR on the screenshot,
    returns all detected text with coordinates and confidence scores,
    then stops the server.
    """
    from adare.cli.mcp import exec_mcp_get_all_text
    args = SimpleNamespace(
        screenshot_path=screenshot,
        format=format,
        host=host,
        port=port
    )
    exec_with_error_printing(exec_mcp_get_all_text, args)


# ------------------------------
# WebSocket commands (was: dev ws)
# ------------------------------
@cli.group(cls=AliasedGroup)
def ws():
    """WebSocket adarevm interaction commands."""
    pass

@ws.command()
@click.argument('action_file', type=click.Path(exists=True))
@click.option('--host', default='localhost', help='AdareVM host (default: localhost)')
@click.option('--port', type=int, default=18765, help='AdareVM WebSocket port (default: 18765)')
@click.option('--vm-instance', help='VM instance name to look up WebSocket port (overrides --port)')
@click.option('--connect-timeout', type=float, default=10.0, help='Connection timeout in seconds (default: 10.0)')
@click.option('--default-timeout', type=float, default=30.0, help='Default action timeout in seconds (default: 30.0)')
@click.option('--continue-on-error', is_flag=True, help='Continue executing actions even if one fails')
@click.option('--output-format', type=click.Choice(['json', 'yaml', 'summary', 'simple']),
              default='simple', help='Output format (default: simple)')
def action(action_file, host, port, vm_instance, connect_timeout, default_timeout, continue_on_error, output_format):
    """Execute actions from YAML file on adarevm via WebSocket.

    ACTION_FILE: Path to YAML file containing actions to execute

    Examples:
        adare ws action test.yml --host 192.168.1.100 --port 18765
        adare ws action test.yml --vm-instance my-vm-instance
    """
    from adare.cli.ws import exec_ws_action
    args = SimpleNamespace(
        action_file=action_file,
        host=host,
        port=port,
        vm_instance=vm_instance,
        connect_timeout=connect_timeout,
        default_timeout=default_timeout,
        continue_on_error=continue_on_error,
        output_format=output_format
    )
    exec_with_error_printing(exec_ws_action, args)

@ws.command(name='example')
@click.argument('output_file', type=click.Path())
def ws_create_example(output_file):
    """Create an example action YAML file."""
    from adare.cli.ws import create_example_action_file
    from pathlib import Path
    create_example_action_file(Path(output_file))

# ------------------------------
# Web Server commands
# ------------------------------
@cli.group(name='server', cls=AliasedGroup)
def server():
    """ADARE web server for dev mode session control."""
    pass

@server.command()
@click.option('--port', type=int, default=8089, help='Server port (default: 8089)')
@click.option('--host', default='127.0.0.1', help='Server host (default: 127.0.0.1)')
@click.option('--dev', is_flag=True, help='Run in development mode with auto-reload')
def start(port, host, dev):
    """Start the ADARE web server."""
    from adare.cli.webserver import exec_webserver_start
    args = SimpleNamespace(port=port, host=host, dev=dev)
    exec_with_error_printing(exec_webserver_start, args)


# ------------------------------
# Status command
# ------------------------------
@cli.command(name='status')
def cli_status():
    """Show quick overview: current project, active sessions, VM count, db status."""
    from adare.cli.status import exec_status
    args = SimpleNamespace()
    exec_with_error_printing(exec_status, args)


# ------------------------------
# Help commands
# ------------------------------
@cli.group()
def help():
    """Show help for special options."""
    pass


def main():
    cli()
    runtime = (time.time() - START_TIME) / 60
    logging.getLogger(__name__).debug(f"--- Runtime {runtime} minutes ---")
    logging.shutdown()


if __name__ == '__main__':
    main()