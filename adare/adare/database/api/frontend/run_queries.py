"""Mixin for experiment run related queries."""

import logging

import pandas as pd
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import joinedload

from adare.database.models.global_models import (
    Environment,
    Vm,
)
from adare.database.models.project_models import (
    Experiment,
    ExperimentRun,
    Stage,
    StageInRun,
    Status,
)

log = logging.getLogger(__name__)


class RunQueryMixin:
    """Mixin providing experiment run query methods."""

    def get_experiment_runs(self, experiment_ulid: str) -> pd.DataFrame:
        self._check_experiment_exists_by_ulid(experiment_ulid)
        # execute query and return result as pandas dataframe excluding the id column
        return pd.read_sql(self._project_api._session.query(ExperimentRun).filter_by(experiment_id=experiment_ulid).statement, self._project_api._session.bind).map(str)

    def _enrich_run_data(self, data: pd.DataFrame) -> pd.DataFrame:
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

        for _index, row in data.iterrows():
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
        return data.drop(columns=['object_run', 'object_environment'])

    def get_runs(self, experiment_ulid: str = None, project_name: str = None, environment_name: str = None, experiment_name: str = None) -> pd.DataFrame:
        if experiment_ulid:
            return self.get_experiment_runs(experiment_ulid)

        if project_name:
            self._check_project_exists(project_name)

        query = self._project_api._session.query(ExperimentRun)
        # Note: Project-based filtering removed since environments are now global
        # and experiments are stored per-project

        if environment_name:
            query = query.filter(ExperimentRun.experiment.has(Experiment.environments.any(Environment.name == environment_name)))

        if experiment_name:
            query = query.filter(ExperimentRun.experiment.has(Experiment.name == experiment_name))

        # execute query and return result as pandas dataframe excluding the id column
        data = pd.read_sql(query.statement, self._project_api._session.bind).map(str)
        return self._enrich_run_data(data)

    def get_run(self, run_ulid: str) -> pd.DataFrame:
        data = pd.read_sql(self._project_api._session.query(ExperimentRun).filter_by(id=run_ulid).statement, self._project_api._session.bind).map(str)
        return self._enrich_run_data(data)

    def get_latest_run_in_project(self, project_name: str = None) -> pd.DataFrame:
        """Get the latest run in the current project or specified project."""
        if not project_name:
            from adare.backend.basics import determine_projectdirectory
            from adare.exceptions import NoProjectFoundError
            if project_path := determine_projectdirectory(None):
                project_name = project_path.name
            else:
                raise NoProjectFoundError(log, message='no project directory found and no project specified')

        self._check_project_exists(project_name)

        # Query the latest run ordered by timestamp
        # Note: Project-based filtering removed since environments are now global
        # and experiments are stored per-project
        query = self._project_api._session.query(ExperimentRun).order_by(ExperimentRun.start_time.desc()).limit(1)

        data = pd.read_sql(query.statement, self._project_api._session.bind).map(str)

        if data.empty:
            from adare.exceptions import RunNotFoundError
            raise RunNotFoundError(log, f'No runs found in project "{project_name}"')

        return self._enrich_run_data(data)

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
            except (SQLAlchemyError, ValueError, KeyError):
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
        from sqlalchemy.orm import joinedload as jl
        test_events = self._project_api._session.query(TestEvent).options(
            jl(TestEvent.result),
            jl(TestEvent.abstract_test)
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
                return self._extract_test_event_data(event, action_data)

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

    def _extract_test_event_data(self, event, action_data):
        """Extract structured data from a test event."""
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
