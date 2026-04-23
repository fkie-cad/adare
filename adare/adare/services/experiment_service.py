"""
Experiment Service - Business logic for experiment operations.

This service handles experiment-related operations and returns Result[T] objects
that can be consumed by any frontend (CLI, Web UI, REST API).

Note: Some complex operations (like experiment_run with async and interactive flows)
are kept in the CLI/backend for now due to their complexity. This service focuses
on simpler CRUD operations that benefit from the API pattern.
"""
import logging
from pathlib import Path

from sqlalchemy.exc import SQLAlchemyError

from adare.backend.experiment import database as experiment_database
from adare.backend.experiment.commands import (
    experiment_add_environments as backend_experiment_add_environments,
)
from adare.backend.experiment.commands import (
    experiment_clean as backend_experiment_clean,
)
from adare.backend.experiment.commands import (
    experiment_clone as backend_experiment_clone,
)
from adare.backend.experiment.commands import (
    experiment_create as backend_experiment_create,
)
from adare.backend.experiment.commands import (
    experiment_example as backend_experiment_example,
)
from adare.backend.experiment.commands import (
    experiment_load as backend_experiment_load,
)
from adare.backend.experiment.commands import (
    experiment_remove as backend_experiment_remove,
)
from adare.backend.experiment.commands import (
    experiment_remove_environments as backend_experiment_remove_environments,
)
from adare.backend.experiment.commands import (
    experiment_validate as backend_experiment_validate,
)
from adare.backend.experiment.directory import ExperimentDirectory
from adare.backend.experiment.exceptions import (
    ExperimentAlreadyExistsError,
    ExperimentDirectoryAlreadyExistsError,
    ExperimentDirectoryDoesNotExistError,
    ExperimentIntegrityError,
    ExperimentNotChanged,
)
from adare.backend.experiment.run import experiment_test as backend_experiment_test
from adare.core.dto.experiment import (
    ExperimentCleanResult,
    ExperimentCloneRequest,
    ExperimentCreateRequest,
    ExperimentEnvModifyRequest,
    ExperimentEnvModifyResult,
    ExperimentInfo,
    ExperimentListItem,
    ExperimentLoadRequest,
    ExperimentRemoveRequest,
    ExperimentRemoveResult,
    ExperimentValidateRequest,
    ExperimentValidateResult,
)
from adare.core.result import Result
from adare.database.api.experiment import ExperimentApi

log = logging.getLogger(__name__)


class ExperimentService:
    """
    Service for experiment management operations.

    All methods return Result[T] objects for consistent error handling
    across different frontends.

    Note: Complex async operations like experiment_run are not included here
    as they require specialized handling (flow console, interrupts, etc.).
    """

    # =========================================================================
    # Experiment Lifecycle
    # =========================================================================

    def create(self, request: ExperimentCreateRequest) -> Result[ExperimentInfo]:
        """
        Create a new experiment.

        Args:
            request: ExperimentCreateRequest with project path and name

        Returns:
            Result[ExperimentInfo] with created experiment info on success,
            or error information on failure.
        """
        try:
            # Call backend create (this prints its own success message currently)
            backend_experiment_create(request.project_path, request.name)

            # Build experiment info
            experiment_dir = ExperimentDirectory(request.project_path, request.name)

            next_steps = [
                f'Edit {experiment_dir.playbookfile.name} to define GUI actions and tests',
                f'Edit {experiment_dir.metadatafile.name} to add experiment details',
                f'Load the experiment with: adare experiment load {request.name}',
                f'Run the experiment with: adare experiment run {request.name} -e <environment>'
            ]

            return Result.ok(ExperimentInfo(
                id='',  # Not in database yet
                name=request.name,
                description='',
                file_path=experiment_dir.path,
                sha256='',
                environment_names=[],
                run_count=0,
                productive_run_count=0,
                is_loaded=False,
                next_steps=next_steps,
                tip='See documentation for tutorial on how to write experiments',
            ))

        except ExperimentDirectoryAlreadyExistsError as e:
            return Result.from_exception(e)

    def load(self, request: ExperimentLoadRequest) -> Result[ExperimentInfo]:
        """
        Load an experiment from its files into the database.

        Args:
            request: ExperimentLoadRequest with project path, name, and options

        Returns:
            Result[ExperimentInfo] with loaded experiment info on success,
            or error information on failure.
        """
        try:
            backend_experiment_load(
                request.project_path,
                request.name,
                force=request.force,
                silent=request.silent
            )

            # Get experiment info from database
            return self.get_by_name(request.project_path, request.name)

        except ExperimentDirectoryDoesNotExistError as e:
            return Result.from_exception(e)
        except ExperimentIntegrityError as e:
            return Result.from_exception(e)
        except ExperimentAlreadyExistsError as e:
            return Result.from_exception(e)
        except ExperimentNotChanged:
            # Not really an error - experiment unchanged
            return self.get_by_name(request.project_path, request.name)

    def clone(self, request: ExperimentCloneRequest) -> Result[ExperimentInfo]:
        """
        Clone an existing experiment.

        Args:
            request: ExperimentCloneRequest with source and target names

        Returns:
            Result[ExperimentInfo] with cloned experiment info on success,
            or error information on failure.
        """
        try:
            backend_experiment_clone(
                request.project_path,
                request.source_experiment,
                request.target_experiment,
                environments=request.environments
            )

            # Build cloned experiment info
            experiment_dir = ExperimentDirectory(request.project_path, request.target_experiment)

            next_steps = [
                'Edit the cloned playbook to create your variation',
                f'Load the experiment with: adare experiment load {request.target_experiment}',
                f'Run the experiment with: adare experiment run {request.target_experiment} -e <environment>'
            ]

            return Result.ok(ExperimentInfo(
                id='',  # Not in database yet
                name=request.target_experiment,
                description=f'Cloned from {request.source_experiment}',
                file_path=experiment_dir.path,
                sha256='',
                environment_names=request.environments or [],
                run_count=0,
                productive_run_count=0,
                is_loaded=False,
                next_steps=next_steps,
                tip='The cloned experiment has its own independent playbook',
            ))

        except ExperimentDirectoryDoesNotExistError as e:
            return Result.from_exception(e)
        except ExperimentDirectoryAlreadyExistsError as e:
            return Result.from_exception(e)

    def remove(self, request: ExperimentRemoveRequest) -> Result[ExperimentRemoveResult]:
        """
        Remove an experiment.

        Args:
            request: ExperimentRemoveRequest with project path and name

        Returns:
            Result[ExperimentRemoveResult] on success,
            or error information on failure.
        """
        try:
            backend_experiment_remove(
                request.project_path,
                request.name,
                force=request.force,
                keep_files=request.keep_files
            )

            return Result.ok(ExperimentRemoveResult(
                removed_from_db=True,
                files_deleted=not request.keep_files,
                experiment_name=request.name,
            ))

        except ExperimentDirectoryDoesNotExistError as e:
            return Result.from_exception(e)

    def clean(self, project_path: Path, name: str) -> Result[ExperimentCleanResult]:
        """
        Clean fake/test runs from an experiment.

        Args:
            project_path: Path to the project
            name: Experiment name

        Returns:
            Result[ExperimentCleanResult] with number of deleted runs.
        """
        try:
            # The backend function prints its own output and returns the count
            deleted_count = backend_experiment_clean(project_path, name)

            return Result.ok(ExperimentCleanResult(
                deleted_count=deleted_count if deleted_count else 0,
                experiment_name=name,
            ))

        except ExperimentDirectoryDoesNotExistError as e:
            return Result.from_exception(e)

    def example(self, project_path: Path, name: str) -> Result[ExperimentInfo]:
        """
        Create an example experiment with sample playbook content.

        Args:
            project_path: Path to the project
            name: Experiment name

        Returns:
            Result[ExperimentInfo] with created experiment info on success.
        """
        try:
            backend_experiment_example(project_path, name)

            # Build experiment info
            experiment_dir = ExperimentDirectory(project_path, name)

            next_steps = [
                f'Review the example playbook at {experiment_dir.playbookfile}',
                f'Load the experiment with: adare experiment load {name}',
                f'Run the experiment with: adare experiment run {name} -e <environment>'
            ]

            return Result.ok(ExperimentInfo(
                id='',
                name=name,
                description='Example experiment',
                file_path=experiment_dir.path,
                sha256='',
                environment_names=[],
                run_count=0,
                productive_run_count=0,
                is_loaded=False,
                next_steps=next_steps,
                tip='This example demonstrates basic playbook structure',
            ))

        except ExperimentDirectoryAlreadyExistsError as e:
            return Result.from_exception(e)

    def test(self, project_path: Path, name: str, environment_name: str) -> Result[None]:
        """
        Run experiment tests without full execution (dry-run).

        Args:
            project_path: Path to the project
            name: Experiment name
            environment_name: Environment to test against

        Returns:
            Result[None] on success, or error information on failure.
        """
        try:
            backend_experiment_test(project_path, name, environment_name)
            return Result.ok(None)

        except ExperimentDirectoryDoesNotExistError as e:
            return Result.from_exception(e)

    def validate(self, request: ExperimentValidateRequest) -> Result[ExperimentValidateResult]:
        """
        Validate experiment configuration and integrity without starting a VM.

        Args:
            request: ExperimentValidateRequest with project path, name, and optional environment

        Returns:
            Result[ExperimentValidateResult] with validation check results.
        """
        try:
            checks = backend_experiment_validate(
                request.project_path,
                request.name,
                environment_name=request.environment,
            )

            return Result.ok(ExperimentValidateResult(
                name=request.name,
                checks=checks,
            ))

        except (ExperimentDirectoryDoesNotExistError, ExperimentIntegrityError) as e:
            return Result.from_exception(e)

    # =========================================================================
    # Environment Management
    # =========================================================================

    def add_environments(self, request: ExperimentEnvModifyRequest) -> Result[ExperimentEnvModifyResult]:
        """
        Add environments to experiment(s).

        Args:
            request: ExperimentEnvModifyRequest with pattern and environments

        Returns:
            Result[ExperimentEnvModifyResult] with affected experiments.
        """
        try:
            result = backend_experiment_add_environments(
                request.project_path,
                request.experiment_pattern,
                request.environments,
                force=request.force
            )

            return Result.ok(ExperimentEnvModifyResult(
                affected_experiments=result.get('affected_experiments', []),
                environments_changed=request.environments,
                operation='add',
            ))

        except ExperimentDirectoryDoesNotExistError as e:
            return Result.from_exception(e)

    def remove_environments(self, request: ExperimentEnvModifyRequest) -> Result[ExperimentEnvModifyResult]:
        """
        Remove environments from experiment(s).

        Args:
            request: ExperimentEnvModifyRequest with pattern and environments

        Returns:
            Result[ExperimentEnvModifyResult] with affected experiments.
        """
        try:
            result = backend_experiment_remove_environments(
                request.project_path,
                request.experiment_pattern,
                request.environments,
                force=request.force
            )

            return Result.ok(ExperimentEnvModifyResult(
                affected_experiments=result.get('affected_experiments', []),
                environments_changed=request.environments,
                operation='remove',
            ))

        except ExperimentDirectoryDoesNotExistError as e:
            return Result.from_exception(e)

    # =========================================================================
    # Queries
    # =========================================================================

    def list_all(self, project_path: Path) -> Result[list[ExperimentListItem]]:
        """
        List all experiments in a project.

        Args:
            project_path: Path to the project

        Returns:
            Result[List[ExperimentListItem]] with all experiments.
        """
        try:
            with ExperimentApi(project_path) as api:
                experiments = api.get_experiments()

                items = []
                for exp in experiments:
                    env_count = len(exp.environments) if exp.environments else 0

                    # Count runs
                    run_count = 0
                    try:
                        run_count = experiment_database.get_experiment_run_count(exp.id, exclude_fake=False)
                    except (SQLAlchemyError, ValueError):
                        pass

                    items.append(ExperimentListItem(
                        id=exp.id,
                        name=exp.name,
                        description=exp.description or "",
                        environment_count=env_count,
                        run_count=run_count,
                    ))

                return Result.ok(items)

        except (SQLAlchemyError, OSError) as e:
            log.error(f"Failed to list experiments: {e}")
            return Result.fail(
                code="ExperimentListError",
                message=f"Failed to list experiments: {e}",
                solutions=['Check project directory', 'Ensure database is accessible']
            )

    def get_by_name(self, project_path: Path, name: str) -> Result[ExperimentInfo]:
        """
        Get an experiment by its name.

        Args:
            project_path: Path to the project
            name: Experiment name

        Returns:
            Result[ExperimentInfo] with experiment data, or error if not found.
        """
        try:
            with ExperimentApi(project_path) as api:
                experiment = api.get_experiment_by_project_and_name(project_path, name)

                if not experiment:
                    return Result.fail(
                        code="ExperimentNotFoundError",
                        message=f'Experiment "{name}" not found in project',
                        solutions=[
                            'Use `adare experiment list` to see available experiments',
                            f'Load the experiment with: adare experiment load {name}',
                            'Check if the experiment name is spelled correctly',
                        ]
                    )

                # Get environment names
                env_names = [env.name for env in experiment.environments] if experiment.environments else []

                # Count runs
                run_count = 0
                productive_run_count = 0
                try:
                    run_count = experiment_database.get_experiment_run_count(experiment.id, exclude_fake=False)
                    productive_run_count = experiment_database.get_experiment_run_count(experiment.id, exclude_fake=True)
                except (SQLAlchemyError, ValueError):
                    pass

                experiment_dir = ExperimentDirectory(project_path, name)

                return Result.ok(ExperimentInfo(
                    id=experiment.id,
                    name=experiment.name,
                    description=experiment.description or "",
                    file_path=experiment_dir.path if experiment_dir.exists() else Path(""),
                    sha256=experiment.sha256 or "",
                    environment_names=env_names,
                    run_count=run_count,
                    productive_run_count=productive_run_count,
                    is_loaded=True,
                ))

        except (SQLAlchemyError, OSError) as e:
            log.error(f"Failed to get experiment: {e}")
            return Result.fail(
                code="ExperimentGetError",
                message=f"Failed to get experiment: {e}",
                solutions=['Check if experiment exists', 'Try reloading the experiment']
            )

    def get_by_id(self, project_path: Path, experiment_id: str) -> Result[ExperimentInfo]:
        """
        Get an experiment by its ID.

        Args:
            project_path: Path to the project
            experiment_id: Experiment ULID

        Returns:
            Result[ExperimentInfo] with experiment data, or error if not found.
        """
        try:
            with ExperimentApi(project_path) as api:
                experiment = api.get_experiment_by_id(experiment_id)

                if not experiment:
                    return Result.fail(
                        code="ExperimentNotFoundError",
                        message=f'Experiment with ID {experiment_id} not found',
                        solutions=[
                            'Use `adare experiment list` to see available experiments',
                            'Check if the experiment ID is correct',
                        ]
                    )

                return self.get_by_name(project_path, experiment.name)

        except (SQLAlchemyError, OSError) as e:
            log.error(f"Failed to get experiment by ID: {e}")
            return Result.fail(
                code="ExperimentGetError",
                message=f"Failed to get experiment by ID: {e}",
                solutions=['Check if experiment exists']
            )
