"""
Project Database API.

This module provides database operations for project-specific databases
in the new multi-database architecture. Each project gets its own database
containing only project-specific data and references to global resources.
"""

import logging
import shutil
from pathlib import Path
from typing import Optional, List, Dict, Any, Tuple
from datetime import datetime
import json

from sqlalchemy.orm import joinedload, selectinload
from sqlalchemy.exc import IntegrityError
from sqlalchemy import func

from adare.database.api.base import EnhancedDatabaseApi
from adare.database.models.project_database import (
    ProjectMetadata,
    GlobalResourceReference,
    ProjectExperiment,
    ExperimentEnvironmentReference,
    ProjectTestFunctionFile,
    ProjectTestFunction,
    ProjectExperimentRun,
    ProjectTag,
    ProjectTool
)
from adare.database.exceptions import (
    DatabaseError,
    EntityNotFoundError,
    ValidationError
)

log = logging.getLogger(__name__)


class ProjectDatabaseApi(EnhancedDatabaseApi):
    """
    Database API for project-specific operations.

    Manages project-specific data in per-project databases while providing
    integration with global resource registries.
    """

    def __init__(self, project_path: Path):
        """
        Initialize project database API.

        Args:
            project_path: Absolute path to project directory
        """
        self.project_path = Path(project_path)
        self.project_db_path = self.project_path / '.adare' / 'project.db'
        super().__init__(db_path=self.project_db_path)
        self._ensure_project_database()

    def _ensure_project_database(self):
        """Ensure project database and directory structure exists."""
        try:
            # Create project .adare directory
            self.project_db_path.parent.mkdir(parents=True, exist_ok=True)

            # Create database tables if they don't exist
            from adare.database.models.project_database import Base as ProjectBase
            ProjectBase.metadata.create_all(self._engine)

            # Ensure project metadata exists
            with self:
                metadata = self._session.query(ProjectMetadata).first()
                if not metadata:
                    metadata = ProjectMetadata(
                        name=self.project_path.name,
                        path=str(self.project_path),
                        schema_version="1.0.0"
                    )
                    self._session.add(metadata)
                    self._session.commit()
                    log.info(f"Created project metadata for {self.project_path.name}")

        except Exception as e:
            log.error(f"Failed to setup project database: {e}")
            raise DatabaseError(f"Cannot setup project database: {e}")

    def get_project_metadata(self) -> ProjectMetadata:
        """
        Get project metadata.

        Returns:
            ProjectMetadata instance

        Raises:
            EntityNotFoundError: If project metadata not found
        """
        with self:
            metadata = self._session.query(ProjectMetadata).first()
            if not metadata:
                raise EntityNotFoundError("Project metadata not found")
            return metadata

    def update_project_metadata(self, **kwargs) -> ProjectMetadata:
        """
        Update project metadata.

        Args:
            **kwargs: Fields to update

        Returns:
            Updated ProjectMetadata instance
        """
        with self:
            metadata = self.get_project_metadata()

            allowed_fields = {
                'name', 'description', 'version', 'auto_cleanup',
                'default_vm_ref', 'default_env_ref'
            }

            for key, value in kwargs.items():
                if key in allowed_fields:
                    setattr(metadata, key, value)
                else:
                    log.warning(f"Ignoring update to non-updateable field: {key}")

            self._session.commit()
            log.info(f"Updated project metadata: {metadata.name}")
            return metadata

    def add_global_resource_reference(self, resource_type: str, global_resource_id: str,
                                     project_alias: str = None, usage_notes: str = None,
                                     configuration_overrides: Dict = None,
                                     pinned_version: str = None) -> GlobalResourceReference:
        """
        Add a reference to a global resource.

        Args:
            resource_type: Type of resource ('vm' or 'environment')
            global_resource_id: ID of resource in global registry
            project_alias: Project-specific name for the resource
            usage_notes: Project-specific notes
            configuration_overrides: Project-specific configuration
            pinned_version: Pin to specific resource version

        Returns:
            GlobalResourceReference instance

        Raises:
            ValidationError: If resource type is invalid or reference already exists
        """
        with self:
            if resource_type not in ['vm', 'environment']:
                raise ValidationError(f"Invalid resource type: {resource_type}")

            # Check if reference already exists
            existing_ref = self._session.query(GlobalResourceReference).filter(
                GlobalResourceReference.resource_type == resource_type,
                GlobalResourceReference.global_resource_id == global_resource_id
            ).first()

            if existing_ref:
                raise ValidationError(
                    f"Reference to {resource_type} {global_resource_id} already exists"
                )

            # Serialize configuration overrides
            config_json = None
            if configuration_overrides:
                try:
                    config_json = json.dumps(configuration_overrides)
                except (TypeError, ValueError) as e:
                    log.warning(f"Failed to serialize configuration overrides: {e}")

            reference = GlobalResourceReference(
                resource_type=resource_type,
                global_resource_id=global_resource_id,
                project_alias=project_alias,
                usage_notes=usage_notes,
                configuration_overrides=config_json,
                pinned_version=pinned_version
            )

            self._session.add(reference)
            self._session.commit()

            log.info(f"Added global resource reference: {resource_type}:{global_resource_id}")
            return reference

    def get_global_resource_references(self, resource_type: str = None) -> List[GlobalResourceReference]:
        """
        Get global resource references for this project.

        Args:
            resource_type: Filter by resource type ('vm', 'environment', or None for all)

        Returns:
            List of GlobalResourceReference instances
        """
        with self:
            query = self._session.query(GlobalResourceReference)

            if resource_type:
                if resource_type not in ['vm', 'environment']:
                    raise ValidationError(f"Invalid resource type: {resource_type}")
                query = query.filter(GlobalResourceReference.resource_type == resource_type)

            return query.order_by(
                GlobalResourceReference.resource_type,
                GlobalResourceReference.project_alias
            ).all()

    def remove_global_resource_reference(self, resource_type: str, global_resource_id: str) -> bool:
        """
        Remove a global resource reference.

        Args:
            resource_type: Type of resource
            global_resource_id: ID of resource in global registry

        Returns:
            True if reference was removed
        """
        with self:
            reference = self._session.query(GlobalResourceReference).filter(
                GlobalResourceReference.resource_type == resource_type,
                GlobalResourceReference.global_resource_id == global_resource_id
            ).first()

            if reference:
                self._session.delete(reference)
                self._session.commit()
                log.info(f"Removed global resource reference: {resource_type}:{global_resource_id}")
                return True

            return False

    def create_experiment(self, name: str, description: str = '', playbook_file: str = None,
                         metadata_file: str = None, **kwargs) -> ProjectExperiment:
        """
        Create a new experiment in this project.

        Args:
            name: Experiment name (must be unique within project)
            description: Experiment description
            playbook_file: Path to playbook file (relative to project)
            metadata_file: Path to metadata file (relative to project)
            **kwargs: Additional experiment fields

        Returns:
            ProjectExperiment instance

        Raises:
            ValidationError: If experiment name already exists
        """
        with self:
            # Check for existing experiment
            existing_exp = self._session.query(ProjectExperiment).filter(
                ProjectExperiment.name == name
            ).first()

            if existing_exp:
                raise ValidationError(f"Experiment with name '{name}' already exists")

            experiment = ProjectExperiment(
                name=name,
                description=description,
                playbook_file=playbook_file,
                metadata_file=metadata_file,
                **kwargs
            )

            self._session.add(experiment)
            self._session.flush()  # Get ID

            log.info(f"Created experiment: {name}")
            return experiment

    def get_experiment_by_name(self, name: str) -> Optional[ProjectExperiment]:
        """Get experiment by name."""
        with self:
            return self._session.query(ProjectExperiment).filter(
                ProjectExperiment.name == name
            ).first()

    def get_all_experiments(self, include_environment_refs: bool = False) -> List[ProjectExperiment]:
        """
        Get all experiments in this project.

        Args:
            include_environment_refs: If True, eagerly load environment references

        Returns:
            List of ProjectExperiment instances
        """
        with self:
            query = self._session.query(ProjectExperiment)

            if include_environment_refs:
                query = query.options(selectinload(ProjectExperiment.environment_refs))

            return query.order_by(ProjectExperiment.name).all()

    def add_environment_to_experiment(self, experiment_name: str, global_environment_id: str,
                                     environment_alias: str = None,
                                     configuration_overrides: Dict = None,
                                     execution_order: int = None,
                                     is_primary: bool = False) -> ExperimentEnvironmentReference:
        """
        Add an environment reference to an experiment.

        Args:
            experiment_name: Name of experiment
            global_environment_id: ID of environment in global registry
            environment_alias: Project-specific alias for environment
            configuration_overrides: Project-specific environment configuration
            execution_order: Order for multi-environment experiments
            is_primary: Whether this is the primary environment

        Returns:
            ExperimentEnvironmentReference instance

        Raises:
            EntityNotFoundError: If experiment not found
            ValidationError: If environment already referenced by experiment
        """
        with self:
            experiment = self._session.query(ProjectExperiment).filter(
                ProjectExperiment.name == experiment_name
            ).first()

            if not experiment:
                raise EntityNotFoundError(f"Experiment '{experiment_name}' not found")

            # Check if environment already referenced
            existing_ref = self._session.query(ExperimentEnvironmentReference).filter(
                ExperimentEnvironmentReference.experiment_id == experiment.id,
                ExperimentEnvironmentReference.global_environment_id == global_environment_id
            ).first()

            if existing_ref:
                raise ValidationError(
                    f"Environment {global_environment_id} already referenced by experiment {experiment_name}"
                )

            # If this is primary, unset any existing primary
            if is_primary:
                self._session.query(ExperimentEnvironmentReference).filter(
                    ExperimentEnvironmentReference.experiment_id == experiment.id,
                    ExperimentEnvironmentReference.is_primary == True
                ).update({'is_primary': False})

            # Serialize configuration overrides
            config_json = None
            if configuration_overrides:
                try:
                    config_json = json.dumps(configuration_overrides)
                except (TypeError, ValueError) as e:
                    log.warning(f"Failed to serialize configuration overrides: {e}")

            env_ref = ExperimentEnvironmentReference(
                experiment_id=experiment.id,
                global_environment_id=global_environment_id,
                environment_alias=environment_alias,
                configuration_overrides=config_json,
                execution_order=execution_order,
                is_primary=is_primary
            )

            self._session.add(env_ref)
            self._session.commit()

            log.info(f"Added environment reference: {experiment_name} -> {global_environment_id}")
            return env_ref

    def create_experiment_run(self, experiment_name: str, environment_ref_id: str,
                             executed_by: str = None, execution_notes: str = None) -> ProjectExperimentRun:
        """
        Create a new experiment run.

        Args:
            experiment_name: Name of experiment
            environment_ref_id: ID of environment reference to use
            executed_by: User who executed the run
            execution_notes: Notes about this run

        Returns:
            ProjectExperimentRun instance

        Raises:
            EntityNotFoundError: If experiment or environment reference not found
        """
        with self:
            experiment = self._session.query(ProjectExperiment).filter(
                ProjectExperiment.name == experiment_name
            ).first()

            if not experiment:
                raise EntityNotFoundError(f"Experiment '{experiment_name}' not found")

            env_ref = self._session.query(ExperimentEnvironmentReference).filter(
                ExperimentEnvironmentReference.id == environment_ref_id
            ).first()

            if not env_ref:
                raise EntityNotFoundError(f"Environment reference '{environment_ref_id}' not found")

            run = ProjectExperimentRun(
                experiment_id=experiment.id,
                environment_ref_id=environment_ref_id,
                executed_by=executed_by,
                execution_notes=execution_notes
            )

            self._session.add(run)
            self._session.flush()

            # Update experiment last_run timestamp
            experiment.last_run = datetime.utcnow()
            self._session.commit()

            log.info(f"Created experiment run: {experiment_name} -> {run.id}")
            return run

    def get_experiment_runs(self, experiment_name: str = None,
                           limit: int = None) -> List[ProjectExperimentRun]:
        """
        Get experiment runs for this project.

        Args:
            experiment_name: Filter by experiment name (optional)
            limit: Maximum number of runs to return

        Returns:
            List of ProjectExperimentRun instances
        """
        with self:
            query = self._session.query(ProjectExperimentRun).options(
                joinedload(ProjectExperimentRun.experiment),
                joinedload(ProjectExperimentRun.environment_ref)
            )

            if experiment_name:
                query = query.join(ProjectExperiment).filter(
                    ProjectExperiment.name == experiment_name
                )

            query = query.order_by(ProjectExperimentRun.started_at.desc())

            if limit:
                query = query.limit(limit)

            return query.all()

    def update_experiment_run_status(self, run_id: str, status: str,
                                    completed_at: datetime = None,
                                    results_path: str = None, log_path: str = None,
                                    error_message: str = None, error_details: Dict = None):
        """
        Update experiment run status and results.

        Args:
            run_id: Run ID
            status: New status
            completed_at: Completion timestamp
            results_path: Path to results (relative to project)
            log_path: Path to log file (relative to project)
            error_message: Error message if failed
            error_details: Detailed error information
        """
        with self:
            run = self.get_by_ulid_or_404(ProjectExperimentRun, run_id)

            run.status = status
            if completed_at:
                run.completed_at = completed_at
            if results_path:
                run.results_path = results_path
            if log_path:
                run.log_path = log_path
            if error_message:
                run.error_message = error_message
            if error_details:
                try:
                    run.error_details = json.dumps(error_details)
                except (TypeError, ValueError) as e:
                    log.warning(f"Failed to serialize error details: {e}")

            self._session.commit()
            log.info(f"Updated experiment run {run_id}: status={status}")

    def get_project_statistics(self) -> Dict[str, Any]:
        """
        Get statistics about this project.

        Returns:
            Dict with project statistics
        """
        with self:
            stats = {
                'project_name': self.project_path.name,
                'project_path': str(self.project_path),
                'experiments_count': self._session.query(ProjectExperiment).count(),
                'runs_count': self._session.query(ProjectExperimentRun).count(),
                'test_function_files_count': self._session.query(ProjectTestFunctionFile).count(),
                'test_functions_count': self._session.query(ProjectTestFunction).count(),
                'global_resource_references': {
                    'vm_references': self._session.query(GlobalResourceReference).filter(
                        GlobalResourceReference.resource_type == 'vm'
                    ).count(),
                    'environment_references': self._session.query(GlobalResourceReference).filter(
                        GlobalResourceReference.resource_type == 'environment'
                    ).count()
                },
                'database_size_bytes': None
            }

            # Get database size
            try:
                stats['database_size_bytes'] = self.project_db_path.stat().st_size
            except OSError:
                pass

            # Get recent activity
            recent_runs = self._session.query(ProjectExperimentRun).order_by(
                ProjectExperimentRun.started_at.desc()
            ).limit(5).all()

            stats['recent_runs'] = [
                {
                    'experiment_name': run.experiment.name,
                    'started_at': run.started_at.isoformat(),
                    'status': run.status,
                    'duration_seconds': run.duration_seconds
                }
                for run in recent_runs
            ]

            return stats

    def cleanup_project_data(self, older_than_days: int = 30,
                            cleanup_runs: bool = True,
                            cleanup_logs: bool = False,
                            dry_run: bool = True) -> Dict[str, Any]:
        """
        Clean up old project data.

        Args:
            older_than_days: Remove data older than this many days
            cleanup_runs: Clean up old experiment runs
            cleanup_logs: Clean up old log files
            dry_run: If True, don't actually delete anything

        Returns:
            Dict with cleanup results
        """
        from datetime import timedelta

        cutoff_date = datetime.utcnow() - timedelta(days=older_than_days)

        results = {
            'dry_run': dry_run,
            'runs_deleted': 0,
            'logs_deleted': 0,
            'space_freed_bytes': 0,
            'errors': []
        }

        try:
            with self:
                if cleanup_runs:
                    old_runs = self._session.query(ProjectExperimentRun).filter(
                        ProjectExperimentRun.started_at < cutoff_date
                    ).all()

                    for run in old_runs:
                        try:
                            if not dry_run:
                                # Delete results and log files if they exist
                                if run.results_path:
                                    results_path = self.project_path / run.results_path
                                    if results_path.exists():
                                        if results_path.is_dir():
                                            shutil.rmtree(results_path)
                                        else:
                                            results_path.unlink()

                                if run.log_path:
                                    log_path = self.project_path / run.log_path
                                    if log_path.exists():
                                        log_path.unlink()

                                self._session.delete(run)

                            results['runs_deleted'] += 1

                        except Exception as e:
                            results['errors'].append(f"Failed to delete run {run.id}: {e}")

                    if not dry_run:
                        self._session.commit()

        except Exception as e:
            results['errors'].append(f"Cleanup error: {e}")

        log.info(f"Project cleanup completed: {results}")
        return results