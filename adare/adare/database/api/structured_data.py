# external imports
from typing import List, Optional
import pandas as pd
from pathlib import Path

# internal imports
from adare.database.models.experiment import (
    Project, Environment, Experiment, ExperimentRun, TestFunction, TestParameter, TestFunctionFile, Vm, OsInfo
)
from adare.database.api.database import DatabaseApi
import adare.config.database as config_database
from adare.types.output_models import (
    ProjectInfo, EnvironmentInfo, ExperimentInfo, TestFunctionInfo, RunInfo
)

# configure logging
import logging
log = logging.getLogger(__name__)


class StructuredDataApi(DatabaseApi):
    """
    Database API for retrieving data as structured objects (not DataFrames).

    This API is designed for JSON/YAML output and automation use cases.
    For Rich terminal display, use DataRetrievalApi instead.
    """

    def __init__(self, db_path: Path = config_database.get_database_location()):
        super().__init__(db_path)

    def get_projects_structured(self) -> List[ProjectInfo]:
        """Get all projects as structured ProjectInfo objects."""
        projects = self._session.query(Project).all()
        result = []

        for project in projects:
            # Count environments for this project
            env_count = self._session.query(Environment).filter(
                Environment.project_id == project.id
            ).count()

            project_info = ProjectInfo(
                name=project.name,
                description=project.description or "",
                created_at=project.created_at,
                environment_count=env_count
            )
            result.append(project_info)

        return result

    def get_environments_structured(self) -> List[EnvironmentInfo]:
        """Get all environments as structured EnvironmentInfo objects."""
        environments = self._session.query(Environment).all()
        result = []

        for env in environments:
            # Get VM information
            vm = self._session.query(Vm).filter_by(id=env.vm_id).first() if env.vm_id else None
            vm_name = vm.name if vm else "No VM"
            vm_id = vm.id if vm else ""

            # Get OS information
            osinfo = None
            if vm and hasattr(vm, 'osinfo_id'):
                osinfo = self._session.query(OsInfo).filter_by(id=vm.osinfo_id).first()

            # Get sync status
            published = bool(env.sync_metadata.is_synced) if hasattr(env, 'sync_metadata') and env.sync_metadata else False
            in_request = bool(env.sync_metadata.needs_sync) if hasattr(env, 'sync_metadata') and env.sync_metadata else False

            # Get smart display name
            from adare.backend.basics import determine_projectdirectory
            current_project_name = None
            if project_path := determine_projectdirectory(None, silent=True):
                current_project_name = project_path.name

            display_name = env.name
            if current_project_name and env.project.name != current_project_name:
                display_name = env.dotnotation

            env_info = EnvironmentInfo(
                name=env.name,
                display_name=display_name,
                ulid=env.id,
                dotnotation=env.dotnotation,
                project=env.project.name,
                description=env.description or "",
                os_info=str(osinfo) if osinfo else "Unknown",
                vm_box=vm_name,
                vm_id=vm_id,
                osinfo_os=osinfo.os if osinfo else "",
                osinfo_distribution=osinfo.distribution if osinfo else "",
                osinfo_version=osinfo.version if osinfo else "",
                osinfo_language=osinfo.language if osinfo else "",
                created_at=env.created_at,
                published=published,
                in_request=in_request
            )
            result.append(env_info)

        return result

    def get_experiments_structured(self) -> List[ExperimentInfo]:
        """Get all experiments as structured ExperimentInfo objects."""
        experiments = self._session.query(Experiment).all()
        result = []

        for exp in experiments:
            # Get first environment for project context
            first_env = exp.environments[0] if exp.environments else None
            project_name = first_env.project.name if first_env else ""

            # Create dotnotation
            dotnotation = f"{project_name}.{exp.name}" if project_name else exp.name

            # Get smart display name
            from adare.backend.basics import determine_projectdirectory
            current_project_name = None
            if project_path := determine_projectdirectory(None, silent=True):
                current_project_name = project_path.name

            display_name = exp.name
            if current_project_name and project_name != current_project_name:
                display_name = dotnotation

            # Get environment names
            env_names = [env.name for env in exp.environments]
            primary_env = env_names[0] if env_names else ""

            # Get tags
            tags = [tag.name for tag in exp.tags] if hasattr(exp, 'tags') else []

            # Get sync status
            published = bool(exp.sync_metadata.is_synced) if hasattr(exp, 'sync_metadata') and exp.sync_metadata else False
            in_request = bool(exp.sync_metadata.needs_sync) if hasattr(exp, 'sync_metadata') and exp.sync_metadata else False

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

    def get_testfunctions_structured(self, include_parameters: bool = True, testfunction_file: str = None) -> List[TestFunctionInfo]:
        """Get all testfunctions as structured TestFunctionInfo objects."""
        query = self._session.query(TestFunction)

        # Apply file filtering if specified
        if testfunction_file:
            file_obj = self._session.query(TestFunctionFile).filter_by(name=testfunction_file).first()
            if file_obj:
                query = query.filter(TestFunction.file_id == file_obj.id)
            else:
                # No matching file found, return empty list
                return []

        testfunctions = query.all()
        result = []

        for tf in testfunctions:
            # Get file information
            tf_file = self._session.query(TestFunctionFile).filter_by(id=tf.file_id).first()
            file_name = tf_file.name if tf_file else "unknown"
            file_name_clean = file_name.replace('.py', '') if file_name.endswith('.py') else file_name

            # Get smart display name
            from adare.backend.basics import determine_projectdirectory
            current_project_name = None
            if project_path := determine_projectdirectory(None, silent=True):
                current_project_name = project_path.name

            display_name = tf.name
            if current_project_name and '.' in tf.dotnotation:
                # Check if testfunction is from current project context
                tf_project = tf.dotnotation.split('.', 1)[0]
                if tf_project == current_project_name:
                    display_name = tf.dotnotation.split('.', 1)[1] if '.' in tf.dotnotation else tf.name
                else:
                    display_name = tf.dotnotation

            # Get parameters if requested
            parameters = []
            if include_parameters and tf.parameters:
                for param in tf.parameters:
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
                dotnotation=tf.dotnotation,
                display_name=display_name,
                description=tf.description or "",
                parameter_count=len(tf.parameters) if tf.parameters else 0,
                parameters=parameters,
                file_id=tf.file_id,
                file_name=file_name,
                file_path=file_name_clean,
                full_file_path=tf_file.path if tf_file else "",
                file_sha256=tf_file.sha256hash if tf_file else "",
                file_description=tf_file.description if tf_file else ""
            )
            result.append(tf_info)

        return result

    def get_runs_structured(self, project_name: str = None, environment_name: str = None, experiment_name: str = None) -> List[RunInfo]:
        """Get runs as structured RunInfo objects with optional filtering."""
        query = self._session.query(ExperimentRun)

        # Apply filters
        if experiment_name and environment_name and project_name:
            query = query.join(Experiment).join(Experiment.environments).join(Environment.project).filter(
                Experiment.name == experiment_name,
                Environment.name == environment_name,
                Project.name == project_name
            )
        elif project_name:
            query = query.join(Experiment).join(Experiment.environments).join(Environment.project).filter(
                Project.name == project_name
            )

        runs = query.all()
        result = []

        for run in runs:
            # Get experiment and environment info
            experiment = run.experiment
            env = experiment.environments[0] if experiment.environments else None

            # Calculate duration
            duration_seconds = 0.0
            if run.start_time and run.end_time:
                duration = run.end_time - run.start_time
                duration_seconds = duration.total_seconds()

            # Create experiment dotnotation
            exp_dotnotation = f"{env.project.name}.{experiment.name}" if env else experiment.name

            run_info = RunInfo(
                ulid=run.id,
                experiment_name=exp_dotnotation,
                experiment_ulid=experiment.id,
                environment_name=env.name if env else "",
                environment_ulid=env.id if env else "",
                project_name=env.project.name if env else "",
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