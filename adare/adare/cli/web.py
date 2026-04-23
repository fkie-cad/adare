# internal imports
# configure logging
import logging

from adare.api import AdareAPI
from adare.console import print_error_message
from adare.core.dto.web import (
    CheckExperimentRequest,
    CheckRunRequest,
    DownloadBundleRequest,
    DownloadEnvironmentRequest,
    DownloadExperimentRequest,
    DownloadTestfunctionRequest,
    PublishRunRequest,
    SubmitRequest,
    SyncRequest,
    UploadRunRequest,
)

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


def _get_project_path(arguments):
    """
    Get project path from arguments or current directory.

    Args:
        arguments: CLI arguments

    Returns:
        Path to project directory
    """
    from adare.backend.basics import determine_projectdirectory
    from adare.exceptions import NoProjectFoundError

    project = getattr(arguments, 'project', None)
    project_directory = determine_projectdirectory(project)
    if not project_directory:
        raise NoProjectFoundError(log, message='project directory not found')
    return project_directory


def exec_web_login(arguments):
    """Login to web app using AdareAPI."""
    api = AdareAPI()
    result = api.web.login()

    if not result.success:
        _handle_api_error(result)


def exec_web_logout(arguments):
    """Logout from web app using AdareAPI."""
    api = AdareAPI()
    result = api.web.logout()

    if not result.success:
        _handle_api_error(result)


def exec_web_status(arguments):
    """Get web login status using AdareAPI."""
    from adare.run import get_formatter_from_context
    from adare.web.login import is_logged_in

    api = AdareAPI()
    formatter, output_file, dual_output = get_formatter_from_context()

    result = api.web.get_status()

    if not result.success:
        _handle_api_error(result)
        return

    status = result.data

    if dual_output or formatter.format_type.value != 'rich':
        # Structured output
        status_data = {
            'logged_in': status.logged_in,
            'username': status.username,
        }
        formatter.print_or_save(status_data, output_file, dual_output)
    else:
        # Rich console output (existing behavior)
        is_logged_in()


def exec_download_environment(arguments):
    """Download environment from web using AdareAPI."""
    from adare.helperfunctions.path_resolution import resolve_environment_path

    project_directory = _get_project_path(arguments)
    environment_name = resolve_environment_path(arguments.name, project_directory)

    api = AdareAPI()
    result = api.web.download_environment(DownloadEnvironmentRequest(
        project_path=project_directory,
        environment_name=environment_name
    ))

    if not result.success:
        _handle_api_error(result)


def exec_download_experiment(arguments):
    """Download experiment from web using AdareAPI."""
    project_directory = _get_project_path(arguments)

    api = AdareAPI()
    result = api.web.download_experiment(DownloadExperimentRequest(
        project_path=project_directory,
        ulid=arguments.ulid
    ))

    if not result.success:
        _handle_api_error(result)


def exec_download_testfunction(arguments):
    """Download testfunction from web using AdareAPI."""
    from adare.helperfunctions.path_resolution import resolve_testfunction_path

    project_directory = _get_project_path(arguments)
    testfunction_name = resolve_testfunction_path(arguments.name, project_directory)

    api = AdareAPI()
    result = api.web.download_testfunction(DownloadTestfunctionRequest(
        project_path=project_directory,
        testfunction_name=testfunction_name,
        version=getattr(arguments, 'version', None)
    ))

    if not result.success:
        _handle_api_error(result)


def exec_download_bundle(arguments):
    """Download an experiment bundle (experiment + all dependencies)."""
    project_directory = _get_project_path(arguments)
    include_disk_images = getattr(arguments, 'include_disk_images', False)

    api = AdareAPI()
    result = api.web.download_bundle(DownloadBundleRequest(
        project_path=project_directory,
        ulid=arguments.ulid,
        include_disk_images=include_disk_images
    ))

    if not result.success:
        _handle_api_error(result)
    else:
        print(result.data.message)


def exec_web_sync(arguments):
    """Sync project with web app using AdareAPI."""
    from adare.backend.basics import determine_projectdirectory

    project = getattr(arguments, 'project', None)
    project_directory = determine_projectdirectory(project)

    api = AdareAPI()
    result = api.web.sync(SyncRequest(project_path=project_directory))

    if not result.success:
        _handle_api_error(result)


def exec_web_upload_experiment_run(arguments):
    """Upload experiment run to server using AdareAPI."""
    api = AdareAPI()
    result = api.web.upload_run(UploadRunRequest(ulid=arguments.ulid))

    if not result.success:
        _handle_api_error(result)


def exec_web_publish_run(arguments):
    """Publish an experiment run to the server using AdareAPI."""
    project_directory = _get_project_path(arguments)

    api = AdareAPI()
    result = api.web.publish_run(PublishRunRequest(
        project_path=project_directory,
        ulid=arguments.ulid
    ))

    if not result.success:
        _handle_api_error(result)


def exec_web_check_experiment(arguments):
    """Check if an experiment exists on the server using AdareAPI."""
    from adare.run import get_formatter_from_context

    api = AdareAPI()
    formatter, output_file, dual_output = get_formatter_from_context()

    result = api.web.check_experiment(CheckExperimentRequest(ulid=arguments.ulid))

    if not result.success:
        _handle_api_error(result)
        return

    check_result = result.data
    result_data = {
        'experiment_ulid': check_result.experiment_ulid,
        'exists': check_result.exists,
        'status': check_result.status
    }

    if dual_output or formatter.format_type.value != 'rich':
        formatter.print_or_save(result_data, output_file, dual_output)
    else:
        if check_result.exists:
            print(f'Experiment {check_result.experiment_ulid} exists on server and is published.')
        else:
            print(f'Experiment {check_result.experiment_ulid} not found on server.')


def exec_web_check_run(arguments):
    """Check if an experiment run exists on the server using AdareAPI."""
    from adare.run import get_formatter_from_context

    api = AdareAPI()
    formatter, output_file, dual_output = get_formatter_from_context()

    result = api.web.check_run(CheckRunRequest(ulid=arguments.ulid))

    if not result.success:
        _handle_api_error(result)
        return

    check_result = result.data
    result_data = {
        'run_ulid': check_result.run_ulid,
        'exists': check_result.exists,
        'status': check_result.status
    }

    if dual_output or formatter.format_type.value != 'rich':
        formatter.print_or_save(result_data, output_file, dual_output)
    else:
        if check_result.exists:
            print(f'Experiment run {check_result.run_ulid} exists on server.')
        else:
            print(f'Experiment run {check_result.run_ulid} not found on server.')


# =========================================================================
# Submit Operations
# =========================================================================

def exec_submit_experiment(arguments):
    """Submit an experiment as a PR to the shared repository."""
    project_directory = _get_project_path(arguments)

    api = AdareAPI()
    result = api.web.submit_experiment(SubmitRequest(
        project_path=project_directory,
        name=arguments.name
    ))

    if not result.success:
        _handle_api_error(result)
    else:
        print(result.data.message)
        print(f'PR URL: {result.data.pr_url}')


def exec_submit_testfunction(arguments):
    """Submit a testfunction as a PR to the shared repository."""
    project_directory = _get_project_path(arguments)

    api = AdareAPI()
    result = api.web.submit_testfunction(SubmitRequest(
        project_path=project_directory,
        name=arguments.name
    ))

    if not result.success:
        _handle_api_error(result)
    else:
        print(result.data.message)
        print(f'PR URL: {result.data.pr_url}')


def exec_submit_environment(arguments):
    """Submit an environment as a PR to the shared repository."""
    project_directory = _get_project_path(arguments)

    api = AdareAPI()
    result = api.web.submit_environment(SubmitRequest(
        project_path=project_directory,
        name=arguments.name
    ))

    if not result.success:
        _handle_api_error(result)
    else:
        print(result.data.message)
        print(f'PR URL: {result.data.pr_url}')
