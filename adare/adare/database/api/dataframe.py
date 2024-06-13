# external imports
import attrs
import sqlalchemy
import pandas as pd
from pathlib import Path

# internal imports
from adare.database.models.experiment import Project, Environment, Experiment, ExperimentRun, OsInfo
from adare.database.api.database import DatabaseApi
import adare.config.database as config_database
from adarelib.exceptions import EnvironmentNotFoundError, ProjectNotFoundError, ExperimentNotFoundError

# configure logging
import logging
log = logging.getLogger(__name__)


class DataRetrievalApi(DatabaseApi):

    def __init__(self, db_path: Path = config_database.get_database_location()):
        super().__init__(db_path)

    def __check_project_exists(self, project_name: str):
        if not self._session.query(Project).filter_by(name=project_name).count():
            raise ProjectNotFoundError(log, f'Project "{project_name}" not found')

    def __check_environment_exists_by_projenv(self, project_name: str, environment_name: str):
        if not self._session.query(Environment).filter(
                Environment.name == environment_name).filter(
                Environment.project.has(Project.name == project_name)).count():
            raise EnvironmentNotFoundError(log, f'Environment "{environment_name}" not found in project "{project_name}"')

    def __check_environment_exists_by_uuid(self, environment_uuid: str):
        if not self._session.query(Environment).filter_by(uuid=environment_uuid).count():
            raise EnvironmentNotFoundError(log, f'Environment with UUID "{environment_uuid}" not found')

    def __check_experiment_exists_by_projenvexp(self, project_name: str, environment_name: str, experiment_name: str):
        if not self._session.query(Experiment).filter(
                Experiment.name == experiment_name).filter(
                Experiment.environments.any(Environment.name == environment_name)).filter(
                Experiment.environments.any(Environment.project.has(Project.name == project_name))).count():
            raise ExperimentNotFoundError(log, f'Experiment "{experiment_name}" not found in project "{project_name}" and environment "{environment_name}"')

    def __check_experiment_exists_by_uuid(self, experiment_uuid: str):
        if not self._session.query(Experiment).filter_by(uuid=experiment_uuid).count():
            raise ExperimentNotFoundError(log, f'Experiment with UUID "{experiment_uuid}" not found')

    def get_projects(self) -> pd.DataFrame:
        # execute query and return result as pandas dataframe excluding the id column
        return pd.read_sql(self._session.query(Project).statement, self._session.bind).map(str)

    def get_project_details(self, project_name: str) -> (pd.DataFrame, pd.DataFrame, pd.DataFrame):
        self.__check_project_exists(project_name)
        project_df = pd.read_sql(self._session.query(Project).filter_by(name=project_name).statement,
                                 self._session.bind)
        project_df = project_df.map(str)

        environments_df = pd.read_sql(self._session.query(Environment).filter(
            Environment.project.has(Project.name == project_name)).statement, self._session.bind)
        # convert all columns to string
        environments_df = environments_df.map(str)

        experiments_df = pd.read_sql(self._session.query(Experiment).filter(
            Experiment.environments.any(Environment.project.has(Project.name == project_name))).statement,
                                     self._session.bind)
        # convert all columns to string
        experiments_df = experiments_df.map(str)

        return project_df, environments_df, experiments_df

    def get_environments_by_project(self, project_name: str) -> pd.DataFrame:
        self.__check_project_exists(project_name)
        # execute query and return result as pandas dataframe excluding the id column
        return pd.read_sql(self._session.query(Environment).filter(
            Environment.project.has(Project.name == project_name)).statement, self._session.bind).map(str)

    def get_environment_details(self, project_name: str, environment_name: str) -> pd.DataFrame:
        self.__check_project_exists(project_name)
        self.__check_environment_exists_by_projenv(project_name, environment_name)

        environment_df = pd.read_sql(self._session.query(Environment).filter(
            Environment.name == environment_name).filter(
            Environment.project.has(Project.name == project_name)).statement, self._session.bind)
        # convert all columns to string
        environment_df = environment_df.map(str)
        return environment_df

    def get_experiments_by_projectenvironment(self, project_name: str, environment_name: str) -> pd.DataFrame:
        self.__check_project_exists(project_name)
        self.__check_environment_exists_by_projenv(project_name, environment_name)
        # execute query and return result as pandas dataframe excluding the id column
        return pd.read_sql(self._session.query(Experiment).filter(
            Experiment.environments.any(Environment.name == environment_name)).filter(
            Experiment.environments.any(Environment.project.has(Project.name == project_name))).statement,
                          self._session.bind).map(str)

    def get_experiments_by_environmentuuid(self, environment_uuid: str) -> pd.DataFrame:
        self.__check_environment_exists_by_uuid(environment_uuid)
        # execute query and return result as pandas dataframe excluding the id column
        return pd.read_sql(self._session.query(Experiment).filter(
            Experiment.environments.any(Environment.uuid == environment_uuid)).statement,
                          self._session.bind).map(str)

    def get_experiment_details(self, project_name: str, environment_name: str, experiment_name: str) -> pd.DataFrame:
        self.__check_project_exists(project_name)
        self.__check_environment_exists_by_projenv(project_name, environment_name)
        self.__check_experiment_exists_by_projenvexp(project_name, environment_name, experiment_name)

        experiment_df = pd.read_sql(self._session.query(Experiment).filter(
            Experiment.name == experiment_name).filter(
            Experiment.environments.any(Environment.name == environment_name)).filter(
            Experiment.environments.any(Environment.project.has(Project.name == project_name))).statement,
                                     self._session.bind)
        # convert all columns to string
        experiment_df = experiment_df.map(str)
        # add column environment and project
        experiment_df['environment'] = environment_name
        experiment_df['project'] = project_name

        return experiment_df

    def get_experiment_details_by_uuid(self, experiment_uuid: str):
        self.__check_experiment_exists_by_uuid(experiment_uuid)
        experiment_df = pd.read_sql(self._session.query(Experiment).filter(
            Experiment.uuid == experiment_uuid).statement, self._session.bind)
        # convert all columns to string
        experiment_df = experiment_df.map(str)
        # add column environment and project
        experiment_df['environment'] = self._session.query(Environment).filter(
            Environment.experiments.any(Experiment.uuid == experiment_uuid)).one().name
        experiment_df['project'] = self._session.query(Project).filter(
            Project.environments.any(Environment.experiments.any(Experiment.uuid == experiment_uuid))).one().name
        return experiment_df

    def get_experiment_runs(self, experiment_uuid: str) -> pd.DataFrame:
        self.__check_experiment_exists_by_uuid(experiment_uuid)
        # execute query and return result as pandas dataframe excluding the id column
        return pd.read_sql(self._session.query(ExperimentRun).filter_by(experiment_id=experiment_uuid).statement, self._session.bind).map(str)

    def get_runs(self, experiment_uuid: str = None, project_name: str = None, environment_name: str = None) -> pd.DataFrame:
        if experiment_uuid:
            return self.get_experiment_runs(experiment_uuid)

        query = self._session.query(ExperimentRun)
        if project_name:
            query = query.filter(ExperimentRun.experiment.has(Experiment.environments.any(Environment.project.has(Project.name == project_name))))
        if environment_name:
            query = query.filter(ExperimentRun.experiment.has(Experiment.environments.any(Environment.name == environment_name)))

        # execute query and return result as pandas dataframe excluding the id column
        return pd.read_sql(query.statement, self._session.bind).map(str)

    def get_run_details(self, run_uuid: str) -> pd.DataFrame:
        # execute query and return result as pandas dataframe excluding the id column
        #return pd.read_sql(self._session.query(ExperimentRun).filter_by(uuid=run_uuid).statement, self._session.bind).map(str)
        return query_to_dataframe(self._session, self._session.query(ExperimentRun).filter_by(uuid=run_uuid))
