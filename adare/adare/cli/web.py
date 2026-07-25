# internal imports
# configure logging
import logging

from adare.api import AdareAPI
from adare.cli.utils import get_project_path, handle_api_error
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


def exec_web_login(arguments):
    """Login to web app using AdareAPI."""
    api = AdareAPI()
    result = api.web.login()

    if not result.success:
        handle_api_error(result)


def exec_web_logout(arguments):
    """Logout from web app using AdareAPI."""
    api = AdareAPI()
    result = api.web.logout()

    if not result.success:
        handle_api_error(result)


def exec_web_status(arguments):
    """Get web login status using AdareAPI."""
    from adare.run import get_formatter_from_context
    from adare.web.login import is_logged_in

    api = AdareAPI()
    formatter, output_file, dual_output = get_formatter_from_context()

    result = api.web.get_status()

    if not result.success:
        handle_api_error(result)
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

    project_directory = get_project_path(arguments)
    environment_name = resolve_environment_path(arguments.name, project_directory)

    api = AdareAPI()
    result = api.web.download_environment(DownloadEnvironmentRequest(
        project_path=project_directory,
        environment_name=environment_name
    ))

    if not result.success:
        handle_api_error(result)


def exec_download_experiment(arguments):
    """Download experiment from web using AdareAPI."""
    project_directory = get_project_path(arguments)

    api = AdareAPI()
    result = api.web.download_experiment(DownloadExperimentRequest(
        project_path=project_directory,
        ulid=arguments.ulid
    ))

    if not result.success:
        handle_api_error(result)


def exec_download_testfunction(arguments):
    """Download testfunction from web using AdareAPI."""
    from adare.helperfunctions.path_resolution import resolve_testfunction_path

    project_directory = get_project_path(arguments)
    testfunction_name = resolve_testfunction_path(arguments.name, project_directory)

    api = AdareAPI()
    result = api.web.download_testfunction(DownloadTestfunctionRequest(
        project_path=project_directory,
        testfunction_name=testfunction_name,
        version=getattr(arguments, 'version', None)
    ))

    if not result.success:
        handle_api_error(result)


def exec_download_bundle(arguments):
    """Download an experiment bundle (experiment + all dependencies)."""
    project_directory = get_project_path(arguments)

    api = AdareAPI()
    result = api.web.download_bundle(DownloadBundleRequest(
        project_path=project_directory,
        ulid=arguments.ulid,
    ))

    if not result.success:
        handle_api_error(result)
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
        handle_api_error(result)


def exec_web_upload_experiment_run(arguments):
    """Upload experiment run to server using AdareAPI."""
    api = AdareAPI()
    result = api.web.upload_run(UploadRunRequest(ulid=arguments.ulid))

    if not result.success:
        handle_api_error(result)


def exec_web_publish_run(arguments):
    """Publish an experiment run to the server using AdareAPI."""
    project_directory = get_project_path(arguments)

    api = AdareAPI()
    result = api.web.publish_run(PublishRunRequest(
        project_path=project_directory,
        ulid=arguments.ulid
    ))

    if not result.success:
        handle_api_error(result)


def exec_web_check_experiment(arguments):
    """Check if an experiment exists on the server using AdareAPI."""
    from adare.run import get_formatter_from_context

    api = AdareAPI()
    formatter, output_file, dual_output = get_formatter_from_context()

    result = api.web.check_experiment(CheckExperimentRequest(ulid=arguments.ulid))

    if not result.success:
        handle_api_error(result)
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
        handle_api_error(result)
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

def _resolve_submit_action(api, entity_type, name):
    """Pre-check a create submission by name and decide the action to submit.

    Returns the action to submit ('create' or 'modify'), or ``None`` to abort.
    Prints guidance and prompts when the name collides:

    * ALREADY_PUBLISHED -> prompt to submit a modify PR instead (yes -> 'modify',
      no -> abort);
    * OPEN_DUPLICATE -> inform that the existing PR #M will be updated, proceed;
    * OK / pre-check unavailable -> proceed with 'create' (the server still guards
      the submission, so a failed pre-check must not block a legitimate submit).
    """
    precheck = api.web.precheck_submission(entity_type, name)
    if not precheck.success:
        # non-fatal: fall back to a plain create; the server remains authoritative
        log.warning(f'submission pre-check unavailable: {precheck.error.message}')
        return 'create'

    info = precheck.data or {}
    code = info.get('code')
    if code == 'ALREADY_PUBLISHED':
        print(info.get('message') or f"'{name}' is already published.")
        answer = input('submit a modify PR instead? [y/N]: ').strip().lower()
        if answer not in ('y', 'yes'):
            print('Aborted — nothing was submitted. Edit the published version with a modify PR.')
            return None
        return 'modify'
    if code == 'OPEN_DUPLICATE':
        pr_number = info.get('pr_number')
        print(info.get('message')
              or f"'{name}' is already proposed in pull request #{pr_number}; updating that PR.")
        return 'create'
    return 'create'


def _run_submit(submit_fn, request):
    """Invoke a submit facade with ``request`` and render the Result."""
    result = submit_fn(request)
    if not result.success:
        handle_api_error(result)
    else:
        print(result.data.message)
        print(f'PR URL: {result.data.pr_url}')


def exec_submit_experiment(arguments):
    """Submit an experiment as a PR to the shared repository."""
    project_directory = get_project_path(arguments)

    api = AdareAPI()
    action = _resolve_submit_action(api, 'experiment', arguments.name)
    if action is None:
        return
    _run_submit(api.web.submit_experiment, SubmitRequest(
        project_path=project_directory,
        name=arguments.name,
        action=action,
    ))


def exec_submit_testfunction(arguments):
    """Submit a testfunction as a PR to the shared repository."""
    project_directory = get_project_path(arguments)

    api = AdareAPI()
    action = _resolve_submit_action(api, 'testfunction', arguments.name)
    if action is None:
        return
    _run_submit(api.web.submit_testfunction, SubmitRequest(
        project_path=project_directory,
        name=arguments.name,
        action=action,
    ))


def exec_submit_environment(arguments):
    """Submit an environment as a PR to the shared repository."""
    project_directory = get_project_path(arguments)

    api = AdareAPI()
    action = _resolve_submit_action(api, 'environment', arguments.name)
    if action is None:
        return
    _run_submit(api.web.submit_environment, SubmitRequest(
        project_path=project_directory,
        name=arguments.name,
        action=action,
    ))
