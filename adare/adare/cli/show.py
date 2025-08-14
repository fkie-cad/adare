# internal imports
from adare.backend.basics import determine_projectdirectory
from adare.exceptions import NoProjectFoundError, ArgumentsError

# configure logging
import logging
log = logging.getLogger(__name__)


def exec_show_runs(arguments):
    from adare.frontend.terminal.run_list import print_run_list

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
    
    print_run_list(project, environment, experiment)


def exec_show_run(arguments):
    from adare.frontend.terminal.run import print_run
    print_run(arguments.ulid)


def exec_show_testfunctions(arguments):
    from adare.frontend.terminal.testfunction_list import print_testfunction_list
    print_testfunction_list(testfunction_file=arguments.file_name)


def exec_show_testfunction(arguments):
    from adare.frontend.terminal.testfunction import print_testfunction
    print_testfunction(arguments.dotnotation, None)


def exec_show_experiment(arguments):
    from adare.frontend.terminal.experiment import print_experiment
    print_experiment(name=arguments.name, ulid=arguments.ulid, dotnotation=arguments.dotnotation)


def exec_show_experiments(arguments):
    from adare.frontend.terminal.experiment_list import print_experiment_list
    print_experiment_list()


def exec_show_projects(arguments):
    from adare.frontend.terminal.project_list import print_project_list
    print_project_list()


def exec_show_environments(arguments):
    from adare.frontend.terminal.environment_list import print_environment_list
    print_environment_list()


def exec_show_environment(arguments):
    from adare.frontend.terminal.environment import print_environment
    print_environment(arguments.dotnotation)


