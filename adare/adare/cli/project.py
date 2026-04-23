# external imports
# configure logging
import logging
from pathlib import Path

from adare.api import AdareAPI

# internal imports
from adare.backend.basics import determine_projectdirectory_for_removal
from adare.cli.utils import handle_api_error
from adare.console import print_success_message
from adare.core.dto.project import ProjectCreateRequest, ProjectRemoveRequest

log = logging.getLogger(__name__)


def exec_create_project(arguments):
    """
    Creates a new project using the AdareAPI.

    :param arguments: arguments parsed via input
    """
    api = AdareAPI()
    path = Path.cwd() / arguments.name
    description = arguments.description or ""

    result = api.project.create(ProjectCreateRequest(
        name=path.name,
        path=path,
        description=description
    ))

    if result.success:
        # CLI handles presentation
        print_success_message(
            title=f'Project "{result.data.name}" created successfully!',
            location=str(result.data.path),
            next_steps=result.data.next_steps,
            tip=result.data.tip
        )
    else:
        handle_api_error(result)


def exec_remove_project(arguments):
    """
    Removes a project using the AdareAPI.

    :param arguments: arguments parsed via input
    """
    path = determine_projectdirectory_for_removal(arguments.name)
    if not path:
        log.error("no valid project found in database")
        exit(1)

    api = AdareAPI()
    result = api.project.remove(ProjectRemoveRequest(path=path))

    if result.success:
        print_success_message(
            title=f'Project at "{path}" removed successfully!',
        )
    else:
        handle_api_error(result)


def exec_list_projects(arguments):
    """
    Lists all projects.

    Uses the existing print_project_list for backward compatibility
    with formatter support (Rich, JSON, YAML).

    :param arguments: arguments parsed via input
    """
    # Check if any projects exist using the API
    api = AdareAPI()
    result = api.project.list_all()

    if not result.success:
        handle_api_error(result)
        return

    if not result.data:
        # No projects found - use existing exception for consistent messaging
        from adare.backend.project.exceptions import NoProjectsFoundMessage
        raise NoProjectsFoundMessage(log, message='no projects found')

    # Use existing print_project_list for rich/json/yaml formatting
    from adare.frontend.terminal.project_list import print_project_list
    print_project_list()
