# internal imports
from adare.backend.basics import determine_projectdirectory
from adare.exceptions import NoProjectFoundError, ArgumentsError
from adare.helperfunctions.path_resolution import resolve_experiment_path, resolve_environment_path

# configure logging
import logging
log = logging.getLogger(__name__)


def exec_show_runs(arguments):
    """Show runs in the configured output format."""
    from adare.frontend.terminal.run_list import print_run_list
    from adare.run import get_formatter_from_context

    # Parse dot notation filter if provided
    project = None
    environment = None
    experiment = None

    if hasattr(arguments, 'filter') and arguments.filter:
        parts = arguments.filter.split('.')
        if len(parts) == 1:
            # Could be project, environment, or experiment - determine from current context
            if project_path := determine_projectdirectory(None):
                # We're in a project directory, so assume it's environment or experiment
                project = project_path.name
                # Check if it's an environment or experiment by context (for now assume environment)
                environment = parts[0]
            else:
                # Not in project directory, assume it's a project name
                project = parts[0]
        elif len(parts) == 2:
            # Could be project.environment or environment.experiment
            if project_path := determine_projectdirectory(None):
                # We're in a project directory, assume environment.experiment
                project = project_path.name
                environment, experiment = parts
            else:
                # Not in project directory, assume project.environment
                project, environment = parts
        elif len(parts) == 3:
            # Full dotnotation: project.environment.experiment
            project, environment, experiment = parts
        else:
            raise ArgumentsError(log, f'Invalid filter "{arguments.filter}". Expected format: [project][.environment][.experiment]')
    elif hasattr(arguments, 'project') and arguments.project:
        # Backward compatibility with old --project option
        project = arguments.project
    else:
        # No filter provided, use current project if available
        if project_path := determine_projectdirectory(None):
            project = project_path.name
        else:
            raise NoProjectFoundError(log, message='no project directory found and no filter provided')

    # Get formatter from CLI context
    formatter, output_file, dual_output = get_formatter_from_context()

    # Call enhanced frontend function with output format support
    print_run_list(
        project=project,
        environment=environment,
        experiment=experiment,
        formatter=formatter,
        output_file=output_file,
        dual_output=dual_output
    )


def exec_show_run(arguments):
    from adare.frontend.terminal.run import print_run
    from adare.database.api.frontend import DataRetrievalApi
    
    if arguments.ulid:
        print_run(arguments.ulid)
    else:
        # Get the latest run in the current project
        with DataRetrievalApi() as api:
            latest_run_data = api.get_latest_run_in_project()
            latest_run_ulid = latest_run_data['id'].iloc[0]
            print_run(latest_run_ulid)


def exec_show_testfunctions(arguments):
    """Show testfunctions in the configured output format."""
    from adare.frontend.terminal.testfunction_list import print_testfunction_list
    from adare.run import get_formatter_from_context

    # Get formatter from CLI context
    formatter, output_file, dual_output = get_formatter_from_context()

    # Call enhanced frontend function with output format support
    print_testfunction_list(
        testfunction_file=arguments.file_name,
        formatter=formatter,
        output_file=output_file,
        dual_output=dual_output
    )


def exec_show_testfunction(arguments):
    from adare.frontend.terminal.testfunction import print_testfunction
    print_testfunction(arguments.dotnotation, None)


def exec_show_experiment(arguments):
    from adare.frontend.terminal.experiment import print_experiment

    # Resolve experiment name if it's a path
    experiment_name = arguments.name
    if experiment_name and (project_directory := determine_projectdirectory(None)):
        try:
            experiment_name = resolve_experiment_path(arguments.name, project_directory)
        except Exception:
            # If path resolution fails, use the original name (might be a simple name or dotnotation)
            experiment_name = arguments.name

    print_experiment(name=experiment_name, ulid=arguments.ulid, dotnotation=arguments.dotnotation)


def exec_show_experiments(arguments):
    """Show experiments in the configured output format."""
    from adare.frontend.terminal.experiment_list import print_experiment_list
    from adare.run import get_formatter_from_context

    # Get formatter from CLI context
    formatter, output_file, dual_output = get_formatter_from_context()

    # Call enhanced frontend function with output format support
    print_experiment_list(
        formatter=formatter,
        output_file=output_file,
        dual_output=dual_output
    )


def exec_show_projects(arguments):
    """Show projects in the configured output format."""
    from adare.frontend.terminal.project_list import print_project_list
    from adare.run import get_formatter_from_context

    # Get formatter from CLI context
    formatter, output_file, dual_output = get_formatter_from_context()

    # Call enhanced frontend function with output format support
    print_project_list(
        formatter=formatter,
        output_file=output_file,
        dual_output=dual_output
    )


def exec_show_environments(arguments):
    """Show environments in the configured output format."""
    from adare.frontend.terminal.environment_list import print_environment_list
    from adare.run import get_formatter_from_context

    # Get formatter from CLI context
    formatter, output_file, dual_output = get_formatter_from_context()

    # Call enhanced frontend function with output format support
    print_environment_list(
        formatter=formatter,
        output_file=output_file,
        dual_output=dual_output
    )


def exec_remove_run(arguments):
    """Remove a single experiment run by its ULID."""
    from adare.database.api.experiment import ExperimentApi
    from adare.database.models.experiment import ExperimentRun
    from adare.console import print_success_message, console_print

    if not arguments.ulid:
        raise ArgumentsError(log, message='no run ULID provided',
                           possible_solutions=['use `adare run list` to find the ULID of the run to remove'])

    try:
        with ExperimentApi() as api:
            # Get the run first to check if it exists
            run = api._session.query(ExperimentRun).filter(ExperimentRun.id == arguments.ulid).first()
            if not run:
                raise ArgumentsError(log, message=f'run with ULID {arguments.ulid} not found')

            # Check if it's a fake run
            if run.fake:
                console_print(f"⚠️  Removing fake run {arguments.ulid}")
            else:
                console_print(f"⚠️  Removing real run {arguments.ulid}")

            # Delete the run
            api.delete_experiment_run(run)
            api._session.commit()

            print_success_message(
                title=f"Successfully removed run {arguments.ulid}",
                location="Database",
                next_steps=["Run 'adare run list' to see remaining runs"]
            )

    except Exception as e:
        log.error(f"Failed to remove run {arguments.ulid}: {str(e)}")
        raise


def exec_show_environment(arguments):
    from adare.frontend.terminal.environment import print_environment
    print_environment(arguments.dotnotation)


