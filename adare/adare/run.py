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
# Experiment commands (extracted to cli/groups/experiment_commands.py)
# ------------------------------
from adare.cli.groups.experiment_commands import register as register_experiment_commands
register_experiment_commands(cli, AliasedGroup, exec_with_error_printing)


# ------------------------------
# Development mode commands (extracted to cli/groups/dev_commands.py)
# ------------------------------
from adare.cli.groups.dev_commands import register as register_dev_commands
register_dev_commands(cli, AliasedGroup, exec_with_error_printing)

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
# VM management commands (extracted to cli/groups/vm_commands.py)
# ------------------------------
from adare.cli.groups.vm_commands import register as register_vm_commands
register_vm_commands(cli, AliasedGroup, exec_with_error_printing)


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
# Web interface commands (extracted to cli/groups/web_commands.py)
# ------------------------------
from adare.cli.groups.web_commands import register as register_web_commands
register_web_commands(cli, AliasedGroup, exec_with_error_printing)


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
@click.option('--port', type=int, default=8000, help='Server port (default: 8000)')
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