# internal imports
from adare.api import AdareAPI
from adare.console import print_success_message, print_error_message
from adare.core.dto.show import RunListRequest, RunRemoveRequest

# configure logging
import logging
log = logging.getLogger(__name__)


def _handle_api_error(result) -> None:
    """
    Handle an API error result by printing formatted error message and exiting.

    Args:
        result: Result object with error information
    """
    error = result.error
    print_error_message(
        title=f'{error.code}: {error.message}',
        next_steps=error.solutions
    )
    exit(1)


def _parse_filter(arguments) -> tuple:
    """
    Parse dot notation filter from arguments.

    Returns:
        tuple: (project, environment, experiment)
    """
    from adare.backend.basics import determine_projectdirectory
    from adare.exceptions import ArgumentsError

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
        # Use silent=True to avoid warning message when outside project directory
        if project_path := determine_projectdirectory(None, silent=True):
            project = project_path.name
        else:
            # When outside of project, show all runs from all projects (like experiments/environments do)
            project = None

    return project, environment, experiment


def exec_show_runs(arguments):
    """Show runs in the configured output format."""
    from adare.run import get_formatter_from_context
    from adare.frontend.terminal.console import DefaultConsole
    from adare.frontend.terminal.run_list import RunListPanel
    from rich.layout import Layout
    import pandas as pd

    api = AdareAPI()
    formatter, output_file, dual_output = get_formatter_from_context()

    # Parse filter
    project, environment, experiment = _parse_filter(arguments)

    # Get runs from API
    result = api.show.list_runs(RunListRequest(
        project=project,
        environment=environment,
        experiment=experiment
    ))

    if not result.success:
        _handle_api_error(result)
        return

    runs = result.data

    if dual_output or formatter.format_type.value != 'rich':
        # Structured output (JSON/YAML)
        run_list = [run.to_dict() for run in runs]
        formatter.print_or_save({'runs': run_list}, output_file, dual_output)
    else:
        # Rich console output - convert to DataFrame for RunListPanel
        if runs:
            runs_data = [{
                'id': run.ulid,
                'experiment_dotnotation': run.experiment_name,
                'status': run.status,
                'result_status': run.result_status,
                'duration': run.duration_seconds,
                'fake': run.fake,
            } for run in runs]
            runs_df = pd.DataFrame(runs_data)
        else:
            runs_df = pd.DataFrame()

        console = DefaultConsole()
        layout = Layout(name="root")
        panel = RunListPanel(runs_df, project=project)
        layout.update(panel)
        console.print(layout)


def exec_show_run(arguments):
    """Get detailed information about a specific run."""
    from adare.frontend.terminal.run import print_run
    from adare.run import get_formatter_from_context

    formatter, output_file, dual_output = get_formatter_from_context()

    api = AdareAPI()

    if arguments.ulid:
        # Use the frontend function for rich display (it handles both data and display)
        print_run(arguments.ulid, formatter, output_file, dual_output)
    else:
        # Get the latest run in the current project via API
        result = api.show.get_run(latest_in_project=True)
        if not result.success:
            _handle_api_error(result)
            return
        # Use frontend function for display
        print_run(result.data.ulid, formatter, output_file, dual_output)


def exec_show_testfunctions(arguments):
    """Show testfunctions in the configured output format."""
    from adare.run import get_formatter_from_context
    from adare.frontend.terminal.console import DefaultConsole
    from adare.frontend.terminal.testfunction_list import TestfunctionTablePanel
    from rich.layout import Layout
    import pandas as pd

    api = AdareAPI()
    formatter, output_file, dual_output = get_formatter_from_context()

    # Get testfunctions from API
    file_name = arguments.file_name if hasattr(arguments, 'file_name') else None
    result = api.show.list_testfunctions(file_name=file_name)

    if not result.success:
        _handle_api_error(result)
        return

    testfunctions = result.data

    if dual_output or formatter.format_type.value != 'rich':
        # Structured output (JSON/YAML)
        tf_list = [tf.to_dict() for tf in testfunctions]
        formatter.print_or_save({'testfunctions': tf_list}, output_file, dual_output)
    else:
        # Rich console output - convert to DataFrame for TestfunctionTablePanel
        if testfunctions:
            tf_data = [{
                'ulid': tf.id,
                'display_name': tf.display_name,
                'name': tf.name,
                'parameters': tf.parameter_count,
                'file_name': tf.file_name,
                'description': tf.description,
            } for tf in testfunctions]
            tf_df = pd.DataFrame(tf_data)
        else:
            tf_df = pd.DataFrame()

        console = DefaultConsole()
        layout = Layout(name="root")
        panel = TestfunctionTablePanel(tf_df)
        layout.update(panel)
        console.print(layout)


def exec_show_testfunction(arguments):
    """Get detailed information about a specific testfunction."""
    from adare.frontend.terminal.testfunction import print_testfunction
    from adare.run import get_formatter_from_context

    formatter, output_file, dual_output = get_formatter_from_context()
    # Use the existing frontend function which handles the display
    print_testfunction(arguments.dotnotation, None, formatter, output_file, dual_output)


def exec_show_experiment(arguments):
    """Get detailed information about a specific experiment."""
    from adare.frontend.terminal.experiment import print_experiment
    from adare.run import get_formatter_from_context
    from adare.backend.basics import determine_projectdirectory
    from adare.helperfunctions.path_resolution import resolve_experiment_path

    formatter, output_file, dual_output = get_formatter_from_context()

    # Resolve experiment name if it's a path
    experiment_name = arguments.name
    if experiment_name and (project_directory := determine_projectdirectory(None)):
        try:
            experiment_name = resolve_experiment_path(arguments.name, project_directory)
        except Exception:
            # If path resolution fails, use the original name (might be a simple name or dotnotation)
            experiment_name = arguments.name

    # Use the existing frontend function which handles the display
    print_experiment(name=experiment_name, ulid=arguments.ulid, dotnotation=arguments.dotnotation,
                    formatter=formatter, output_file=output_file, dual_output=dual_output)


def exec_show_experiments(arguments):
    """Show experiments in the configured output format."""
    from adare.run import get_formatter_from_context
    from adare.frontend.terminal.console import DefaultConsole
    from adare.frontend.terminal.experiment_list import ExperimentTablePanel
    from rich.layout import Layout
    import pandas as pd

    api = AdareAPI()
    formatter, output_file, dual_output = get_formatter_from_context()

    # Get experiments from API
    result = api.show.list_experiments()

    if not result.success:
        _handle_api_error(result)
        return

    experiments = result.data

    if dual_output or formatter.format_type.value != 'rich':
        # Structured output (JSON/YAML)
        exp_list = [exp.to_dict() for exp in experiments]
        formatter.print_or_save({'experiments': exp_list}, output_file, dual_output)
    else:
        # Rich console output - convert to DataFrame for ExperimentTablePanel
        if experiments:
            exp_data = [{
                'display_name': exp.display_name,
                'ulid': exp.ulid,
                'environments_names': ', '.join(exp.environments),
                'description': exp.description,
                'published': str(exp.published),
                'in_request': str(exp.in_request),
            } for exp in experiments]
            exp_df = pd.DataFrame(exp_data)
        else:
            exp_df = pd.DataFrame()

        console = DefaultConsole()
        layout = Layout(name="root")
        panel = ExperimentTablePanel(exp_df)
        layout.update(panel)
        console.print(layout)


def exec_show_projects(arguments):
    """Show projects in the configured output format."""
    from adare.run import get_formatter_from_context
    from adare.frontend.terminal.console import DefaultConsole
    from adare.frontend.terminal.project_list import ProjectTablePanel
    from rich.layout import Layout
    import pandas as pd

    api = AdareAPI()
    formatter, output_file, dual_output = get_formatter_from_context()

    # Get projects from API
    result = api.show.list_projects()

    if not result.success:
        _handle_api_error(result)
        return

    projects = result.data

    if dual_output or formatter.format_type.value != 'rich':
        # Structured output (JSON/YAML)
        proj_list = [proj.to_dict() for proj in projects]
        formatter.print_or_save({'projects': proj_list}, output_file, dual_output)
    else:
        # Rich console output - convert to DataFrame for ProjectTablePanel
        if projects:
            proj_data = [{
                'name': proj.name,
                'description': proj.description,
                'created_at': proj.created_at,
            } for proj in projects]
            proj_df = pd.DataFrame(proj_data)
        else:
            proj_df = pd.DataFrame()

        console = DefaultConsole()
        layout = Layout(name="root")
        panel = ProjectTablePanel(proj_df)
        layout.update(panel)
        console.print(layout)


def exec_show_environments(arguments):
    """Show environments in the configured output format."""
    from adare.run import get_formatter_from_context
    from adare.frontend.terminal.console import DefaultConsole
    from adare.frontend.terminal.environment_list import EnvironmentTablePanel
    from rich.layout import Layout
    import pandas as pd

    api = AdareAPI()
    formatter, output_file, dual_output = get_formatter_from_context()

    # Get environments from API
    result = api.show.list_environments()

    if not result.success:
        _handle_api_error(result)
        return

    environments = result.data

    if dual_output or formatter.format_type.value != 'rich':
        # Structured output (JSON/YAML)
        env_list = [env.to_dict() for env in environments]
        formatter.print_or_save({'environments': env_list}, output_file, dual_output)
    else:
        # Rich console output - convert to DataFrame for EnvironmentTablePanel
        if environments:
            env_data = [{
                'id': env.ulid,
                'display_name': env.display_name,
                'name': env.name,
                'description': env.description,
                'osinfo': env.os_info,
                'vm_name': env.vm_name,
                'file': env.file,
                'published': str(env.published),
                'in_request': str(env.in_request),
            } for env in environments]
            env_df = pd.DataFrame(env_data)
        else:
            env_df = pd.DataFrame()

        console = DefaultConsole()
        layout = Layout(name="root")
        panel = EnvironmentTablePanel(env_df)
        layout.update(panel)
        console.print(layout)


def exec_remove_run(arguments):
    """Remove a single experiment run by its ULID."""
    from adare.console import console_print

    api = AdareAPI()

    result = api.show.remove_run(RunRemoveRequest(ulid=arguments.ulid))

    if result.success:
        run_type = "fake" if result.data.was_fake else "real"
        console_print(f"Removing {run_type} run {result.data.ulid}")
        print_success_message(
            title=f"Successfully removed run {result.data.ulid}",
            location="Database",
            next_steps=["Run 'adare show runs' to see remaining runs"]
        )
    else:
        _handle_api_error(result)


def exec_show_environment(arguments):
    """Get detailed information about a specific environment."""
    from adare.frontend.terminal.environment import print_environment
    from adare.run import get_formatter_from_context

    formatter, output_file, dual_output = get_formatter_from_context()
    # Use the existing frontend function which handles the display
    print_environment(arguments.environment_name, formatter, output_file, dual_output)
