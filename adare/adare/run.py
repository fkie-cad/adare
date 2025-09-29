import sys
import time
import logging
from types import SimpleNamespace
import click
from trogon import tui


class AliasedGroup(click.Group):
    """A Click Group that supports command aliases."""
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.aliases = {}
    
    def add_alias(self, alias, command_name):
        """Add an alias for a command."""
        self.aliases[alias] = command_name
    
    def get_command(self, ctx, cmd_name):
        # First try the alias mapping
        if cmd_name in self.aliases:
            cmd_name = self.aliases[cmd_name]
        
        rv = click.Group.get_command(self, ctx, cmd_name)
        if rv is not None:
            return rv
            
        # If no exact match, try prefix matching
        matches = [x for x in self.list_commands(ctx)
                   if x.startswith(cmd_name)]
        if not matches:
            return None
        elif len(matches) == 1:
            return click.Group.get_command(self, ctx, matches[0])
        ctx.fail(f'Too many matches: {", ".join(sorted(matches))}')
    
    def list_commands(self, ctx):
        """Return both commands and aliases."""
        commands = super().list_commands(ctx)
        return sorted(commands + list(self.aliases.keys()))

# Internal imports
from adare.cli.project import (
    exec_create_project, exec_remove_project, exec_list_projects
)
from adare.cli.environment import (
    exec_environment_load, exec_environment_create, exec_environment_delete
)
from adare.cli.experiment import (
    exec_experiment_create, exec_experiment_load, exec_experiment_run, exec_experiment_test, exec_experiment_example, exec_experiment_clean, exec_experiment_add_env, exec_experiment_remove_env
)
from adare.cli.interactive import (
    exec_experiment_dev
)
from adare.cli.manage import exec_manage_reset_db, exec_manage_reset_vm, exec_manage_vm_runtime_refresh, exec_manage_init_db, exec_manage_db_status, exec_manage_repair_db, exec_manage_clean_install_db
from adare.cli.show import (
    exec_show_environment, exec_show_environments,
    exec_show_experiment, exec_show_runs, exec_show_run,
    exec_show_testfunctions, exec_show_testfunction, exec_show_experiments,
    exec_remove_run
)
from adare.cli.web import (
    exec_web_login, exec_web_logout, exec_web_status,
    exec_download_experiment, exec_download_testfunction, exec_download_environment,
    exec_web_sync, exec_web_upload_experiment_run
)
from adare.cli.testfunction import (
    exec_create_testfunction, exec_remove_testfunction, exec_load_testfunction, exec_list_testfunctions
)
from adare.cli.vm import (
    exec_vm_list, exec_vm_info, exec_vm_delete, exec_vm_delete_snapshot, exec_vm_clear_all, exec_vm_clear_by_environment, exec_vm_test,
    exec_vm_list_instances, exec_vm_instance_info, exec_vm_instance_cleanup, exec_vm_instance_usage, exec_vm_port_usage
)
from adare.cli.mcp import (
    exec_mcp_test_icon, exec_mcp_test_text, exec_mcp_get_all_text
)
from adare.cli.ws import (
    exec_ws_action, create_example_action_file
)
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
    args = SimpleNamespace()
    exec_with_error_printing(exec_manage_reset_db, args)

@manage.command(name='init-db')
def init_db():
    """Initialize the database system."""
    args = SimpleNamespace()
    exec_with_error_printing(exec_manage_init_db, args)

@manage.command(name='db-status')
def db_status():
    """Check database system status."""
    args = SimpleNamespace()
    exec_with_error_printing(exec_manage_db_status, args)

@manage.command(name='repair-db')
def repair_db():
    """Repair the database system."""
    args = SimpleNamespace()
    exec_with_error_printing(exec_manage_repair_db, args)

@manage.command(name='clean-install-db')
@click.option('--force', '-f', is_flag=True, help='Force clean installation without confirmation')
def clean_install_db(force):
    """Perform clean database installation (DANGER: deletes all data)."""
    args = SimpleNamespace(force=force)
    exec_with_error_printing(exec_manage_clean_install_db, args)

@manage.command(name='reset-vm')
@click.option('--force', '-f', is_flag=True, help='Force deletion of all VMs (required for confirmation)')
def reset_vm(force):
    """Reset all VMs in the system (use with caution)."""
    args = SimpleNamespace(force=force)
    exec_with_error_printing(exec_manage_reset_vm, args)

@manage.group(name='vm-runtime')
def vm_runtime():
    """VM runtime management for current project."""
    pass

@vm_runtime.command(name='refresh')
def vm_runtime_refresh():
    """Refresh VM runtime files in current project, ensuring they are up-to-date."""
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
    args = SimpleNamespace(name=name, description=description)
    exec_with_error_printing(exec_create_project, args)

@project.command()
@click.argument('name')
def remove(name):
    """Remove a project."""
    args = SimpleNamespace(name=name)
    exec_with_error_printing(exec_remove_project, args)

@project.command(name='list')
def list_projects():
    """List all projects."""
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
@click.argument('environment')
@click.option('--project', '-p', help='Name of the project')
@click.option('--force', '-f', is_flag=True, help='Force update of the environment')
def load(environment, project, force):
    """Load an environment.

    ENVIRONMENT can be:
    - Simple name: ubuntu24
    - Relative path: environments/ubuntu24.yml
    - Relative path: ./environments/ubuntu24.yaml
    """
    args = SimpleNamespace(environment=environment, project=project, force=force)
    exec_with_error_printing(exec_environment_load, args)

@environment.command()
@click.argument('name')
@click.option('--project', '-p', help='Name of the project')
@click.option('--with-vm', type=click.Path(exists=True), help='VM file path (OVA) to load automatically during environment creation')
def create(name, project, with_vm):
    """Create an environment.

    NAME can be:
    - Simple name: ubuntu24
    - Relative path: environments/ubuntu24
    """
    args = SimpleNamespace(name=name, project=project, with_vm=with_vm)
    exec_with_error_printing(exec_environment_create, args)

@environment.command()
@click.argument('ulid')
@click.option('--force', '-f', is_flag=True, help='Force deletion of the environment and any orphaned experiments')
def remove(ulid, force):
    """Delete an environment.
    
    WARNING: If this environment is the only one used by experiments,
    those experiments will become orphaned and be deleted when using --force.
    Without --force, deletion will fail to prevent data loss."""
    args = SimpleNamespace(ulid=ulid, force=force)
    exec_with_error_printing(exec_environment_delete, args)


@environment.command(name='list')
def list_environments():
    """List all environments in a project."""
    args = SimpleNamespace()
    exec_with_error_printing(exec_show_environments, args)

@environment.command()
@click.argument('environment_name')
def info(environment_name):
    """Show detailed information about a specific environment."""
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
experiment.add_alias('rm-env', 'remove-env')

@experiment.command()
@click.argument('experiment')
@click.option('--project', '-p', help='Name of the project')
def create(experiment, project):
    """Create a new experiment skeleton.

    EXPERIMENT can be:
    - Simple name: test_csv
    - Relative path: experiments/test_csv
    """
    args = SimpleNamespace(experiment=experiment, project=project)
    exec_with_error_printing(exec_experiment_create, args)

@experiment.command()
@click.argument('experiment')
@click.option('-e', '--environment', help='Name of the environment')
@click.option('--force', '-f', is_flag=True, help='Force update of the experiment')
@click.option('--project', '-p', help='Name of the project')
def load(experiment, environment, force, project):
    """Load an experiment.

    EXPERIMENT can be:
    - Simple name: test_csv
    - Relative path: experiments/test_csv
    - Relative path: ./experiments/test_csv
    """
    args = SimpleNamespace(
        experiment=experiment,
        environment=environment,
        force=force,
        project=project
    )
    exec_with_error_printing(exec_experiment_load, args)

@experiment.command()
@click.argument('experiment')
@click.option('-e', '--environment', help='Name of the environment (if not specified, runs on all environments in project)')
@click.option('--test', '-t', is_flag=True, help='Run the experiment in test mode - delete results afterwards and do not block changes')
@click.option('--debug-screenshots', is_flag=True, help='Save screenshots to experiment run directory for debugging')
@click.option('--preserve-snapshot', '-s', is_flag=True, help='Create experiment snapshot for preservation (default: only reset to base snapshot)')
@click.option('--no-runlog', is_flag=True, help='Do not save adare log to the run/logs directory')
@click.option('--vm-memory', type=int, help='VM RAM in MB (default: 4096 for Linux, 8192 for Windows)')
@click.option('--vm-cpus', type=int, help='VM CPU count (default: 4)')
@click.option('--project', '-p', help='Name of the project')
@click.pass_context
def run(ctx, experiment, environment, test, debug_screenshots, preserve_snapshot, no_runlog, vm_memory, vm_cpus, project):
    """Run an experiment in a given environment or all environments if none specified.

    EXPERIMENT can be:
    - Simple name: test_csv
    - Relative path: experiments/test_csv
    - Relative path: ./experiments/test_csv

    ENVIRONMENT can be:
    - Simple name: ubuntu24
    - Relative path: environments/ubuntu24.yml
    - Relative path: ./environments/ubuntu24.yaml
    """
    args = SimpleNamespace(
        experiment=experiment,
        environment=environment,
        test=test,
        debug_screenshots=debug_screenshots,
        preserve_snapshot=preserve_snapshot,
        runlog=not no_runlog,
        vm_memory=vm_memory,
        vm_cpus=vm_cpus,
        project=project,
        verbose=ctx.obj.verbose,
        very_verbose=ctx.obj.very_verbose
    )
    exec_with_error_printing(exec_experiment_run, args)

@experiment.command()
@click.argument('experiment')
@click.option('-e', '--environment', required=True, help='Name of the environment')
@click.option('--project', '-p', help='Name of the project')
def develop(experiment, environment, project):
    """Run an experiment in test mode."""
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
    args = SimpleNamespace(
        experiment=name,
        project=project
    )
    exec_with_error_printing(exec_experiment_example, args)

@experiment.command(name='list')
def list_experiments():
    """List all experiments in an environment."""
    args = SimpleNamespace()
    exec_with_error_printing(exec_show_experiments, args)

@experiment.command()
@click.argument('experiment')
@click.option('-e', '--environment', required=True, help='Name of the environment')
@click.option('--project', '-p', help='Name of the project')
@click.option('--port', type=int, default=8080, help='Port for the web interface (default: 8080)')
def dev(experiment, environment, project, port):
    """Start interactive development mode for an experiment.
    
    This would start a web-based interface for interactive development and testing
    of experiment playbooks, but is currently not implemented.
    """
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
    args = SimpleNamespace(
        experiment=experiment,
        project=project
    )
    exec_with_error_printing(exec_experiment_clean, args)


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
    args = SimpleNamespace(
        experiment_pattern=experiment_pattern,
        environments=list(environments),
        force=force,
        project=project
    )
    exec_with_error_printing(exec_experiment_remove_env, args)


# ------------------------------
# Testfunction commands
# ------------------------------
@cli.group(cls=AliasedGroup)
def testfunction():
    """Testfunction-related commands."""
    pass

@testfunction.command()
@click.argument('name')
@click.option('--project', '-p', help='Name of the project')
def create(name, project):
    """Create a new testfunction.

    NAME can be:
    - Simple name: my_test
    - Relative path: testfunctions/my_test
    """
    args = SimpleNamespace(name=name, project=project)
    exec_with_error_printing(exec_create_testfunction, args)

@testfunction.command()
@click.argument('name')
@click.option('--project', '-p', help='Name of the project')
def remove(name, project):
    """Remove a testfunction.

    NAME can be:
    - Simple name: my_test
    - Relative path: testfunctions/my_test
    """
    args = SimpleNamespace(name=name, project=project)
    exec_with_error_printing(exec_remove_testfunction, args)

@testfunction.command()
@click.argument('name')
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
    args = SimpleNamespace(name=name, force=force)
    exec_with_error_printing(exec_load_testfunction, args)

@testfunction.command(name='list')
@click.option('--set', help='Filter testfunctions by set (e.g., standard)')
def list_testfunctions(set):
    """List all testfunctions."""
    args = SimpleNamespace(set=set)
    exec_with_error_printing(exec_list_testfunctions, args)

@testfunction.command()
@click.option('--file-name', '-f', help='File name')
def show(file_name):
    """Show testfunctions with optional file filtering."""
    args = SimpleNamespace(file_name=file_name)
    exec_with_error_printing(exec_show_testfunctions, args)

@testfunction.command()
@click.argument('dotnotation')
def info(dotnotation):
    """Show detailed information about a specific testfunction."""
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
    args = SimpleNamespace()
    exec_with_error_printing(exec_vm_list, args)

@vm.command()
@click.argument('vm_id')
def info(vm_id):
    """Get detailed information about a VM."""
    args = SimpleNamespace(vm_id=vm_id)
    exec_with_error_printing(exec_vm_info, args)

@vm.command()
@click.argument('vm_id')
@click.option('--force', '-f', is_flag=True, help='Force deletion even if VM is in use')
def remove(vm_id, force):
    """Delete a specific VM."""
    args = SimpleNamespace(vm_id=vm_id, force=force)
    exec_with_error_printing(exec_vm_delete, args)

@vm.command(name='remove-snapshot')
@click.argument('vm_id')
@click.argument('snapshot_name')
def remove_snapshot(vm_id, snapshot_name):
    """Delete a single snapshot from a specific VM."""
    args = SimpleNamespace(vm_id=vm_id, snapshot_name=snapshot_name)
    exec_with_error_printing(exec_vm_delete_snapshot, args)

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
    args = SimpleNamespace(force=force)
    exec_with_error_printing(exec_vm_clear_all, args)

@clear.command(name='environment')
@click.argument('environment_ulid')
@click.option('--force', '-f', is_flag=True, help='Force deletion of environment VMs (required for confirmation)')
def clear_environment(environment_ulid, force):
    """Clear all VMs associated with a specific environment."""
    args = SimpleNamespace(environment_ulid=environment_ulid, force=force)
    exec_with_error_printing(exec_vm_clear_by_environment, args)

# Nested group for VM instance management
@vm.group()
def instance():
    """VM instance management commands."""
    pass

@instance.command(name='list')
def instance_list():
    """List all VM instances in the system."""
    args = SimpleNamespace()
    exec_with_error_printing(exec_vm_list_instances, args)

@instance.command()
@click.argument('instance_id')
def info(instance_id):
    """Get detailed information about a specific VM instance."""
    args = SimpleNamespace(instance_id=instance_id)
    exec_with_error_printing(exec_vm_instance_info, args)

@instance.command()
@click.option('--instance-id', help='Cleanup specific instance by ID')
@click.option('--age-days', type=int, help='Cleanup instances older than specified days')
@click.option('--experiment-id', help='Cleanup instances for specific experiment')
@click.option('--force', '-f', is_flag=True, help='Force cleanup even if instances are active')
def cleanup(instance_id, age_days, experiment_id, force):
    """Clean up VM instances based on criteria."""
    args = SimpleNamespace(
        instance_id=instance_id,
        age_days=age_days,
        experiment_id=experiment_id,
        force=force
    )
    exec_with_error_printing(exec_vm_instance_cleanup, args)

@instance.command()
def usage():
    """Show VM instance usage statistics."""
    args = SimpleNamespace()
    exec_with_error_printing(exec_vm_instance_usage, args)

@vm.command(name='port-usage')
def port_usage():
    """Show websocket port usage statistics."""
    args = SimpleNamespace()
    exec_with_error_printing(exec_vm_port_usage, args)

# Add aliases for vm commands
vm.add_alias('l', 'list')
vm.add_alias('rm', 'remove')
vm.add_alias('rm-snapshot', 'remove-snapshot')


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
    args = SimpleNamespace(filter=filter)
    exec_with_error_printing(exec_show_runs, args)

@run.command()
@click.argument('ulid', required=False)
def info(ulid):
    """Show detailed information about a run. Shows latest run if no ULID provided."""
    args = SimpleNamespace(ulid=ulid)
    exec_with_error_printing(exec_show_run, args)

@run.command()
@click.argument('ulid', required=True)
def remove(ulid):
    """Remove a single experiment run by its ULID."""
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
    args = SimpleNamespace()
    exec_with_error_printing(exec_web_login, args)

@web.command()
def logout():
    """Logout from the web interface."""
    args = SimpleNamespace()
    exec_with_error_printing(exec_web_logout, args)

@web.command()
def status():
    """Show the web login status."""
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
    args = SimpleNamespace(ulid=ulid)
    exec_with_error_printing(exec_download_experiment, args)

@download.command(name='testfunction')
@click.argument('name')
def download_testfunction(name):
    """Download a testfunction."""
    args = SimpleNamespace(name=name)
    exec_with_error_printing(exec_download_testfunction, args)

@download.command(name='environment')
@click.argument('name')
def download_environment(name):
    """Download an environment."""
    args = SimpleNamespace(name=name)
    exec_with_error_printing(exec_download_environment, args)

@web.command()
@click.argument('ulid')
def publish(ulid):
    """Publish an experiment run to the web interface."""
    args = SimpleNamespace(ulid=ulid)
    exec_with_error_printing(exec_web_upload_experiment_run, args)

@web.command()
@click.option('--project', '-p', help='Name of the project')
def sync(project):
    """Sync all environments and experiments with the web interface."""
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
