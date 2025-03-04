import sys
import time
import logging
from types import SimpleNamespace
import click
from trogon import tui

# Internal imports
from adare.cli.project import (
    exec_create_project, exec_remove_project, exec_list_projects
)
from adare.cli.environment import (
    exec_environment_load, exec_environment_create, exec_environment_delete
)
from adare.cli.experiment import (
    exec_experiment_create, exec_experiment_load, exec_experiment_run, exec_experiment_test
)
from adare.cli.manage import exec_manage_reset
from adare.cli.gui import exec_gui
from adare.cli.showversion import exec_show_version
from adare.cli.show import (
    exec_show_projects, exec_show_environment, exec_show_environments,
    exec_show_experiment, exec_show_runs, exec_show_run,
    exec_show_testfunctions, exec_show_testfunction, exec_show_experiments
)
from adare.cli.web import (
    exec_web_login, exec_web_logout, exec_web_status,
    exec_download_experiment, exec_download_testfunction, exec_download_environment,
    exec_web_sync, exec_web_upload_experiment_run
)
from adare.cli.testfunction import (
    exec_create_testfunction, exec_remove_testfunction, exec_load_testfunction, exec_list_testfunctions
)
from adare.setup_logging import setup_logging
from adarelib.exceptions import LoggedException, LoggedErrorException


def exec_with_error_printing(func, args):
    try:
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
@click.group()
@click.option('--logfile', type=click.Path(), help='Path to logfile')
@click.option('--verbose', is_flag=True, help='Verbose output (loglevel=INFO)')
@click.option('--very-verbose', is_flag=True, help='Very verbose output (loglevel=DEBUG)')
@click.option('--log-level', help='Log level for logfile')
@click.version_option()  # Uses the package version if configured
def cli(logfile, verbose, very_verbose, log_level):
    """
    Adare - A tool to run experiments in virtual environments.
    """
    options = SimpleNamespace(
        logfile=logfile,
        verbose=verbose,
        very_verbose=very_verbose,
        log_level=log_level
    )
    setup_logging(options, sys.argv)


# ------------------------------
# Manage commands
# ------------------------------
@cli.group()
def manage():
    """Manage commands (wrapper for management-related operations)."""
    pass

@manage.command()
def reset():
    """Remove the database (use with caution)."""
    args = SimpleNamespace()
    exec_with_error_printing(exec_manage_reset, args)


# ------------------------------
# Project commands
# ------------------------------
@cli.group()
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


# ------------------------------
# Environment commands
# ------------------------------
@cli.group(name='environment')
def environment():
    """Environment-related commands."""
    pass

@environment.command()
@click.argument('environment')
@click.option('--project', '-p', help='Name of the project')
@click.option('--force', '-f', is_flag=True, help='Force update of the environment')
def load(environment, project, force):
    """Load an environment."""
    args = SimpleNamespace(environment=environment, project=project, force=force)
    exec_with_error_printing(exec_environment_load, args)

@environment.command()
@click.argument('name')
@click.option('--project', '-p', help='Name of the project')
def create(name, project):
    """Create an environment."""
    args = SimpleNamespace(name=name, project=project)
    exec_with_error_printing(exec_environment_create, args)

@environment.command()
@click.argument('ulid')
@click.option('--force', '-f', is_flag=True, help='Force deletion of the environment')
def delete(ulid, force):
    """Delete an environment."""
    args = SimpleNamespace(ulid=ulid, force=force)
    exec_with_error_printing(exec_environment_delete, args)


# ------------------------------
# Experiment commands
# ------------------------------
@cli.group(name='experiment')
def experiment():
    """Experiment-related commands."""
    pass

@experiment.command()
@click.argument('experiment')
@click.option('--project', '-p', help='Name of the project')
def create(experiment, project):
    """Create a new experiment skeleton."""
    args = SimpleNamespace(experiment=experiment, project=project)
    exec_with_error_printing(exec_experiment_create, args)

@experiment.command()
@click.argument('experiment')
@click.option('-e', '--environment', help='Name of the environment')
@click.option('--force', '-f', is_flag=True, help='Force update of the experiment')
@click.option('--project', '-p', help='Name of the project')
def load(experiment, environment, force, project):
    """Load an experiment."""
    args = SimpleNamespace(
        experiment=experiment,
        environment=environment,
        force=force,
        project=project
    )
    exec_with_error_printing(exec_experiment_load, args)

@experiment.command()
@click.argument('experiment')
@click.option('-e', '--environment', required=True, help='Name of the environment')
@click.option('--breakpoints', '-b', multiple=True, help='Breakpoints to stop the experiment at')
@click.option('--debug', '-d', is_flag=True, help='Run the experiment in debug mode')
@click.option('--project', '-p', help='Name of the project')
def run(experiment, environment, breakpoints, debug, project):
    """Run an experiment in a given environment."""
    args = SimpleNamespace(
        experiment=experiment,
        environment=environment,
        breakpoints=list(breakpoints),
        debug=debug,
        project=project
    )
    exec_with_error_printing(exec_experiment_run, args)

@experiment.command()
@click.argument('experiment')
@click.option('-e', '--environment', required=True, help='Name of the environment')
@click.option('--project', '-p', help='Name of the project')
def test(experiment, environment, project):
    """Run an experiment in test mode."""
    args = SimpleNamespace(
        experiment=experiment,
        environment=environment,
        project=project
    )
    exec_with_error_printing(exec_experiment_test, args)


# ------------------------------
# Testfunction commands
# ------------------------------
@cli.group()
def testfunction():
    """Testfunction-related commands."""
    pass

@testfunction.command()
@click.argument('name')
@click.option('--project', '-p', help='Name of the project')
def create(name, project):
    """Create a new testfunction."""
    args = SimpleNamespace(name=name, project=project)
    exec_with_error_printing(exec_create_testfunction, args)

@testfunction.command()
@click.argument('name')
@click.option('--project', '-p', help='Name of the project')
def remove(name, project):
    """Remove a testfunction."""
    args = SimpleNamespace(name=name, project=project)
    exec_with_error_printing(exec_remove_testfunction, args)

@testfunction.command()
@click.argument('name')
@click.option('--project', '-p', help='Name of the project')
def load(name, project):
    """Load a testfunction."""
    args = SimpleNamespace(name=name, project=project)
    exec_with_error_printing(exec_load_testfunction, args)

@testfunction.command(name='list')
@click.option('--project', '-p', help='Name of the project')
def list_testfunctions(project):
    """List all testfunctions."""
    args = SimpleNamespace(project=project)
    exec_with_error_printing(exec_list_testfunctions, args)


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
# Help commands
# ------------------------------
@cli.group()
def help():
    """Show help for special options."""
    pass


# ------------------------------
# Show information commands
# ------------------------------
@cli.group()
def show():
    """Show information about projects, environments, experiments, etc."""
    pass

@show.command(name='projects')
def show_projects():
    """Show list of projects."""
    args = SimpleNamespace()
    exec_with_error_printing(exec_show_projects, args)

@show.command(name='environments')
def show_environments():
    """Show all environments in a project."""
    args = SimpleNamespace()
    exec_with_error_printing(exec_show_environments, args)

@show.command(name='environment')
@click.option('-env', '--environment-name', help='Name of the environment')
@click.option('-proj', '--project-name', help='Name of the project')
@click.option('-ulid', '--ulid', help='ULID of the environment')
def show_environment(environment_name, project_name, ulid):
    """Show a specific environment."""
    args = SimpleNamespace(
        environment_name=environment_name,
        project_name=project_name,
        ulid=ulid
    )
    exec_with_error_printing(exec_show_environment, args)

@show.command(name='experiments')
def show_experiments():
    """Show all experiments in an environment."""
    args = SimpleNamespace()
    exec_with_error_printing(exec_show_experiments, args)

@show.command(name='experiment')
@click.option('-env', '--environment-name', help='Name of the environment')
@click.option('-proj', '--project-name', help='Name of the project')
@click.option('-exp', '--experiment-name', help='Name of the experiment')
@click.option('-ulid', '--ulid', help='ULID of the experiment')
def show_experiment(environment_name, project_name, experiment_name, ulid):
    """Show a specific experiment."""
    args = SimpleNamespace(
        environment_name=environment_name,
        project_name=project_name,
        experiment_name=experiment_name,
        ulid=ulid
    )
    exec_with_error_printing(exec_show_experiment, args)

@show.command(name='runs')
@click.option('-proj', '--project', help='Name of the project')
def show_runs(project):
    """Show all runs."""
    args = SimpleNamespace(project=project)
    exec_with_error_printing(exec_show_runs, args)

@show.command(name='run')
@click.argument('ulid')
def show_run(ulid):
    """Show a specific run."""
    args = SimpleNamespace(ulid=ulid)
    exec_with_error_printing(exec_show_run, args)

@show.command(name='testfunctions')
@click.option('-f', '--file-name', help='File name')
def show_testfunctions(file_name):
    """Show all testfunctions."""
    args = SimpleNamespace(file_name=file_name)
    exec_with_error_printing(exec_show_testfunctions, args)

@show.command(name='testfunction')
@click.argument('dotnotation')
def show_testfunction(dotnotation):
    """Show a specific testfunction."""
    args = SimpleNamespace(dotnotation=dotnotation)
    exec_with_error_printing(exec_show_testfunction, args)


def main():
    cli()
    runtime = (time.time() - START_TIME) / 60
    logging.getLogger(__name__).debug(f"--- Runtime {runtime} minutes ---")
    logging.shutdown()


if __name__ == '__main__':
    main()
