# configure logging
import logging

from adare.api import AdareAPI
from adare.cli.utils import get_project_path, handle_api_error
from adare.console import print_success_message
from adare.core.dto.environment import EnvironmentCreateRequest, EnvironmentLoadRequest
from adare.helperfunctions.path_resolution import resolve_environment_path

log = logging.getLogger(__name__)


def exec_environment_load(arguments):
    """
    Load an environment from YAML file using the AdareAPI.
    """
    api = AdareAPI()
    no_copy = getattr(arguments, 'no_copy', False)

    result = api.environment.load(EnvironmentLoadRequest(
        environment=arguments.environment,
        force=arguments.force,
        no_copy=no_copy
    ))

    if result.success:
        print_success_message(
            title=f'Environment "{result.data.name}" loaded successfully!',
            location=str(result.data.file_path) if result.data.file_path else None,
            next_steps=result.data.next_steps,
            tip=result.data.tip
        )
    else:
        handle_api_error(result)


def exec_environment_create(arguments):
    """
    Create a new environment template file using the AdareAPI.
    """
    from pathlib import Path

    project_directory = get_project_path(arguments)

    # Resolve environment name from path
    environment_name = resolve_environment_path(arguments.name, project_directory)

    # Handle --with-vm option
    vm_path = None
    if hasattr(arguments, 'with_vm') and arguments.with_vm:
        vm_path = Path(arguments.with_vm)

    api = AdareAPI()
    result = api.environment.create(EnvironmentCreateRequest(
        project_path=project_directory,
        name=environment_name,
        vm_path=vm_path
    ))

    if result.success:
        print_success_message(
            title=f'Environment "{result.data.name}" created successfully!',
            location=str(result.data.file_path) if result.data.file_path else None,
            next_steps=result.data.next_steps,
            tip=result.data.tip
        )
    else:
        handle_api_error(result)


def exec_environment_verify(arguments):
    """
    Verify an environment by running the built-in verify_vm experiment foreground.
    """
    import asyncio
    import sys

    from adare.backend.basics import determine_projectdirectory
    from adare.backend.experiment.run import experiment_run

    env_name = arguments.name
    api = AdareAPI()

    project_directory = determine_projectdirectory(arguments.project)
    if not project_directory:
        fallback = api.experiment.get_or_create_verify_scratch()
        if not fallback.success:
            handle_api_error(fallback)
            return
        project_directory = fallback.data
        log.info(f"No project specified — verify artifacts will be saved to {project_directory}")

    setup_result = api.experiment.ensure_verify_setup(project_directory, env_name)
    if not setup_result.success:
        handle_api_error(setup_result)
        return

    experiment_name = setup_result.data

    was_interrupted, was_successful = asyncio.run(experiment_run(
        project_directory,
        experiment_name,
        env_name,
        test=False,
        runlog=True,
    ))

    if not was_successful:
        from adare.console import print_error_message
        print_error_message(
            title=f'Environment "{env_name}" verification failed',
            next_steps=[
                f'Inspect run artifacts under {project_directory}/.adare/runs/',
                f'Re-run verification with: adare env verify {env_name}',
            ],
        )
        sys.exit(1)

    print_success_message(
        title=f'Environment "{env_name}" verified',
        next_steps=[
            f'Inspect run artifacts under {project_directory}/.adare/runs/',
            f'Re-run verification anytime with: adare env verify {env_name}',
        ],
        tip='The verify_vm experiment is now attached and can be run again as needed.',
    )


def exec_environment_delete(arguments):
    """
    Delete an environment using the AdareAPI.
    """
    api = AdareAPI()
    result = api.environment.delete(
        identifier=arguments.identifier,
        force=arguments.force
    )

    if result.success:
        print_success_message(
            title=f'Environment "{arguments.identifier}" deleted successfully!',
        )
    else:
        handle_api_error(result)
