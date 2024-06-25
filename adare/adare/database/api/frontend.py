# external imports
import attrs
import sqlalchemy
import pandas as pd
from pathlib import Path

# internal imports
from adare.database.models.experiment import Project, Environment, Experiment, ExperimentRun, OsInfo, StageInRun, Stage, Event, Status, TestFunction, TestFunctionFile, TestParameter, AbstractTest
from adare.database.api.database import DatabaseApi
import adare.config.database as config_database
from adarelib.exceptions import EnvironmentNotFoundError, ProjectNotFoundError, ExperimentNotFoundError, TestFunctionNotFoundError, ArgumentsError

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

    def __check_environment_exists_by_ulid(self, environment_ulid: str):
        if not self._session.query(Environment).filter_by(ulid=environment_ulid).count():
            raise EnvironmentNotFoundError(log, f'Environment with ulid "{environment_ulid}" not found')

    def __check_experiment_exists_by_projenvexp(self, project_name: str, environment_name: str, experiment_name: str):
        if not self._session.query(Experiment).filter(
                Experiment.name == experiment_name).filter(
                Experiment.environments.any(Environment.name == environment_name)).filter(
                Experiment.environments.any(Environment.project.has(Project.name == project_name))).count():
            raise ExperimentNotFoundError(log, f'Experiment "{experiment_name}" not found in project "{project_name}" and environment "{environment_name}"')

    def __check_experiment_exists_by_ulid(self, experiment_ulid: str):
        if not self._session.query(Experiment).filter_by(ulid=experiment_ulid).count():
            raise ExperimentNotFoundError(log, f'Experiment with ulid "{experiment_ulid}" not found')

    def __enrich_project_data(self, data: pd.DataFrame) -> pd.DataFrame:
        data['object'] = [self._session.query(Project).filter_by(id=id).one() for id in data['id']]
        data['environments'] = [self._session.query(Environment).filter_by(project_id=id).count() for id in data['id']]
        data['environments_names'] = [', '.join([env.name for env in self._session.query(Environment).filter_by(project_id=id)]) for id in data['id']]
        # remove object column
        data = data.drop(columns=['object'])
        return data

    def get_projects(self) -> pd.DataFrame:
        data = pd.read_sql(self._session.query(Project).statement, self._session.bind).map(str)
        data = self.__enrich_project_data(data)
        return data

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

    def __enrich_environment_data(self, data: pd.DataFrame) -> pd.DataFrame:
        data['object'] = [self._session.query(Environment).filter_by(ulid=id).one() for id in data['ulid']]
        data['dotnotation'] = [obj.dotnotation for obj in data['object']]
        data['osinfo'] = [str(obj.osinfo) for obj in data['object']]
        data['osinfo_os'] = [obj.osinfo.os for obj in data['object']]
        data['osinfo_distribution'] = [obj.osinfo.distribution for obj in data['object']]
        data['osinfo_version'] = [obj.osinfo.version for obj in data['object']]
        data['osinfo_language'] = [obj.osinfo.language for obj in data['object']]
        data['osinfo_architecture'] = [obj.osinfo.architecture for obj in data['object']]
        data['project_name'] = [obj.project.name for obj in data['object']]
        data['tags'] = [', '.join([tag.name for tag in obj.tags]) for obj in data['object']]
        # remove object column
        data = data.drop(columns=['object'])
        return data

    def get_environments(self) -> pd.DataFrame:
        data = pd.read_sql(self._session.query(Environment).statement, self._session.bind).map(str)
        data = self.__enrich_environment_data(data)
        return data


    def get_environment(self, project_name: str = None, environment_name: str = None, ulid: str = None) -> pd.DataFrame:
        if ulid:
            self.__check_environment_exists_by_ulid(ulid)
            environment_df = pd.read_sql(self._session.query(Environment).filter_by(ulid=ulid).statement, self._session.bind).map(str)
            self.__enrich_environment_data(environment_df)
        elif project_name and environment_name:
            self.__check_project_exists(project_name)
            self.__check_environment_exists_by_projenv(project_name, environment_name)

            environment_df = pd.read_sql(self._session.query(Environment).filter(
                Environment.name == environment_name).filter(
                Environment.project.has(Project.name == project_name)).statement, self._session.bind)
            # convert all columns to string
            environment_df = environment_df.map(str)
            environment_df = self.__enrich_environment_data(environment_df)
        else:
            raise ArgumentsError(log, 'Either ulid or project_name and environment_name must be provided')
        return environment_df

    def __enrich_experiment_data(self, data: pd.DataFrame) -> pd.DataFrame:
        data['object'] = [self._session.query(Experiment).filter_by(ulid=id).one() for id in data['ulid']]
        data['environments'] = [', '.join([env.name for env in obj.environments]) for obj in data['object']]
        data['environments_names'] = [', '.join([env.name for env in obj.environments]) for obj in data['object']]
        data['tags'] = [', '.join([tag.name for tag in obj.tags]) for obj in data['object']]
        # remove object column
        data = data.drop(columns=['object'])
        return data

    def get_experiments(self):
        data = pd.read_sql(self._session.query(Experiment).statement, self._session.bind).map(str)
        data = self.__enrich_experiment_data(data)
        return data

    def get_experiment(self, project_name: str = None, environment_name: str = None, experiment_name: str = None, ulid: str = None) -> pd.DataFrame:
        if ulid:
            self.__check_experiment_exists_by_ulid(ulid)
            experiment_df = pd.read_sql(self._session.query(Experiment).filter_by(ulid=ulid).statement, self._session.bind)
            # convert all columns to string
            experiment_df = experiment_df.map(str)
            experiment_df = self.__enrich_experiment_data(experiment_df)
        elif project_name and environment_name and experiment_name:
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
            experiment_df = self.__enrich_experiment_data(experiment_df)
        else:
            raise ArgumentsError(log, 'Either ulid or project_name, environment_name and experiment_name must be provided')
        return experiment_df

    def get_experiment_details_by_ulid(self, experiment_ulid: str):
        self.__check_experiment_exists_by_ulid(experiment_ulid)
        experiment_df = pd.read_sql(self._session.query(Experiment).filter(
            Experiment.ulid == experiment_ulid).statement, self._session.bind)
        # convert all columns to string
        experiment_df = experiment_df.map(str)
        # add column environment and project
        experiment_df['environment'] = self._session.query(Environment).filter(
            Environment.experiments.any(Experiment.ulid == experiment_ulid)).one().name
        experiment_df['project'] = self._session.query(Project).filter(
            Project.environments.any(Environment.experiments.any(Experiment.ulid == experiment_ulid))).one().name
        return experiment_df

    def get_experiment_runs(self, experiment_ulid: str) -> pd.DataFrame:
        self.__check_experiment_exists_by_ulid(experiment_ulid)
        # execute query and return result as pandas dataframe excluding the id column
        return pd.read_sql(self._session.query(ExperimentRun).filter_by(experiment_id=experiment_ulid).statement, self._session.bind).map(str)

    def __enrich_run_data(self, data: pd.DataFrame) -> pd.DataFrame:
        data['experiment_name'] = self._session.query(Experiment).filter_by(ulid=data['experiment_id'].values[0]).one().name
        data['environment_name'] = self._session.query(Environment).filter_by(ulid=data['environment_id'].values[0]).one().name
        data['project_name'] = self._session.query(Project).filter(
            Project.environments.any(Environment.ulid == data['environment_id'].values[0])).one().name
        data['object_run'] = self._session.query(ExperimentRun).filter_by(ulid=data['ulid'].values[0]).one()
        data['object_environment'] = self._session.query(Environment).filter_by(ulid=data['environment_id'].values[0]).one()
        # access hybrid properties
        data['duration'] = [obj.duration for obj in data['object_run']]
        data['result_status'] = [obj.result_status for obj in data['object_run']]
        data['status'] = [obj.status for obj in data['object_run']]
        data['experiment_dotnotation'] = [obj.experiment_dotnotation for obj in data['object_run']]
        data['box'] = [obj.vagrantbox for obj in data['object_environment']]
        data['osinfo'] = [str(obj.osinfo) for obj in data['object_environment']]
        # remove object_run column
        data = data.drop(columns=['object_run', 'object_environment'])
        return data

    def get_runs(self, experiment_ulid: str = None, project_name: str = None, environment_name: str = None) -> pd.DataFrame:
        if experiment_ulid:
            return self.get_experiment_runs(experiment_ulid)

        query = self._session.query(ExperimentRun)
        if project_name:
            query = query.filter(ExperimentRun.experiment.has(Experiment.environments.any(Environment.project.has(Project.name == project_name))))
        if environment_name:
            query = query.filter(ExperimentRun.experiment.has(Experiment.environments.any(Environment.name == environment_name)))

        # execute query and return result as pandas dataframe excluding the id column
        data = pd.read_sql(query.statement, self._session.bind).map(str)
        data = self.__enrich_run_data(data)
        return data

    def get_run(self, run_ulid: str) -> pd.DataFrame:
        data = pd.read_sql(self._session.query(ExperimentRun).filter_by(ulid=run_ulid).statement, self._session.bind).map(str)
        data = self.__enrich_run_data(data)
        return data

    def get_run_stages(self, run_ulid: str) -> pd.DataFrame:
        # execute query and return result as pandas dataframe excluding the id column
        data = pd.read_sql(self._session.query(StageInRun).filter_by(run_id=run_ulid).statement, self._session.bind)
        # enrich data by adding stage details (such as name, msg, description)
        stages = pd.read_sql(self._session.query(Stage).statement, self._session.bind)
        # query hybrid property level and add it to the dataframe
        stages['level'] = stages['id'].apply(lambda x: self._session.query(Stage).filter_by(id=x).one().level)
        data = data.merge(stages, left_on='stage_id', right_on='id', suffixes=('', '_stage'))
        return data

    def get_tests(self, run_ulid: str) -> dict:
        tests_data = {}
        test_events = self._session.query(Event).filter_by(experiment_run_id=run_ulid).filter(Event.category == 'test').all()
        for event in test_events:
            if event.abstract_test.name not in tests_data:
                tests_data[event.abstract_test.name] = {
                    'name': event.abstract_test.name,
                    'description': event.abstract_test.description,
                    'testfunction_name': event.abstract_test.testfunction.dotnotation,
                    'testfunction_description': event.abstract_test.testfunction.description,
                    'result_status': event.stage_result if event.result else None,
                    'result_details': event.result.details if event.result else None,
                    'result_status_name': self._session.query(Status).filter_by(id=event.result.status).one().name if event.result else None,
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
                tests_data[event.abstract_test.name]['result_status'] = event.stage_result
                tests_data[event.abstract_test.name]['result_details'] = event.result.details
                tests_data[event.abstract_test.name]['result_status_name'] = self._session.query(Status).filter_by(id=event.result.status).one().name
        return tests_data

    def get_abstract_tests(self, experiment_ulid: str) -> dict:
        experiment = self._session.query(Experiment).filter_by(ulid=experiment_ulid).one()
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
                        'name': parameter.parameter.name,
                        'dtype': parameter.parameter.dtype,
                        'value': parameter.value,
                    }
                    for parameter in test.parameters
                ],
            }
        return tests_data

    def __enrich_testfunction_data(self, data: pd.DataFrame) -> pd.DataFrame:
        data['object'] = [self._session.query(TestFunction).filter_by(id=id).one() for id in data['id']]
        data['testfunction_file'] = [self._session.query(TestFunctionFile).filter_by(id=file_id).one() for file_id in data['file_id']]
        data['dotnotation'] = [obj.dotnotation for obj in data['object']]
        data['num_parameters'] = [obj.num_parameters for obj in data['object']]
        data['file_path'] = [obj.path for obj in data['testfunction_file']]
        data['file_name'] = [obj.name for obj in data['testfunction_file']]
        data['file_sha256'] = [obj.sha256hash for obj in data['testfunction_file']]
        data['file_description'] = [obj.description for obj in data['testfunction_file']]
        # remove object and testfunction_file columns
        data = data.drop(columns=['object', 'testfunction_file'])
        return data

    def get_testfunction_list(self) -> pd.DataFrame:
        data = pd.read_sql(self._session.query(TestFunction).statement, self._session.bind).map(str)
        data = self.__enrich_testfunction_data(data)
        return data

    def get_testfunction(self, testfunction_id: int) -> (pd.DataFrame, pd.DataFrame):
        try:
            testfunction_data = pd.read_sql(self._session.query(TestFunction).filter_by(id=testfunction_id).statement, self._session.bind).map(str)
        except sqlalchemy.orm.exc.NoResultFound:
            raise TestFunctionNotFoundError(log, f'Testfunction with id "{testfunction_id}" not found')
        testfunction_data = self.__enrich_testfunction_data(testfunction_data)
        # get all parameters for the testfunction in a pandas dataframe (test parameters can be in multiple functions)
        testfunction = self._session.query(TestFunction).filter_by(id=testfunction_id).one()
        parameter_ids = [parameter.id for parameter in testfunction.parameters]
        parameter_data = pd.read_sql(self._session.query(TestParameter).filter(TestParameter.id.in_(parameter_ids)).statement, self._session.bind).map(str)
        return testfunction_data, parameter_data

    def testfunction_dotnotation_to_id(self, dotnotation: str) -> int:
        file_name, function_name = dotnotation.split('.')
        file_name_with_extension = file_name + '.py'
        try:
            testfunction_file = self._session.query(TestFunctionFile).filter_by(name=file_name_with_extension).one()
            testfunction = self._session.query(TestFunction).filter_by(file_id=testfunction_file.id, name=function_name).one()
        except sqlalchemy.orm.exc.NoResultFound:
            raise TestFunctionNotFoundError(log, f'Testfunction with dotnotation "{dotnotation}" not found')
        return testfunction.id

