# external imports
# configure logging
import logging
from pathlib import Path

import pandas as pd
import sqlalchemy
from sqlalchemy.orm import joinedload

from adare.database.api.base import GlobalDatabaseApi, ProjectDatabaseApi
from adare.database.models.global_models import (
    Environment,
    OsInfo,
    Project,
    TestFunction,
    TestFunctionFile,
    TestParameter,
    Vm,
)

# internal imports
from adare.database.models.project_models import Event, Experiment, ExperimentRun, Stage, StageInRun, Status
from adare.exceptions import (
    ArgumentsError,
    EnvironmentNotFoundError,
    ExperimentNotFoundError,
    ProjectNotFoundError,
    TestFunctionNotFoundError,
)

log = logging.getLogger(__name__)


class DataRetrievalApi:
    """
    Unified API for retrieving data from both global and project databases.

    This API provides access to:
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

    def __check_project_exists(self, project_name: str):
        if not self._global_api._session.query(Project).filter_by(name=project_name).count():
            raise ProjectNotFoundError(log, f'Project "{project_name}" not found')

    def __check_environment_exists_by_name(self, environment_name: str):
        if not self._global_api._session.query(Environment).filter_by(name=environment_name).count():
            raise EnvironmentNotFoundError(log, f'Environment "{environment_name}" not found')

    def __check_environment_exists_by_ulid(self, environment_ulid: str):
        if not self._global_api._session.query(Environment).filter_by(id=environment_ulid).count():
            raise EnvironmentNotFoundError(log, f'Environment with ulid "{environment_ulid}" not found')

    def __check_experiment_exists_by_projenvexp(self, project_name: str, environment_name: str, experiment_name: str):
        if not self._project_api._session.query(Experiment).filter(
                Experiment.name == experiment_name).count():
            raise ExperimentNotFoundError(log, f'Experiment "{experiment_name}" not found in project "{project_name}" and environment "{environment_name}"')

    def __check_experiment_exists_by_ulid(self, experiment_ulid: str):
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

    def __enrich_project_data(self, data: pd.DataFrame) -> pd.DataFrame:
        # data['object'] = [self._session.query(Project).filter_by(id=id).one() for id in data['id']]
        # remove object column
        # data = data.drop(columns=['object'])
        return data

    def get_projects(self) -> pd.DataFrame:
        data = pd.read_sql(self._global_api._session.query(Project).statement, self._global_api._session.bind).map(str)
        data = self.__enrich_project_data(data)
        return data

    def get_project_details(self, project_name: str) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
        self.__check_project_exists(project_name)
        project_df = pd.read_sql(self._global_api._session.query(Project).filter_by(name=project_name).statement,
                                 self._global_api._session.bind)
        project_df = project_df.map(str)

        environments_df = pd.read_sql(self._global_api._session.query(Environment).filter(
            Environment.project.has(Project.name == project_name)).statement, self._global_api._session.bind)
        # convert all columns to string
        environments_df = environments_df.map(str)

        experiments_df = pd.read_sql(self._project_api._session.query(Experiment).filter(
            Experiment.environments.any(Environment.project.has(Project.name == project_name))).statement,
                                     self._project_api._session.bind)
        # convert all columns to string
        experiments_df = experiments_df.map(str)

        return project_df, environments_df, experiments_df

    def get_environments_by_project(self, project_name: str) -> pd.DataFrame:
        # Environments are now global, return all environments
        # TODO: In the future, we might want to filter by environments used in this project
        return self.get_environments()

    def __enrich_environment_data(self, data: pd.DataFrame) -> pd.DataFrame:
        data['object'] = [self._global_api._session.query(Environment).filter_by(id=id).one() for id in data['id']]
        # Environments are now global, display name is just the environment name
        data['display_name'] = [obj.name for obj in data['object']]
        # Get VM information
        data['vm'] = [self._global_api._session.query(Vm).filter_by(id=obj.vm_id).one() if obj.vm_id else None for obj in data['object']]
        data['vm_name'] = [obj.name if obj else '' for obj in data['vm']]
        data['vm_id'] = [obj.id if obj else '' for obj in data['vm']]
        # Get osinfo from the VM attached to the environment - fix osinfo access
        data['osinfo_object'] = [self._global_api._session.query(OsInfo).filter_by(id=vm.osinfo_id).one() if vm and hasattr(vm, 'osinfo_id') else None for vm in data['vm']]
        data['osinfo'] = [str(osinfo) if osinfo else '' for osinfo in data['osinfo_object']]
        data['osinfo_os'] = [osinfo.os if osinfo else '' for osinfo in data['osinfo_object']]
        data['osinfo_distribution'] = [osinfo.distribution if osinfo else '' for osinfo in data['osinfo_object']]
        data['osinfo_version'] = [osinfo.version if osinfo else '' for osinfo in data['osinfo_object']]
        data['osinfo_language'] = [osinfo.language if osinfo else '' for osinfo in data['osinfo_object']]
        data['osinfo_architecture'] = [osinfo.architecture if osinfo else '' for osinfo in data['osinfo_object']]
        # Environments are now global, no longer have project association
        data['project_name'] = ['Global' for obj in data['object']]
        data['tags'] = [', '.join([tag.name for tag in obj.tags]) for obj in data['object']]
        # Add fields for web status through sync_metadata if available
        data['published'] = [str(obj.sync_metadata.is_synced) if hasattr(obj, 'sync_metadata') and obj.sync_metadata else 'False' for obj in data['object']]
        data['in_request'] = [str(obj.sync_metadata.needs_sync) if hasattr(obj, 'sync_metadata') and obj.sync_metadata else 'False' for obj in data['object']]
        # remove object column
        data = data.drop(columns=['object'])
        return data

    def get_environments(self) -> pd.DataFrame:
        data = pd.read_sql(self._global_api._session.query(Environment).statement, self._global_api._session.bind).map(str)
        data = self.__enrich_environment_data(data)
        return data


    def get_environment(self, project_name: str = None, environment_name: str = None, ulid: str = None) -> pd.DataFrame:
        if ulid:
            self.__check_environment_exists_by_ulid(ulid)
            environment_df = pd.read_sql(self._global_api._session.query(Environment).filter_by(id=ulid).statement, self._global_api._session.bind).map(str)
            self.__enrich_environment_data(environment_df)
        elif project_name and environment_name:
            self.__check_project_exists(project_name)
            self.__check_environment_exists_by_projenv(project_name, environment_name)

            environment_df = pd.read_sql(self._global_api._session.query(Environment).filter(
                Environment.name == environment_name).filter(
                Environment.project.has(Project.name == project_name)).statement, self._global_api._session.bind)
            # convert all columns to string
            environment_df = environment_df.map(str)
            environment_df = self.__enrich_environment_data(environment_df)
        else:
            raise ArgumentsError(log, 'Either ulid or project_name and environment_name must be provided')
        return environment_df

    def get_environment_by_name(self, environment_name: str) -> pd.DataFrame:
        """Get environment by name (environments are now global)."""
        if not self._global_api._session.query(Environment).filter_by(name=environment_name).count():
            raise EnvironmentNotFoundError(log, f'Environment "{environment_name}" not found')

        environment_df = pd.read_sql(self._global_api._session.query(Environment).filter(
            Environment.name == environment_name).statement, self._global_api._session.bind)
        environment_df = environment_df.map(str)
        environment_df = self.__enrich_environment_data(environment_df)
        return environment_df

    def __enrich_experiment_data(self, data: pd.DataFrame) -> pd.DataFrame:
        data['object'] = [self._project_api._session.query(Experiment).filter_by(id=id).one() for id in data['id']]
        # Create dotnotation based on current project (experiments are stored in project-specific databases)
        project_name = self.project_path.name if self.project_path else None
        data['dotnotation'] = [f'{project_name}.{obj.name}' if project_name else obj.name for obj in data['object']]
        # Add smart display name based on current project context
        data['display_name'] = [self._get_smart_display_name(obj, 'experiment') for obj in data['object']]
        data['environments'] = [', '.join([env.name for env in obj.environments if env]) for obj in data['object']]
        data['environments_names'] = [', '.join([env.name for env in obj.environments if env]) for obj in data['object']]
        data['tags'] = [', '.join([tag.name for tag in obj.tags]) for obj in data['object']]
        # Add ulid field (which is same as id for experiments)
        data['ulid'] = data['id']
        # Add fields for web status through sync_metadata if available
        data['published'] = [str(obj.sync_metadata.is_synced) if hasattr(obj, 'sync_metadata') and obj.sync_metadata else 'False' for obj in data['object']]
        data['in_request'] = [str(obj.sync_metadata.needs_sync) if hasattr(obj, 'sync_metadata') and obj.sync_metadata else 'False' for obj in data['object']]
        # remove object column
        data = data.drop(columns=['object'])
        return data

    def get_experiments(self):
        data = pd.read_sql(self._project_api._session.query(Experiment).statement, self._project_api._session.bind).map(str)
        data = self.__enrich_experiment_data(data)
        return data

    def get_experiment(self, project_name: str = None, environment_name: str = None, experiment_name: str = None, ulid: str = None) -> pd.DataFrame:
        if ulid:
            self.__check_experiment_exists_by_ulid(ulid)
            experiment_df = pd.read_sql(self._project_api._session.query(Experiment).filter_by(id=ulid).statement, self._project_api._session.bind)
            # convert all columns to string
            experiment_df = experiment_df.map(str)
            experiment_df = self.__enrich_experiment_data(experiment_df)
        elif project_name and environment_name and experiment_name:
            self.__check_project_exists(project_name)
            self.__check_environment_exists_by_name(environment_name)
            self.__check_experiment_exists_by_projenvexp(project_name, environment_name, experiment_name)

            experiment_df = pd.read_sql(self._project_api._session.query(Experiment).filter(
                Experiment.name == experiment_name).statement,
                                         self._project_api._session.bind)
            # convert all columns to string
            experiment_df = experiment_df.map(str)
            experiment_df = self.__enrich_experiment_data(experiment_df)
        else:
            raise ArgumentsError(log, 'Either ulid or project_name, environment_name and experiment_name must be provided')
        return experiment_df

    def get_experiment_by_name_in_current_project(self, experiment_name: str) -> pd.DataFrame:
        """Get experiment by name within the current project (names are unique per project)."""
        from adare.backend.basics import determine_projectdirectory
        from adare.exceptions import NoProjectFoundError

        # Determine current project
        project_path = determine_projectdirectory(None)
        if not project_path:
            raise NoProjectFoundError(log, message='No project directory found. Please run from within a project directory or provide full dotnotation.')

        project_name = project_path.name
        self.__check_project_exists(project_name)

        # Find the experiment by name within this project database
        experiment_query = self._project_api._session.query(Experiment).filter(
            Experiment.name == experiment_name)

        if not experiment_query.count():
            from adare.exceptions import ExperimentNotFoundError
            raise ExperimentNotFoundError(log, f'Experiment "{experiment_name}" not found in project "{project_name}"')

        experiment_df = pd.read_sql(experiment_query.statement, self._project_api._session.bind)
        experiment_df = experiment_df.map(str)
        experiment_df = self.__enrich_experiment_data(experiment_df)
        return experiment_df

    def get_experiment_details_by_ulid(self, experiment_ulid: str):
        self.__check_experiment_exists_by_ulid(experiment_ulid)
        experiment_df = pd.read_sql(self._project_api._session.query(Experiment).filter(
            Experiment.id == experiment_ulid).statement, self._project_api._session.bind)
        # convert all columns to string
        experiment_df = experiment_df.map(str)
        # add column environment and project
        experiment_df['environment'] = self._global_api._session.query(Environment).filter(
            Environment.experiments.any(Experiment.id == experiment_ulid)).one().name
        experiment_df['project'] = self._global_api._session.query(Project).filter(
            Project.environments.any(Environment.experiments.any(Experiment.id == experiment_ulid))).one().name
        return experiment_df

    def get_experiment_runs(self, experiment_ulid: str) -> pd.DataFrame:
        self.__check_experiment_exists_by_ulid(experiment_ulid)
        # execute query and return result as pandas dataframe excluding the id column
        return pd.read_sql(self._project_api._session.query(ExperimentRun).filter_by(experiment_id=experiment_ulid).statement, self._project_api._session.bind).map(str)

    def __enrich_run_data(self, data: pd.DataFrame) -> pd.DataFrame:
        # Use bulk loading to avoid N+1 queries
        run_ids = data['id'].tolist()
        experiment_ids = data['experiment_id'].tolist()
        environment_ids = data['environment_id'].tolist()

        # Bulk load all required objects with eager loading
        runs_dict = {run.id: run for run in self._project_api._session.query(ExperimentRun).filter(ExperimentRun.id.in_(run_ids)).all()}

        experiments_dict = {exp.id: exp for exp in self._project_api._session.query(Experiment).filter(
            Experiment.id.in_(experiment_ids)).all()}

        environments_dict = {env.id: env for env in self._global_api._session.query(Environment).options(
            joinedload(Environment.vm).joinedload(Vm.osinfo)
        ).filter(Environment.id.in_(environment_ids)).all()}

        # Build result arrays using bulk-loaded data
        experiment_names = []
        environment_names = []
        project_names = []
        object_runs = []
        object_environments = []

        for index, row in data.iterrows():
            experiment = experiments_dict.get(row['experiment_id'])
            environment = environments_dict.get(row['environment_id'])
            run = runs_dict.get(row['id'])

            experiment_names.append(experiment.name if experiment else '')
            environment_names.append(environment.name if environment else '')
            project_names.append(self.project_path.name if self.project_path else '')
            object_runs.append(run)
            object_environments.append(environment)

        data['experiment_name'] = experiment_names
        data['environment_name'] = environment_names
        data['project_name'] = project_names
        data['object_run'] = object_runs
        data['object_environment'] = object_environments

        # access hybrid properties with null checks
        data['duration'] = data['object_run'].apply(lambda obj: obj.duration if obj else None)
        data['result_status'] = data['object_run'].apply(lambda obj: int(obj.result_status) if obj else 0)
        data['status'] = data['object_run'].apply(lambda obj: obj.status if obj else '')
        data['experiment_dotnotation'] = data['object_run'].apply(lambda obj: obj.experiment_dotnotation if obj else 'unknown.unknown.unknown')
        data['vm'] = data['object_environment'].apply(lambda obj: obj.vm if obj else None)
        data['vm_name'] = data['object_environment'].apply(lambda obj: obj.vm.name if obj and obj.vm else '')
        data['osinfo'] = data['object_environment'].apply(lambda obj: str(obj.vm.osinfo) if obj and obj.vm and hasattr(obj.vm, 'osinfo') and obj.vm.osinfo else '')
        # Add missing timestamp fields
        data['timestamp_start'] = data['object_run'].apply(lambda obj: getattr(obj, 'start_time', '') if obj else '')
        data['timestamp_end'] = data['object_run'].apply(lambda obj: getattr(obj, 'end_time', '') if obj else '')
        # Add published field through sync_metadata if available
        data['published'] = data['object_run'].apply(lambda obj: obj.sync_metadata.is_synced if obj and hasattr(obj, 'sync_metadata') and obj.sync_metadata else False)
        # Add fake field
        data['fake'] = data['object_run'].apply(lambda obj: getattr(obj, 'fake', False) if obj else False)
        # remove object_run column
        data = data.drop(columns=['object_run', 'object_environment'])
        return data

    def get_runs(self, experiment_ulid: str = None, project_name: str = None, environment_name: str = None, experiment_name: str = None) -> pd.DataFrame:
        if experiment_ulid:
            return self.get_experiment_runs(experiment_ulid)

        if project_name:
            self.__check_project_exists(project_name)

        query = self._project_api._session.query(ExperimentRun)
        # Note: Project-based filtering removed since environments are now global
        # and experiments are stored per-project

        if environment_name:
            query = query.filter(ExperimentRun.experiment.has(Experiment.environments.any(Environment.name == environment_name)))

        if experiment_name:
            query = query.filter(ExperimentRun.experiment.has(Experiment.name == experiment_name))

        # execute query and return result as pandas dataframe excluding the id column
        data = pd.read_sql(query.statement, self._project_api._session.bind).map(str)
        data = self.__enrich_run_data(data)
        return data

    def get_run(self, run_ulid: str) -> pd.DataFrame:
        data = pd.read_sql(self._project_api._session.query(ExperimentRun).filter_by(id=run_ulid).statement, self._project_api._session.bind).map(str)
        data = self.__enrich_run_data(data)
        return data

    def get_latest_run_in_project(self, project_name: str = None) -> pd.DataFrame:
        """Get the latest run in the current project or specified project."""
        if not project_name:
            from adare.backend.basics import determine_projectdirectory
            from adare.exceptions import NoProjectFoundError
            if project_path := determine_projectdirectory(None):
                project_name = project_path.name
            else:
                raise NoProjectFoundError(log, message='no project directory found and no project specified')

        self.__check_project_exists(project_name)

        # Query the latest run ordered by timestamp
        # Note: Project-based filtering removed since environments are now global
        # and experiments are stored per-project
        query = self._project_api._session.query(ExperimentRun).order_by(ExperimentRun.start_time.desc()).limit(1)

        data = pd.read_sql(query.statement, self._project_api._session.bind).map(str)

        if data.empty:
            from adare.exceptions import RunNotFoundError
            raise RunNotFoundError(log, f'No runs found in project "{project_name}"')

        data = self.__enrich_run_data(data)
        return data

    def get_run_stages(self, run_ulid: str) -> pd.DataFrame:
        # execute query and return result as pandas dataframe excluding the id column
        data = pd.read_sql(self._project_api._session.query(StageInRun).filter_by(run_id=run_ulid).statement, self._project_api._session.bind)
        # enrich data by adding stage details (such as name, msg, description)
        stages = pd.read_sql(self._project_api._session.query(Stage).statement, self._project_api._session.bind)
        # query hybrid property level and add it to the dataframe
        stages['level'] = stages['id'].apply(lambda x: self._project_api._session.query(Stage).filter_by(id=x).one().level)
        data = data.merge(stages, left_on='stage_id', right_on='id', suffixes=('', '_stage'))

        # Convert status_id to proper integer status values for StatusEnum
        from adarelib.constants import StatusEnum

        def get_status_value(status_id):
            """Convert status_id to StatusEnum integer value."""
            if pd.isna(status_id) or not status_id:
                return StatusEnum.PENDING
            try:
                # Query the Status object to get the status name, then convert to StatusEnum
                status_obj = self._project_api._session.query(Status).filter_by(id=status_id).first()
                if status_obj:
                    return StatusEnum.from_string(status_obj.name)
                return StatusEnum.PENDING
            except Exception:
                return StatusEnum.PENDING

        # Apply the conversion and ensure we have a proper 'status' column
        data['status'] = data['status_id'].apply(get_status_value)

        return data

    def get_run_actions(self, run_ulid: str) -> pd.DataFrame:
        """Get all action events for a specific run, including tests.

        Returns a DataFrame with comprehensive event information including:
        - success: Boolean indicating if the event execution succeeded (for green/red dots)
        - error: Error message if execution failed
        - result_status: For test events only - the actual test result (StatusEnum)
        """
        from adare.database.models.project_models import ActionEvent, TestEvent

        # Query action events (non-test actions)
        action_events = self._project_api._session.query(ActionEvent).filter_by(experiment_run_id=run_ulid).filter(
            ActionEvent.category.in_(['action', 'command'])  # Exclude test category from ActionEvent
        ).all()

        # Query test events separately (they are stored in TestEvent model)
        # Include relationships to get hierarchy and result information
        from sqlalchemy.orm import joinedload
        test_events = self._project_api._session.query(TestEvent).options(
            joinedload(TestEvent.result),
            joinedload(TestEvent.abstract_test)
        ).filter_by(experiment_run_id=run_ulid).all()

        def extract_event_data(event, is_test_event=False):
            """Extract data from either ActionEvent or TestEvent"""
            # Extract basic event data and deserialize action_data if available
            action_data = {}
            if hasattr(event, 'action_data') and event.action_data:
                try:
                    import json
                    action_data = json.loads(event.action_data)
                except (json.JSONDecodeError, TypeError):
                    action_data = {}

            # For test events, we need to map their fields to action-like fields
            if is_test_event:
                # Compute display level from parent relationship
                display_level = self._compute_display_level(event)

                # Get execution success from the event itself (now all events have success field)
                execution_success = getattr(event, 'success', None)

                # Get test result status and details
                result_status = None
                result_details = None
                if hasattr(event, 'result') and event.result:
                    result_status = event.result.status if event.result else None
                    result_details = event.result.details if event.result else None

                # Add test result information to action_data
                if not action_data:
                    action_data = {}
                if result_details:
                    action_data['test_result_details'] = result_details

                # Also add test name if available
                if hasattr(event, 'abstract_test') and event.abstract_test:
                    action_data['test_name'] = event.abstract_test.name

                base_data = {
                    'id': event.id,
                    'event_type': 'test_complete',  # Tests are typically stored as complete events
                    'category': 'test',
                    'success': execution_success,  # Boolean for execution success (dot color)
                    'timestamp': event.timestamp,
                    'error': event.error,
                    'action_type': 'test',
                    'action_id': getattr(event, 'action_id', event.id),  # Use event id if no action_id
                    'event_group_id': getattr(event, 'event_group_id', event.id),  # Universal grouping field
                    'event_type_specific': getattr(event, 'event_type_specific', 'test_complete'),
                    'display_level': display_level,
                    'parent_event_id': event.parent_event_id,
                    'data': action_data
                }

                # Add test result status for test events
                if result_status is not None:
                    from adarelib.constants import StatusEnum
                    if hasattr(result_status, 'name'):
                        status_enum = StatusEnum.from_string(result_status.name)
                        base_data['result_status'] = int(status_enum)
                    else:
                        base_data['result_status'] = int(result_status)

                return base_data
            # For action events, get success from the event's success field
            execution_success = getattr(event, 'success', None)

            return {
                'id': event.id,
                'event_type': event.event_type or 'unknown',
                'category': event.category,
                'success': execution_success,  # Boolean for execution success (dot color)
                'timestamp': event.timestamp,
                'error': event.error,
                'action_type': getattr(event, 'action_type', None),
                'action_id': getattr(event, 'action_id', None),
                'event_group_id': getattr(event, 'event_group_id', None),  # Universal grouping field
                'event_type_specific': getattr(event, 'event_type_specific', None),
                'display_level': self._compute_display_level(event),
                'parent_event_id': event.parent_event_id,
                'data': action_data
            }

        actions_data = []

        # Process regular action events
        for event in action_events:
            actions_data.append(extract_event_data(event, is_test_event=False))

        # Process test events
        for event in test_events:
            actions_data.append(extract_event_data(event, is_test_event=True))

        if not actions_data:
            # Return empty DataFrame with proper structure
            return pd.DataFrame(columns=['id', 'event_type', 'category', 'success', 'timestamp', 'error', 'action_type', 'action_id', 'event_group_id', 'event_type_specific', 'display_level', 'data', 'result_status'])

        # Create DataFrame and sort by timestamp to ensure proper chronological order
        df = pd.DataFrame(actions_data)
        if 'timestamp' in df.columns:
            df = df.sort_values('timestamp')

        return df

    def get_tests(self, run_ulid: str) -> dict:
        tests_data = {}
        test_events = self._project_api._session.query(Event).filter_by(experiment_run_id=run_ulid).filter(Event.category == 'test').all()
        for event in test_events:
            if event.abstract_test.name not in tests_data:
                tests_data[event.abstract_test.name] = {
                    'name': event.abstract_test.name,
                    'description': event.abstract_test.description,
                    'testfunction_name': event.abstract_test.testfunction.dotnotation,
                    'testfunction_description': event.abstract_test.testfunction.description,
                    'result_status': int(event.stage_result) if event.result else None,
                    'result_details': event.result.details if event.result else None,
                    'result_status_name': self._project_api._session.query(Status).filter_by(id=event.result.status).one().name if event.result else None,
                }
                parameter_data = [
                    {
                        'name': parameter.parameter.name,
                        'dtype': parameter.parameter.dtype,
                        'value': parameter.value,
                    }
                    for parameter in event.abstract_test.parameters
                ]
                tests_data[event.abstract_test.name]['parameters'] = parameter_data
            else:
                # update results
                tests_data[event.abstract_test.name]['result_status'] = int(event.stage_result)
                tests_data[event.abstract_test.name]['result_details'] = event.result.details
                tests_data[event.abstract_test.name]['result_status_name'] = self._project_api._session.query(Status).filter_by(id=event.result.status).one().name
        return tests_data

    def get_abstract_tests(self, experiment_ulid: str) -> dict:
        experiment = self._project_api._session.query(Experiment).filter_by(id=experiment_ulid).one()
        tests = experiment.abstract_tests
        tests_data = {}
        for test in tests:
            tests_data[test.name] = {
                'name': test.name,
                'description': test.description,
                'testfunction_name': test.testfunction.dotnotation,
                'testfunction_description': test.testfunction.description,
                'parameters': [
                    {
                        'name': parameter.parameter.name if parameter.parameter else parameter.parameter_id,
                        'dtype': parameter.parameter.dtype if parameter.parameter else 'unknown',
                        'value': parameter.value,
                    }
                    for parameter in test.parameters
                    if parameter is not None
                ],
            }
        return tests_data

    def __enrich_testfunction_data(self, data: pd.DataFrame) -> pd.DataFrame:
        data['object'] = [self._global_api._session.query(TestFunction).filter_by(id=id).one() for id in data['id']]
        data['testfunction_file'] = [self._global_api._session.query(TestFunctionFile).filter_by(id=file_id).one() for file_id in data['file_id']]
        data['dotnotation'] = [obj.dotnotation for obj in data['object']]
        # Add smart display name based on current project context
        data['display_name'] = [self._get_smart_display_name(obj, 'testfunction') for obj in data['object']]
        data['num_parameters'] = [obj.num_parameters for obj in data['object']]
        data['file_path'] = [obj.path for obj in data['testfunction_file']]
        data['file_name'] = [obj.name for obj in data['testfunction_file']]
        data['file_sha256'] = [obj.sha256hash for obj in data['testfunction_file']]
        data['file_description'] = [obj.description for obj in data['testfunction_file']]
        # remove object and testfunction_file columns
        data = data.drop(columns=['object', 'testfunction_file'])
        return data

    def get_testfunction_list(self) -> pd.DataFrame:
        data = pd.read_sql(self._global_api._session.query(TestFunction).statement, self._global_api._session.bind).map(str)
        data = self.__enrich_testfunction_data(data)
        return data

    def get_testfunction(self, testfunction_id: int) -> tuple[pd.DataFrame, pd.DataFrame]:
        try:
            testfunction_data = pd.read_sql(self._global_api._session.query(TestFunction).filter_by(id=testfunction_id).statement, self._global_api._session.bind).map(str)
        except sqlalchemy.orm.exc.NoResultFound:
            raise TestFunctionNotFoundError(log, f'Testfunction with id "{testfunction_id}" not found')
        testfunction_data = self.__enrich_testfunction_data(testfunction_data)
        # get all parameters for the testfunction in a pandas dataframe (test parameters can be in multiple functions)
        testfunction = self._global_api._session.query(TestFunction).filter_by(id=testfunction_id).one()
        parameter_ids = [parameter.id for parameter in testfunction.parameters]
        parameter_data = pd.read_sql(self._global_api._session.query(TestParameter).filter(TestParameter.id.in_(parameter_ids)).statement, self._global_api._session.bind).map(str)
        return testfunction_data, parameter_data

    def testfunction_dotnotation_to_id(self, dotnotation: str) -> int:
        from adare.database.api.dotnotation_parser import DotNotationParser

        parser = DotNotationParser()
        parsed = parser.parse_testfunction_dotnotation(dotnotation)

        file_name = parsed['file_name']
        function_name = parsed['function_name']
        project_name = parsed['project_name']

        file_name_with_extension = file_name + '.py'

        try:
            if project_name:
                # 3-part notation: project.file.function
                # Filter by project to ensure we get the right testfunction
                from adare.database.models.global_models import Project
                testfunction_file = self._global_api._session.query(TestFunctionFile).filter(
                    TestFunctionFile.name == file_name_with_extension).filter(
                    TestFunctionFile.projects.any(Project.name == project_name)).one()
            else:
                # 2-part notation: file.function (current project context)
                # Get from current project or first match if no project specified
                testfunction_file = self._global_api._session.query(TestFunctionFile).filter_by(name=file_name_with_extension).one()

            testfunction = self._global_api._session.query(TestFunction).filter_by(file_id=testfunction_file.id, name=function_name).one()
        except sqlalchemy.orm.exc.NoResultFound:
            if project_name:
                raise TestFunctionNotFoundError(log, f'Testfunction with dotnotation "{dotnotation}" not found in project "{project_name}"')
            raise TestFunctionNotFoundError(log, f'Testfunction with dotnotation "{dotnotation}" not found')
        return testfunction.id

