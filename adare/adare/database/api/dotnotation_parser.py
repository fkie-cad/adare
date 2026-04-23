# internal imports
# configure logging
import logging

from adare.backend.basics import determine_projectdirectory
from adare.exceptions import ArgumentsError, NoProjectFoundError

log = logging.getLogger(__name__)


class DotNotationParser:
    """Unified parser for dot notation across different entity types."""

    def parse_experiment_dotnotation(self, dotnotation: str) -> dict:
        """
        Parse experiment dotnotation into components.

        Supported formats:
        - 2-part: project.experiment
        - 3-part: project.environment.experiment

        Returns:
            dict with keys: project_name, environment_name (optional), experiment_name
        """
        dotparts = dotnotation.split('.')

        if len(dotparts) == 2:
            # project.experiment format (most common)
            project_name, experiment_name = dotparts
            return {
                'project_name': project_name,
                'experiment_name': experiment_name,
                'environment_name': None
            }
        if len(dotparts) == 3:
            # project.environment.experiment format
            project_name, environment_name, experiment_name = dotparts
            return {
                'project_name': project_name,
                'environment_name': environment_name,
                'experiment_name': experiment_name
            }
        if len(dotparts) == 1:
            # experiment only - use current project
            experiment_name = dotparts[0]
            current_project_name = self._get_current_project_name()
            return {
                'project_name': current_project_name,
                'experiment_name': experiment_name,
                'environment_name': None
            }
        raise ArgumentsError(log,
            f'Invalid experiment dotnotation "{dotnotation}". '
            'Expected format: experiment, project.experiment, or project.environment.experiment')

    def parse_environment_dotnotation(self, dotnotation: str) -> dict:
        """
        Parse environment dotnotation into components.

        Supported formats:
        - 1-part: environment (in current project)
        - 2-part: project.environment

        Returns:
            dict with keys: project_name, environment_name
        """
        dotparts = dotnotation.split('.')

        if len(dotparts) == 1:
            # environment only - use current project
            environment_name = dotparts[0]
            current_project_name = self._get_current_project_name()
            return {
                'project_name': current_project_name,
                'environment_name': environment_name
            }
        if len(dotparts) == 2:
            # project.environment format
            project_name, environment_name = dotparts
            return {
                'project_name': project_name,
                'environment_name': environment_name
            }
        raise ArgumentsError(log,
            f'Invalid environment dotnotation "{dotnotation}". '
            'Expected format: environment or project.environment')

    def parse_testfunction_dotnotation(self, dotnotation: str) -> dict:
        """
        Parse testfunction dotnotation into components.

        Supported formats:
        - 2-part: file.function (current project)
        - 3-part: project.file.function (cross-project access)

        Returns:
            dict with keys: project_name (optional), file_name, function_name
        """
        dotparts = dotnotation.split('.')

        if len(dotparts) == 2:
            # file.function format (current project)
            file_name, function_name = dotparts
            return {
                'project_name': None,  # Use current project context
                'file_name': file_name,
                'function_name': function_name
            }
        if len(dotparts) == 3:
            # project.file.function format (cross-project)
            project_name, file_name, function_name = dotparts
            return {
                'project_name': project_name,
                'file_name': file_name,
                'function_name': function_name
            }
        raise ArgumentsError(log,
            f'Invalid testfunction dotnotation "{dotnotation}". '
            'Expected format: file.function or project.file.function')

    def _get_current_project_name(self) -> str:
        """Get current project name or raise error if not in project directory."""
        if project_path := determine_projectdirectory(None, silent=True):
            return project_path.name
        raise NoProjectFoundError(log,
            message='No project directory found. Either provide full dotnotation or run from a project directory')
