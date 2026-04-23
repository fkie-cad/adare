"""Mixin for project and environment related queries."""

import logging

import pandas as pd

from adare.database.models.global_models import (
    Environment,
    OsInfo,
    Project,
    Vm,
)
from adare.exceptions import (
    ArgumentsError,
    EnvironmentNotFoundError,
)

log = logging.getLogger(__name__)


class ProjectQueryMixin:
    """Mixin providing project and environment query methods."""

    def _enrich_project_data(self, data: pd.DataFrame) -> pd.DataFrame:
        return data

    def get_projects(self) -> pd.DataFrame:
        data = pd.read_sql(self._global_api._session.query(Project).statement, self._global_api._session.bind).map(str)
        return self._enrich_project_data(data)

    def get_project_details(self, project_name: str) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
        from adare.database.models.project_models import Experiment

        self._check_project_exists(project_name)
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

    def _enrich_environment_data(self, data: pd.DataFrame) -> pd.DataFrame:
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
        return data.drop(columns=['object'])

    def get_environments(self) -> pd.DataFrame:
        data = pd.read_sql(self._global_api._session.query(Environment).statement, self._global_api._session.bind).map(str)
        return self._enrich_environment_data(data)

    def get_environment(self, project_name: str = None, environment_name: str = None, ulid: str = None) -> pd.DataFrame:
        if ulid:
            self._check_environment_exists_by_ulid(ulid)
            environment_df = pd.read_sql(self._global_api._session.query(Environment).filter_by(id=ulid).statement, self._global_api._session.bind).map(str)
            self._enrich_environment_data(environment_df)
        elif project_name and environment_name:
            self._check_project_exists(project_name)
            self.__check_environment_exists_by_projenv(project_name, environment_name)

            environment_df = pd.read_sql(self._global_api._session.query(Environment).filter(
                Environment.name == environment_name).filter(
                Environment.project.has(Project.name == project_name)).statement, self._global_api._session.bind)
            # convert all columns to string
            environment_df = environment_df.map(str)
            environment_df = self._enrich_environment_data(environment_df)
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
        return self._enrich_environment_data(environment_df)
