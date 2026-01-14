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
cli.add_alias('env', 'environment') 
cli.add_alias('tf', 'testfunction')


# ------------------------------
# Manage commands
# ------------------------------
@cli.group()
def manage():
    """Manage commands (wrapper for management-related operations)."""
    pass

@manage.command(name='reset-db')
def reset_db():
    """Reset the database (use with caution)."""
    from adare.cli.manage import exec_manage_reset_db
    args = SimpleNamespace()
    exec_with_error_printing(exec_manage_reset_db, args)

@manage.command(name='init-db')
def init_db():
    """Initialize the database system."""
    from adare.cli.manage import exec_manage_init_db
    args = SimpleNamespace()
    exec_with_error_printing(exec_manage_init_db, args)

@manage.command(name='db-status')
def db_status():
    """Check database system status."""
    from adare.cli.manage import exec_manage_db_status
    args = SimpleNamespace()
    exec_with_error_printing(exec_manage_db_status, args)

@manage.command(name='repair-db')
def repair_db():
    """Repair the database system."""
    from adare.cli.manage import exec_manage_repair_db
    args = SimpleNamespace()
    exec_with_error_printing(exec_manage_repair_db, args)

@manage.command(name='clean-install-db')
@click.option('--force', '-f', is_flag=True, help='Force clean installation without confirmation')
def clean_install_db(force):
    """Perform clean database installation (DANGER: deletes all data)."""
    from adare.cli.manage import exec_manage_clean_install_db
    args = SimpleNamespace(force=force)
    exec_with_error_printing(exec_manage_clean_install_db, args)

@manage.command(name='reset-vm')
@click.option('--force', '-f', is_flag=True, help='Force deletion of all VMs (required for confirmation)')
def reset_vm(force):
    """Reset all VMs in the system (use with caution)."""
    from adare.cli.manage import exec_manage_reset_vm
    args = SimpleNamespace(force=force)
    exec_with_error_printing(exec_manage_reset_vm, args)

@manage.group(name='vm-runtime')
def vm_runtime():
    """VM runtime management for current project."""
    pass

@vm_runtime.command(name='refresh')
def vm_runtime_refresh():
    """Refresh VM runtime files in current project, ensuring they are up-to-date."""
    from adare.cli.manage import exec_manage_vm_runtime_refresh
    args = SimpleNamespace()
    exec_with_error_printing(exec_manage_vm_runtime_refresh, args)


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
@cli.group(name='environment', cls=AliasedGroup)
def environment():
    """Environment-related commands."""
    pass

@environment.command()
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

@environment.command()
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

@environment.command()
@click.argument('identifier')
@click.option('--force', '-f', is_flag=True, help='Force deletion of the environment and any orphaned experiments')
def remove(identifier, force):
    """Delete an environment.

    IDENTIFIER can be:
    - Environment name: ubuntu24
    - Environment ULID: 01K72Q25GDNHWMEZB97N9RDPG0

    WARNING: If this environment is the only one used by experiments,
    those experiments will become orphaned and be deleted when using --force.
    Without --force, deletion will fail to prevent data loss."""
    from adare.cli.environment import exec_environment_delete
    args = SimpleNamespace(identifier=identifier, force=force)
    exec_with_error_printing(exec_environment_delete, args)


@environment.command(name='list')
def list_environments():
    """List all environments in a project."""
    from adare.cli.show import exec_show_environments
    args = SimpleNamespace()
    exec_with_error_printing(exec_show_environments, args)

@environment.command()
@click.argument('environment_name')
def info(environment_name):
    """Show detailed information about a specific environment."""
    from adare.cli.show import exec_show_environment
    args = SimpleNamespace(
        environment_name=environment_name,
    )
    exec_with_error_printing(exec_show_environment, args)

# Add aliases for environment commands
environment.add_alias('l', 'list')
environment.add_alias('rm', 'remove')


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
@click.option('--production', '-p', is_flag=True, help='Run the experiment in production mode - creates real runs with integrity checks (default: test mode)')
@click.option('--debug-screenshots', is_flag=True, help='Save screenshots to experiment run directory for debugging')
@click.option('--preserve-snapshot', '-s', is_flag=True, help='Create experiment snapshot for preservation (default: only reset to base snapshot)')
@click.option('--no-runlog', is_flag=True, help='Do not save adare log to the run/logs directory')
@click.option('--vm-memory', type=int, help='VM RAM in MB (default: 4096 for Linux, 8192 for Windows)')
@click.option('--vm-cpus', type=int, help='VM CPU count (default: 4)')
@click.option('--gui-mode', type=click.Choice(['auto', 'agent', 'host']), help='GUI execution mode: auto (default), agent (WebSocket), or host (QMP for QEMU only)')
@click.option('--project', help='Name of the project')
@click.pass_context
def run(ctx, experiment, environment, production, debug_screenshots, preserve_snapshot, no_runlog, vm_memory, vm_cpus, gui_mode, project):
    """Run an experiment in a given environment or all environments if none specified.

    By default, runs in TEST mode (creates fake runs, skips integrity checks, allows modifications).
    Use --production/-p for real production runs with full integrity validation.

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
        project=project,
        verbose=ctx.obj.verbose,
        very_verbose=ctx.obj.very_verbose
    )
    exec_with_error_printing(exec_experiment_run, args)

@experiment.command()
@click.argument('experiment', type=click.Path(exists=False))
@click.option('-e', '--environment', type=click.Path(exists=False), required=True, help='Name of the environment')
@click.option('--project', '-p', help='Name of the project')
def develop(experiment, environment, project):
    """Run an experiment in test mode."""
    from adare.cli.experiment import exec_experiment_test
    args = SimpleNamespace(
        experiment=experiment,
        environment=environment,
        project=project
    )
    exec_with_error_printing(exec_experiment_test, args)

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
@click.argument('experiment', type=click.Path(exists=False))
@click.option('-e', '--environment', type=click.Path(exists=False), required=True, help='Name of the environment')
@click.option('--project', '-p', help='Name of the project')
@click.option('--port', type=int, default=8080, help='Port for the web interface (default: 8080)')
def dev(experiment, environment, project, port):
    """Start interactive development mode for an experiment.
    
    This would start a web-based interface for interactive development and testing
    of experiment playbooks, but is currently not implemented.
    """
    from adare.cli.interactive import exec_experiment_dev
    args = SimpleNamespace(
        experiment=experiment,
        environment=environment,
        project=project,
        port=port
    )
    exec_with_error_printing(exec_experiment_dev, args)

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


# ------------------------------
# Development mode commands
# ------------------------------
@cli.group(name='dev', cls=AliasedGroup)
def dev():
    """Development mode commands for interactive playbook development."""
    pass

@dev.command()
@click.argument('experiment')
@click.option('-e', '--environment', required=True, help='Environment name')
@click.option('--project', '-p', help='Project name/path')
def start(experiment, environment, project):
    """Start a new dev mode session."""
    from adare.cli.dev import exec_dev_start
    args = SimpleNamespace(experiment=experiment, environment=environment, project=project)
    exec_with_error_printing(exec_dev_start, args)

@dev.command()
@click.argument('session_id')
def stop(session_id):
    """Stop a dev mode session."""
    from adare.cli.dev import exec_dev_stop
    args = SimpleNamespace(session_id=session_id)
    exec_with_error_printing(exec_dev_stop, args)

@dev.command()
@click.option('--project', '-p', help='Filter by project')
def list(project):
    """List active dev mode sessions."""
    from adare.cli.dev import exec_dev_list
    args = SimpleNamespace(project=project)
    exec_with_error_printing(exec_dev_list, args)

@dev.command()
@click.argument('session_id')
@click.option('-f', '--file', 'action_file', help='Action YAML file')
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
@click.argument('session_id')
@click.option('-f', '--file', 'playbook_file', help='Playbook YAML file')
@click.option('-u', '--url', help='Playbook URL')
@click.option('--stdin', is_flag=True, help='Read from stdin')
def playbook(session_id, playbook_file, url, stdin):
    """Execute a playbook."""
    from adare.cli.dev import exec_dev_playbook
    args = SimpleNamespace(
        session_id=session_id,
        playbook_file=playbook_file,
        url=url,
        stdin=stdin
    )
    exec_with_error_printing(exec_dev_playbook, args)

@dev.command(name='reset-soft')
@click.argument('session_id')
def reset_soft(session_id):
    """Soft reset: Reset variables only (<1 second)."""
    from adare.cli.dev import exec_dev_reset_soft
    args = SimpleNamespace(session_id=session_id)
    exec_with_error_printing(exec_dev_reset_soft, args)

@dev.command(name='reset-hard')
@click.argument('session_id')
def reset_hard(session_id):
    """Hard reset: Full VM restore (10-30 seconds)."""
    from adare.cli.dev import exec_dev_reset_hard
    args = SimpleNamespace(session_id=session_id)
    exec_with_error_printing(exec_dev_reset_hard, args)

@dev.command(name='checkpoint-create')
@click.argument('session_id')
@click.argument('name')
@click.option('-d', '--description', default='', help='Checkpoint description')
def checkpoint_create(session_id, name, description):
    """Create a named checkpoint (live snapshot)."""
    from adare.cli.dev import exec_dev_checkpoint_create
    args = SimpleNamespace(session_id=session_id, name=name, description=description)
    exec_with_error_printing(exec_dev_checkpoint_create, args)

@dev.command(name='checkpoint-restore')
@click.argument('session_id')
@click.argument('name')
def checkpoint_restore(session_id, name):
    """Restore to a named checkpoint."""
    from adare.cli.dev import exec_dev_checkpoint_restore
    args = SimpleNamespace(session_id=session_id, name=name)
    exec_with_error_printing(exec_dev_checkpoint_restore, args)

@dev.command(name='checkpoint-list')
@click.argument('session_id')
def checkpoint_list(session_id):
    """List available checkpoints."""
    from adare.cli.dev import exec_dev_checkpoint_list
    args = SimpleNamespace(session_id=session_id)
    exec_with_error_printing(exec_dev_checkpoint_list, args)

@dev.command()
@click.argument('session_id')
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
dev.add_alias('l', 'list')
dev.add_alias('rs', 'reset-soft')
dev.add_alias('rh', 'reset-hard')
dev.add_alias('cc', 'checkpoint-create')
dev.add_alias('cr', 'checkpoint-restore')
dev.add_alias('cl', 'checkpoint-list')


# ------------------------------
# Testfunction commands
# ------------------------------
@cli.group(cls=AliasedGroup)
def testfunction():
    """Testfunction-related commands."""
    pass

@testfunction.command()
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

@testfunction.command()
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

@testfunction.command()
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

@testfunction.command(name='list')
@click.option('--set', help='Filter testfunctions by set (e.g., standard)')
def list_testfunctions(set):
    """List all testfunctions."""
    from adare.cli.testfunction import exec_list_testfunctions
    args = SimpleNamespace(set=set)
    exec_with_error_printing(exec_list_testfunctions, args)

@testfunction.command()
@click.option('--file-name', '-f', help='File name')
def show(file_name):
    """Show testfunctions with optional file filtering."""
    from adare.cli.show import exec_show_testfunctions
    args = SimpleNamespace(file_name=file_name)
    exec_with_error_printing(exec_show_testfunctions, args)

@testfunction.command()
@click.argument('dotnotation')
def info(dotnotation):
    """Show detailed information about a specific testfunction."""
    from adare.cli.show import exec_show_testfunction
    args = SimpleNamespace(dotnotation=dotnotation)
    exec_with_error_printing(exec_show_testfunction, args)

# Add aliases for testfunction commands
testfunction.add_alias('l', 'list')
testfunction.add_alias('rm', 'remove')


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
@click.option('--instance-id', help='Remove specific instance by ULID')
@click.option('--all', is_flag=True, help='Remove all stopped instances')
@click.option('--experiment-id', help='Remove instances for specific experiment')
def remove(instance_id, all, experiment_id):
    """Remove VM instances. Running instances cannot be removed."""
    from adare.cli.vm import exec_vm_instance_remove
    args = SimpleNamespace(
        instance_id=instance_id,
        all=all,
        experiment_id=experiment_id
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
    - Installing poetry dependencies and starting adarevm
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

# Nested group for VM cleanup commands
@vm.group()
def clear():
    """Clear (delete) VMs from the system."""
    pass

@clear.command(name='all')
@click.option('--force', '-f', is_flag=True, help='Force deletion of all VMs (required for confirmation)')
def clear_all(force):
    """Clear ALL VMs from the system."""
    from adare.cli.vm import exec_vm_clear_all
    args = SimpleNamespace(force=force)
    exec_with_error_printing(exec_vm_clear_all, args)

@clear.command(name='environment')
@click.argument('environment_ulid')
@click.option('--force', '-f', is_flag=True, help='Force deletion of environment VMs (required for confirmation)')
def clear_environment(environment_ulid, force):
    """Clear all VMs associated with a specific environment."""
    from adare.cli.vm import exec_vm_clear_by_environment
    args = SimpleNamespace(environment_ulid=environment_ulid, force=force)
    exec_with_error_printing(exec_vm_clear_by_environment, args)

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
@click.option('--filter', '-f', help='Filter by dotnotation: [project][.environment][.experiment]')
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
def download_testfunction(name):
    """Download a testfunction."""
    from adare.cli.web import exec_download_testfunction
    args = SimpleNamespace(name=name)
    exec_with_error_printing(exec_download_testfunction, args)

@download.command(name='environment')
@click.argument('name')
def download_environment(name):
    """Download an environment."""
    from adare.cli.web import exec_download_environment
    args = SimpleNamespace(name=name)
    exec_with_error_printing(exec_download_environment, args)

@web.command()
@click.argument('ulid')
def publish(ulid):
    """Publish an experiment run to the web interface."""
    from adare.cli.web import exec_web_upload_experiment_run
    args = SimpleNamespace(ulid=ulid)
    exec_with_error_printing(exec_web_upload_experiment_run, args)

@web.command('publish-run')
@click.argument('ulid')
@click.option('--project', '-p', help='Name of the project')
def publish_run(ulid, project):
    """Publish an experiment run to the server with progress tracking."""
    from adare.cli.web import exec_web_publish_run
    args = SimpleNamespace(ulid=ulid, project=project)
    exec_with_error_printing(exec_web_publish_run, args)

@web.command('check-experiment')
@click.argument('ulid')
def check_experiment(ulid):
    """Check if an experiment exists on the server."""
    from adare.cli.web import exec_web_check_experiment
    args = SimpleNamespace(ulid=ulid)
    exec_with_error_printing(exec_web_check_experiment, args)

@web.command('check-run')
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


# ------------------------------
# Development commands
# ------------------------------
@cli.group()
def dev():
    """Development commands for testing and debugging."""
    pass

# ------------------------------
# MCP test commands (under dev)
# ------------------------------
@dev.group()
def mcp():
    """MCP server testing commands."""
    pass

@mcp.command(name='test-icon')
@click.option('--icon', required=True, type=click.Path(exists=True), help='Path to icon image file')
@click.option('--screenshot', required=True, type=click.Path(exists=True), help='Path to screenshot image file')
@click.option('--output', type=click.Path(), help='Path to save marked image with found locations')
@click.option('--host', default='localhost', help='MCP server host (default: localhost)')
@click.option('--port', type=int, default=13109, help='MCP server port (default: 13109)')
@click.option('--threshold', type=float, default=0.6, help='Match threshold (0.0-1.0, default: 0.6)')
@click.option('--mcplog', type=click.Path(), help='Path to save MCP server logs')
def test_icon(icon, screenshot, output, host, port, threshold, mcplog):
    """Test MCP server icon finding functionality.
    
    Automatically starts MCP server, finds an icon in a screenshot, 
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

@mcp.command(name='test-text')
@click.argument('text')
@click.option('--screenshot', required=True, type=click.Path(exists=True), help='Path to screenshot image file')
@click.option('--format', default='json', help='Output format: json or csv (default: json)')
@click.option('--host', default='localhost', help='MCP server host (default: localhost)')
@click.option('--port', type=int, default=13109, help='MCP server port (default: 13109)')
def test_text(text, screenshot, format, host, port):
    """Test MCP server text finding functionality.
    
    TEXT is the text string to search for in the screenshot.
    Automatically starts MCP server, finds text matches, 
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

@mcp.command(name='get-all-text')
@click.option('--screenshot', required=True, type=click.Path(exists=True), help='Path to screenshot image file')
@click.option('--format', default='json', help='Output format: json or csv (default: json)')
@click.option('--host', default='localhost', help='MCP server host (default: localhost)')
@click.option('--port', type=int, default=13109, help='MCP server port (default: 13109)')
def get_all_text(screenshot, format, host, port):
    """Get all detected text from screenshot using OCR.
    
    Automatically starts MCP server, runs OCR on the screenshot,
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
# WebSocket commands (under dev)
# ------------------------------
@dev.group()
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
def create_example(output_file):
    """Create an example action YAML file."""
    from adare.cli.ws import create_example_action_file
    from pathlib import Path
    create_example_action_file(Path(output_file))



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