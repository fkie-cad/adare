from adare.backend.basics import determine_projectdirectory
from adare.exceptions import NoProjectFoundError
from adare.helperfunctions.path_resolution import resolve_environment_path, resolve_testfunction_path

# configure logging
import logging
log = logging.getLogger(__name__)


def exec_web_login(arguments):
    from adare.web.login import login
    login()


def exec_web_logout(arguments):
    from adare.web.login import logout
    logout()


def exec_web_status(arguments):
    """Get web login status."""
    from adare.web.login import is_logged_in
    from adare.database.api.usersession import UserSessionApi
    from adare.run import get_formatter_from_context

    formatter, output_file, dual_output = get_formatter_from_context()

    if dual_output or formatter.format_type.value != 'rich':
        # Structured output
        with UserSessionApi() as db:
            db.remove_expired_user_sessions()
            user_session = db.get_first_user_session()
            status_data = {
                'logged_in': bool(user_session),
                'username': user_session.username if user_session else None,
            }
        formatter.print_or_save(status_data, output_file, dual_output)
    else:
        # Rich console output (existing behavior)
        is_logged_in()


def exec_download_environment(arguments):
    from adare.backend.environment.commands import environment_download
    project_directory = determine_projectdirectory(arguments.project)
    if not project_directory:
        raise NoProjectFoundError(log, message='project directory not found')
    environment_name = resolve_environment_path(arguments.name, project_directory)
    environment_download(project_directory, environment_name)


def exec_download_experiment(arguments):
    from adare.backend.experiment.commands import experiment_download
    project_directory = determine_projectdirectory(arguments.project)
    if not project_directory:
        raise NoProjectFoundError(log, message='project directory not found')
    experiment_download(project_directory, arguments.ulid)


def exec_download_testfunction(arguments):
    from adare.backend.testfunction.commands import testfunction_download
    project_directory = determine_projectdirectory(arguments.project)
    if not project_directory:
        raise NoProjectFoundError(log, message='project directory not found')
    testfunction_name = resolve_testfunction_path(arguments.name, project_directory)
    testfunction_download(project_directory, testfunction_name)


def exec_web_sync(arguments):
    from adare.backend.sync import sync
    project_directory = determine_projectdirectory(arguments.project)
    sync(project_directory)


def exec_web_upload_experiment_run(arguments):
    from adare.webappaccess.upload import publish_experiment_run
    publish_experiment_run(arguments.ulid)
