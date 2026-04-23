# external imports
# configure logging
import logging
from pathlib import Path

from sqlalchemy.orm import joinedload, selectinload

import adare.config.database as config_database
from adare.database.api.database import DatabaseApi

# internal imports
from adare.database.models.global_models import Environment, Project, TestFunction, TestFunctionFile, Vm
from adare.database.models.project_models import (
    Experiment,
    ExperimentRun,
)
from adare.database.utils.display_helpers import (
    get_current_project_name,
    get_smart_display_name,
    safe_get_os_info,
    safe_get_sync_status,
    safe_get_tags,
    safe_get_vm_info,
)
from adare.database.utils.error_handling import DataRetrievalError, safe_query_all, safe_query_first
from adare.types.output_models import EnvironmentInfo, ExperimentInfo, ProjectInfo, RunInfo, TestFunctionInfo

log = logging.getLogger(__name__)


class StructuredDataApi(DatabaseApi):
    """
    Database API for retrieving data as structured objects (not DataFrames).

    This API is designed for JSON/YAML output and automation use cases.
    For Rich terminal display, use DataRetrievalApi instead.
    """

    def __init__(self, db_path: Path = config_database.get_database_location()):
        super().__init__(db_path)

    def get_projects_structured(self) -> list[ProjectInfo]:
        """Get all projects as structured ProjectInfo objects."""
        projects = safe_query_all(self._session.query(Project))
        result = []

        for project in projects:
            project_info = ProjectInfo(
                name=project.name,
                description=project.description or "",
                path=project.path or "",
            )
            result.append(project_info)

        return result

    def get_environments_structured(self) -> list[EnvironmentInfo]:
        """Get all environments as structured EnvironmentInfo objects."""
        # Use eager loading to prevent N+1 queries
        environments = safe_query_all(self._session.query(Environment).options(
            joinedload(Environment.vm).joinedload(Vm.osinfo),
            selectinload(Environment.sync_metadata)
        ))
        result = []

        for env in environments:
            # Use utility functions for cleaner, reusable code
            vm_name, vm_id = safe_get_vm_info(env)
            os_info_str, osinfo_os, osinfo_distribution, osinfo_version, osinfo_language = safe_get_os_info(env.vm)
            published, in_request = safe_get_sync_status(env)
            # Environments are global, display name is just the environment name
            display_name = env.name

            env_info = EnvironmentInfo(
                name=env.name,
                display_name=display_name,
                ulid=env.id,
                dotnotation=env.name,  # Environments don't have dotnotation, just use name
                project="Global",  # Environments are global resources
                description=env.description or "",
                os_info=os_info_str,
                vm_box=vm_name,
                vm_id=vm_id,
                osinfo_os=osinfo_os,
                osinfo_distribution=osinfo_distribution,
                osinfo_version=osinfo_version,
                osinfo_language=osinfo_language,
                created_at=env.created_at,
                published=published,
                in_request=in_request,
                file=env.file or ""
            )
            result.append(env_info)

        return result

    def get_experiments_structured(self, project_name: str = None) -> list[ExperimentInfo]:
        """Get all experiments as structured ExperimentInfo objects."""
        # Use eager loading to prevent N+1 queries
        experiments = safe_query_all(self._session.query(Experiment).options(
            selectinload(Experiment.tags)
        ))
        result = []

        # Use explicitly passed project_name first, fall back to CWD detection
        project_name = project_name or get_current_project_name() or ""

        for exp in experiments:
            # Use utility functions for cleaner, reusable code
            dotnotation = f"{project_name}.{exp.name}" if project_name else exp.name

            display_name = get_smart_display_name(exp, 'experiment')
            env_names = [env.name for env in exp.environments if env]
            primary_env = env_names[0] if env_names else ""
            tags = safe_get_tags(exp)
            published, in_request = safe_get_sync_status(exp)

            exp_info = ExperimentInfo(
                name=exp.name,
                display_name=display_name,
                ulid=exp.id,
                dotnotation=dotnotation,
                project=project_name,
                environment=primary_env,
                environments=env_names,
                description=exp.description or "",
                tags=tags,
                created_at=exp.created_at,
                published=published,
                in_request=in_request
            )
            result.append(exp_info)

        return result

    def get_testfunctions_structured(self, include_parameters: bool = True, testfunction_file: str = None) -> list[TestFunctionInfo]:
        """Get all testfunctions as structured TestFunctionInfo objects."""
        # Validate testfunction_file parameter if provided
        if testfunction_file and not isinstance(testfunction_file, str):
            raise DataRetrievalError("testfunction_file must be a string")

        # Build query with eager loading to prevent N+1 queries
        query_options = [
            joinedload(TestFunction.file)
        ]
        if include_parameters:
            query_options.append(selectinload(TestFunction.parameters))

        query = self._session.query(TestFunction).options(*query_options)

        # Apply file filtering if specified
        if testfunction_file:
            file_obj = safe_query_first(
                self._session.query(TestFunctionFile).filter_by(name=testfunction_file)
            )
            if file_obj:
                query = query.filter(TestFunction.file_id == file_obj.id)
            else:
                # No matching file found, return empty list
                log.info(f"No testfunction file found with name: {testfunction_file}")
                return []

        testfunctions = safe_query_all(query)
        result = []

        for tf in testfunctions:
            try:
                # Validate required fields
                if not tf.id or not tf.name:
                    log.warning(f"Skipping testfunction with missing required fields: id={tf.id}, name={tf.name}")
                    continue

                # File information is now eagerly loaded
                tf_file = tf.file
                file_name = tf_file.name if tf_file else "unknown"
                file_name_clean = file_name.replace('.py', '') if file_name.endswith('.py') else file_name


                # Use utility function for smart display name
                display_name = get_smart_display_name(tf, 'testfunction')

                # Parameters are now eagerly loaded
                parameters = []
                if include_parameters and tf.parameters:
                    for param in tf.parameters:
                        # Validate parameter data
                        if param.id and param.name:
                            parameters.append({
                                'id': param.id,
                                'name': param.name,
                                'description': param.description or '',
                                'data_type': param.dtype or '',
                                'optional': param.optional or False,
                                'required': not (param.optional or False)
                            })

                tf_info = TestFunctionInfo(
                    id=tf.id,
                    name=tf.name,
                    dotnotation=tf.dotnotation or f"unknown.{tf.name}",
                    display_name=display_name,
                    description=tf.description or "",
                    parameter_count=len(tf.parameters) if tf.parameters else 0,
                    parameters=parameters,
                    file_id=tf.file_id or "",
                    file_name=file_name,
                    file_path=file_name_clean,
                    full_file_path=tf_file.path if tf_file else "",
                    file_sha256=tf_file.sha256hash if tf_file else "",
                    file_description=tf_file.description if tf_file else ""
                )
                result.append(tf_info)
            except Exception as e:
                log.error(f"Error processing testfunction {tf.id}: {e}")
                continue

        return result

    def get_runs_structured(self, project_name: str = None, environment_name: str = None, experiment_name: str = None) -> list[RunInfo]:
        """Get runs as structured RunInfo objects with optional filtering."""
        # Validate input parameters
        for param_name, param_value in [('project_name', project_name), ('environment_name', environment_name), ('experiment_name', experiment_name)]:
            if param_value is not None and not isinstance(param_value, str):
                raise DataRetrievalError(f"{param_name} must be a string")

        # Use eager loading to prevent N+1 queries
        query = self._session.query(ExperimentRun).options(
            joinedload(ExperimentRun.experiment)
        )

        # Apply filters
        # Note: Experiments are stored per-project in separate databases,
        # so the database context already determines the project.
        # Filtering by project_name is not needed at the database level.
        if experiment_name:
            query = query.join(Experiment).filter(
                Experiment.name == experiment_name
            )

        runs = safe_query_all(query)
        result = []

        # Get current project name from context (experiments are stored per-project)
        current_project_name = project_name or get_current_project_name() or ""

        for run in runs:
            # Experiment and environment info are now eagerly loaded
            experiment = run.experiment
            env = experiment.environments[0] if experiment.environments else None

            # Calculate duration
            duration_seconds = 0.0
            if run.start_time and run.end_time:
                duration = run.end_time - run.start_time
                duration_seconds = duration.total_seconds()

            # Create experiment dotnotation
            exp_dotnotation = f"{current_project_name}.{experiment.name}" if current_project_name else experiment.name

            run_info = RunInfo(
                ulid=run.id,
                experiment_name=exp_dotnotation,
                experiment_ulid=experiment.id,
                environment_name=env.name if env else "",
                environment_ulid=env.id if env else "",
                project_name=current_project_name,
                start_time=run.start_time,
                end_time=run.end_time,
                duration_seconds=duration_seconds,
                status=run.status,
                published=run.published or False,
                fake=run.fake or False,
                overall_result=run.result_status or ""
            )
            result.append(run_info)

        return result
