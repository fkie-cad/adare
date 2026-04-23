"""Base mixin with initialization, context management, validation, and display helpers."""

import logging
from pathlib import Path

from adare.database.api.base import GlobalDatabaseApi, ProjectDatabaseApi
from adare.database.models.global_models import (
    Environment,
    Project,
)
from adare.database.models.project_models import Event, Experiment
from adare.exceptions import (
    EnvironmentNotFoundError,
    ExperimentNotFoundError,
    ProjectNotFoundError,
)

log = logging.getLogger(__name__)


class DataRetrievalBase:
    """
    Base mixin providing initialization, context management, validation checks,
    and display helper methods for the DataRetrievalApi.

    This mixin provides access to:
    - Global models: Project, Environment, VM, TestFunction (from global database)
    - Project models: Experiment, ExperimentRun (from project-specific database)
    """

    def __init__(self, project_path: Path = None, require_project: bool = True):
        """
        Initialize DataRetrievalApi with project context.

        Args:
            project_path: Path to project directory. If None, will auto-detect from current directory.
            require_project: If True, raises error when no project found. If False, allows global-only operations.

        Raises:
            ProjectNotFoundError: If no project can be determined and require_project=True
        """
        if project_path is None:
            from adare.backend.basics import determine_projectdirectory
            project_path = determine_projectdirectory(None, silent=True)
            if project_path is None and require_project:
                raise ProjectNotFoundError(log, "No current project found. Please run this command from within a project directory.")

        self.project_path = project_path
        self.require_project = require_project
        self._global_api = None
        self._project_api = None

    def __enter__(self):
        """Context manager entry - start both database sessions."""
        try:
            self._global_api = GlobalDatabaseApi()
            self._project_api = ProjectDatabaseApi(self.project_path)
            self._global_api.__enter__()
            self._project_api.__enter__()
            return self
        except Exception as e:
            # Clean up if initialization fails
            self.__exit__(type(e), e, e.__traceback__)
            raise

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit - handle cleanup of both database sessions."""
        project_exception = None
        global_exception = None

        # Close project database first
        if self._project_api:
            try:
                self._project_api.__exit__(exc_type, exc_val, exc_tb)
            except Exception as e:
                project_exception = e
                log.error(f"Error closing project database: {e}")
            finally:
                self._project_api = None

        # Close global database second
        if self._global_api:
            try:
                self._global_api.__exit__(exc_type, exc_val, exc_tb)
            except Exception as e:
                global_exception = e
                log.error(f"Error closing global database: {e}")
            finally:
                self._global_api = None

        # If we had exceptions during cleanup, log them but don't mask the original exception
        if project_exception or global_exception:
            if exc_type is None:  # No original exception, raise cleanup exception
                raise project_exception or global_exception

    def _check_project_exists(self, project_name: str):
        if not self._global_api._session.query(Project).filter_by(name=project_name).count():
            raise ProjectNotFoundError(log, f'Project "{project_name}" not found')

    def _check_environment_exists_by_name(self, environment_name: str):
        if not self._global_api._session.query(Environment).filter_by(name=environment_name).count():
            raise EnvironmentNotFoundError(log, f'Environment "{environment_name}" not found')

    def _check_environment_exists_by_ulid(self, environment_ulid: str):
        if not self._global_api._session.query(Environment).filter_by(id=environment_ulid).count():
            raise EnvironmentNotFoundError(log, f'Environment with ulid "{environment_ulid}" not found')

    def _check_experiment_exists_by_projenvexp(self, project_name: str, environment_name: str, experiment_name: str):
        if not self._project_api._session.query(Experiment).filter(
                Experiment.name == experiment_name).count():
            raise ExperimentNotFoundError(log, f'Experiment "{experiment_name}" not found in project "{project_name}" and environment "{environment_name}"')

    def _check_experiment_exists_by_ulid(self, experiment_ulid: str):
        if not self._project_api._session.query(Experiment).filter_by(id=experiment_ulid).count():
            raise ExperimentNotFoundError(log, f'Experiment with ulid "{experiment_ulid}" not found')

    def _compute_display_level(self, event):
        """
        Compute display level for an event based on parent relationships.
        Root level events have display_level = 0, each nested level adds 1.
        """
        if not event.parent_event_id:
            return 0  # Root level

        # Find parent event and recursively compute depth
        parent = self._project_api._session.query(Event).filter_by(id=event.parent_event_id).first()
        if parent:
            return self._compute_display_level(parent) + 1
        # If parent not found, assume next level
        return 1

    def _get_smart_display_name(self, obj, obj_type: str, current_project_name: str = None):
        """
        Get context-aware display name for objects (environments, experiments, testfunctions).

        Args:
            obj: The database object
            obj_type: Type of object ('environment', 'experiment', 'testfunction')
            current_project_name: Current project context (detected if None)

        Returns:
            str: Display name - either just the name part or full dotnotation
        """
        if current_project_name is None:
            from adare.backend.basics import determine_projectdirectory
            if project_path := determine_projectdirectory(None, silent=True):
                current_project_name = project_path.name

        # Get the full dotnotation (create it for experiments if needed)
        if obj_type == 'experiment':
            # For experiments, create dotnotation based on current project
            full_dotnotation = f'{current_project_name}.{obj.name}' if current_project_name else obj.name
        elif obj_type == 'environment':
            # Environments are now global, use name only
            full_dotnotation = obj.name
        else:
            full_dotnotation = obj.dotnotation

        if obj_type == 'environment':
            # Environments are now global, just return the name
            return obj.name

        if obj_type == 'experiment':
            # For experiments, check if we're in the same project context
            if current_project_name and full_dotnotation.startswith(f'{current_project_name}.'):
                return obj.name  # Return just the experiment name
            return full_dotnotation  # Return full project.name format

        if obj_type == 'testfunction':
            # For testfunctions, dotnotation is file.function_name
            # We could add more sophisticated logic here if needed
            return full_dotnotation

        # Fallback to full dotnotation for unknown types
        return full_dotnotation
