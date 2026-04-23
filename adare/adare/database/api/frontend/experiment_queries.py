"""Mixin for experiment related queries."""

import logging

import pandas as pd

from adare.database.models.global_models import (
    Environment,
    Project,
)
from adare.database.models.project_models import Experiment
from adare.exceptions import (
    ArgumentsError,
    ExperimentNotFoundError,
)

log = logging.getLogger(__name__)


class ExperimentQueryMixin:
    """Mixin providing experiment query methods."""

    def _enrich_experiment_data(self, data: pd.DataFrame) -> pd.DataFrame:
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
        return data.drop(columns=['object'])

    def get_experiments(self):
        data = pd.read_sql(self._project_api._session.query(Experiment).statement, self._project_api._session.bind).map(str)
        return self._enrich_experiment_data(data)

    def get_experiment(self, project_name: str = None, environment_name: str = None, experiment_name: str = None, ulid: str = None) -> pd.DataFrame:
        if ulid:
            self._check_experiment_exists_by_ulid(ulid)
            experiment_df = pd.read_sql(self._project_api._session.query(Experiment).filter_by(id=ulid).statement, self._project_api._session.bind)
            # convert all columns to string
            experiment_df = experiment_df.map(str)
            experiment_df = self._enrich_experiment_data(experiment_df)
        elif project_name and environment_name and experiment_name:
            self._check_project_exists(project_name)
            self._check_environment_exists_by_name(environment_name)
            self._check_experiment_exists_by_projenvexp(project_name, environment_name, experiment_name)

            experiment_df = pd.read_sql(self._project_api._session.query(Experiment).filter(
                Experiment.name == experiment_name).statement,
                                         self._project_api._session.bind)
            # convert all columns to string
            experiment_df = experiment_df.map(str)
            experiment_df = self._enrich_experiment_data(experiment_df)
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
        self._check_project_exists(project_name)

        # Find the experiment by name within this project database
        experiment_query = self._project_api._session.query(Experiment).filter(
            Experiment.name == experiment_name)

        if not experiment_query.count():
            raise ExperimentNotFoundError(log, f'Experiment "{experiment_name}" not found in project "{project_name}"')

        experiment_df = pd.read_sql(experiment_query.statement, self._project_api._session.bind)
        experiment_df = experiment_df.map(str)
        return self._enrich_experiment_data(experiment_df)

    def get_experiment_details_by_ulid(self, experiment_ulid: str):
        self._check_experiment_exists_by_ulid(experiment_ulid)
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
