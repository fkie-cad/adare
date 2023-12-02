# internal imports
from adare.backend.basics import determine_projectdirectory
from adare.backend.project import Project
from adare.database.api.project import ProjectManagementApi

# configure logging
import logging
log = logging.getLogger(__name__)


def exec_create_project(arguments):
    """
    creates a new project

    :param arguments: arguments parsed via input
    """
    # check if project already exists
    with ProjectManagementApi() as api:
        project = api.get_project(arguments.name)
        if project:
            print(f"Project '{project.name}' already exists in database ({project.path})")
            print(f"Use 'adare show project' to show all projects")
            return
    Project(arguments.name, create=True)


def exec_remove_project(arguments):
    """
    removes a project

    :param arguments: arguments parsed via input
    """
    with ProjectManagementApi() as api:
        project = api.get_project(arguments.name)
        if not project:
            print(f"Project '{arguments.name}' is not found and therefore cannot be removed")
            return
    project_directory = determine_projectdirectory(arguments.name)
    project = Project(project_directory)
    project.remove()
