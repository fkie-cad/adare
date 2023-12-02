# external imports
import sqlalchemy
from pathlib import Path
from datetime import datetime
import json

# internal imports
from adare.helperFunctions.pyfileanalyze import PyModuleAnalyzer
from adare.helperFunctions.hash import hash_file_sha256, combine_hashes, hash_dict_sha256
from adare.config.configdirectory import PROG_PARSEANDTEST_DIR
import adare.config.database as config_database
from adare.database.models.experiments import PostSetupInstallation, Scenario, PublishStatus, TestParameter, TestParameterEntry, Experiment, ExperimentRun, Status, TestFunction, AbstractTest, Test, Tool, Result, OsInfo, LogFile, Request, Environment, Project, Base as ExperimentsBase
from adare.database.api.database import DatabaseApi
from adare.testsetfile.parser import parse_testsetfile
from adare.testsetfile.fileformat import FTestsetFile, FTest, FToolTest

# configure logging
import logging
log = logging.getLogger(__name__)


class ExperimentApi(DatabaseApi):
    testfunction_locations: dict[str, Path] = {
        'default': PROG_PARSEANDTEST_DIR/'src'/'parseandtest'/'testfunctions',
    }
    def __init__(self, db_path: Path = config_database.get_database_location()):
        super().__init__(db_path)
        ExperimentsBase.metadata.create_all(self.engine)

    def __enter__(self):
        super().__enter__()
        for status in config_database.DB_STATUS_LIST:
            self.add_status(status)
        for publishstatus in config_database.DB_PUBLISH_STATUS_LIST:
            self.add_publishstatus(publishstatus)
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        super().__exit__(exc_type, exc_val, exc_tb)


    def add_testfunction_location(self, name:str, location:Path):
        """
            Adds a location to the list of locations where testfunctions are searched for.
        """
        self.testfunction_locations[name] = location

    def get_experiment_in_env(self,project_name: str, experiment_name: str, env_name: str):
        """
            Returns the experiment with the given name in the given environment.
        """
        experiment = self._session.query(Experiment).filter_by(name=experiment_name).join(Experiment.environment).filter_by(name=env_name).join(Environment.project).filter_by(name=project_name).first()
        return experiment

    def get_all_experiments(self):
        """
            Returns all experiments in the database.
        """
        experiments = self._session.query(Experiment).all()
        return experiments

    def get_all_experiment_runs(self):
        """
            Returns all experiment runs in the database.
            (sorted by timestamp_start descending)
        """
        experiment_runs = self._session.query(ExperimentRun).order_by(sqlalchemy.desc(ExperimentRun.timestamp_start)).all()
        return experiment_runs

    def get_experiment_runs_by_experiment_uuid(self, experiment_uuid: str):
        """
            Returns all experiment runs for a given experiment uuid.
        """
        experiment_runs = self._session.query(ExperimentRun).filter_by(experiment_id=experiment_uuid).order_by(sqlalchemy.desc(ExperimentRun.timestamp_start)).all()
        return experiment_runs

    def get_experiment_by_uuid(self, uuid: str):
        """
            Returns the experiment with the given id.
        """
        experiment = self._session.query(Experiment).filter_by(uuid=uuid).first()
        return experiment

    def get_experimentrun_by_uuid(self, uuid: str):
        """
            Returns the experiment run with the given id.
        """
        experiment_run = self._session.query(ExperimentRun).filter_by(uuid=uuid).first()
        return experiment_run

    def get_experiment_run_counts_by_status(self, experiment_uuid: str):
        """
            Returns the number of experiment runs for each status.
        """
        experiment_runs = self._session.query(ExperimentRun).filter_by(experiment_id=experiment_uuid).all()
        status_counts = {}
        for status in self._session.query(Status).all():
            status_counts[status.name] = 0
        for experiment_run in experiment_runs:
            status_counts[experiment_run.status.name] += 1
        return status_counts

    def get_logfile_by_uuid(self, uuid: str):
        """
            Returns the logfile with the given id.
        """
        logfile = self._session.query(LogFile).filter_by(uuid=uuid).first()
        return logfile

    def set_experiment_publish_status(self, experiment_uuid: str, publish_status: str):
        """
            Sets the publish status of an experiment.
        """
        experiment = self._session.query(Experiment).filter_by(uuid=experiment_uuid).first()
        if not experiment:
            log.error(f'Experiment with uuid {experiment_uuid} not found in database')
            return
        publish_status_obj = self._session.query(PublishStatus).filter_by(name=publish_status).first()
        if not publish_status_obj:
            log.error(f'Publish status {publish_status} not found in database')
            return
        experiment.publish_status = publish_status_obj
        self._session.commit()

    def add_postsetup_installation(self, environment: Environment, name:str, description: str, command: str):
        """
            Adds the postsetup installations to the database.
        """
        obj = PostSetupInstallation(
            name=name,
            description=description,
            command=command,
        )
        environment.postsetupinstallations.append(obj)
        self._session.add(obj)
        self._session.commit()

    def update_testfunctions(self):
        """
            Updates the database with testfunction found in python files in various specified locations.
        """

        for directory in self.testfunction_locations.values():
            for path in directory.rglob('*.py'):
                if not path.name.startswith('__') and not path.name.endswith('.pyc'):
                    module_analyzer = PyModuleAnalyzer(path)
                    for t_func_class in module_analyzer.get_classes(parent='BasicTest'):
                        if t_func_class.has_attribute('params'):
                            parameter_attr_type = t_func_class.get_attribute('params').get_type()
                            matching_parameter_class = module_analyzer.get_class(parameter_attr_type)
                            db_parameter_objects = dict()
                            if matching_parameter_class:
                                attribute_dict = matching_parameter_class.get_attributes_as_dict()
                                # add parameters to database
                                for attr in attribute_dict.values():
                                    testparameter_query = self._session.query(TestParameter).filter_by(name=attr['name'])
                                    db_testparameter_objects = list(testparameter_query)
                                    if not db_testparameter_objects:
                                        db_testparameter_obj = TestParameter(name=attr['name'], dtype=attr['type'])
                                        self._session.add(db_testparameter_obj)
                                        self._session.commit()
                                    else:
                                        db_testparameter_obj = db_testparameter_objects[0]
                                    db_parameter_objects[attr['name']] = db_testparameter_obj

                                # add testfunction to db
                                test_name = t_func_class.get_attribute('testname').get_value()
                                test_description = t_func_class.get_attribute('testdescription').get_value()
                                testfunction_obj = self._session.query(TestFunction).filter_by(type=test_name).first()
                                if testfunction_obj:
                                    if testfunction_obj.name != test_name:
                                        testfunction_obj.name = test_name
                                        log.info(f'test function name of test function class {t_func_class.name} changed to {test_name}')
                                    if testfunction_obj.description != test_description:
                                        testfunction_obj.description = test_description
                                        log.info(
                                            f'test description of test function class {t_func_class.name} changed to {test_description}')
                                else:
                                    testfunction_obj = TestFunction(type=test_name,
                                                                       name=t_func_class.name,
                                                                       description=test_description)

                                # add parameter to testfunction in database
                                for db_para_obj in db_parameter_objects.values():
                                    testfunction_obj.possible_parameters.append(db_para_obj)

                                self._session.add(testfunction_obj)
                                self._session.commit()

                            else:
                                log.warning(f'parameter class for testfunction class {t_func_class.name} is missing')
                        else:
                            log.warning(f'testfunction class {t_func_class.name} is missing the mandatory params attribute')

    def add_status(self, status: str):
        """
            adds a status to the database.
        """
        status_obj = self._session.query(Status).filter_by(name=status).first()
        if not status_obj:
            status = Status(name=status)
            self._session.add(status)
            log.debug(f"Added status {status} to database")

    def add_publishstatus(self, publishstatus: str):
        """
            adds a publishstatus to the database.
        """
        publishstatus_obj = self._session.query(PublishStatus).filter_by(name=publishstatus).first()
        if not publishstatus_obj:
            publishstatus = PublishStatus(name=publishstatus)
            self._session.add(publishstatus)
            log.debug(f"Added publishstatus {publishstatus} to database")
        self._session.commit()

    def add_testparameter(self, name: str, dtype: str):
        """
            adds a testparameter to the database.
        """
        testparameter = TestParameter(name=name, dtype=dtype)
        self._session.add(testparameter)
        self._session.commit()
        return testparameter

    def add_testparameterentry(self, parameter: TestParameter, value: str):
        """
            adds a testparameterentry to the database.
        """
        testparameterentry = TestParameterEntry(parameter=parameter, value=value)
        self._session.add(testparameterentry)
        self._session.commit()

    def __add_test(self, abstract_test: AbstractTest, test_result: dict):
        """
            adds a test to the database
        """
        # get or create Result object (for the test result)
        status_name = test_result['result']['status']
        status_obj = self._session.query(Status).filter_by(name=status_name).first()
        if not status_obj:
            log.fatal(f'status {status_name} does not exist')
            return
        result_obj = self._session.query(Result).filter_by(status=status_obj).first()
        if not result_obj:
            # todo: clarify how to handle details (either keep it string only of create additional database entries)
            result_details = ''
            if 'details' in test_result['result'].keys():
                result_details = '||'.join(test_result['result']['details'])
            result_obj = Result(status=status_obj, details=result_details)
            self._session.add(result_obj)
            self._session.commit()

        # get or create Test object
        test_obj = self._session.query(Test).filter_by(abstracttest=abstract_test, result=result_obj).first()
        if not test_obj:
            test_obj = Test(abstracttest=abstract_test, result=result_obj)
            self._session.add(test_obj)
            self._session.commit()
        return test_obj


    def __get_abstract_test(self, test: FTest, tool: Tool = None) -> AbstractTest or None:
        """
        get/creates the abstract test from the data parsed from the testset file.
        :param test:
        :return:
        """
        testfunction = self._session.query(TestFunction).filter_by(type=test.type).first()
        if not testfunction:
            log.error(f'testfunction {test.type} does not exist')
            return

        parameter_entries = []
        for p_key, p_val in test.params.items():
            parameter = self._session.query(TestParameter).filter_by(name=p_key).first()
            # check if TestParameterEntry already exists
            test_parameter_entry_q = self._session.query(TestParameterEntry).filter_by(parameter=parameter, value=str(p_val))
            test_parameter_entry_obj = test_parameter_entry_q.first()
            if not test_parameter_entry_obj:
                # create an TestParameterEntry object for the parameter
                test_parameter_entry_obj = TestParameterEntry(parameter=parameter, value=str(p_val))
                self._session.add(test_parameter_entry_obj)
                self._session.commit()
            parameter_entries.append(test_parameter_entry_obj)

        # check if abstract test already exists (todo: make this more efficient by using filter instead of filtering in python)
        abstract_test_obj = None
        if tool:
            abstract_test_q = self._session.query(AbstractTest).filter_by(name=test.name, description=test.description, testfunction=testfunction, tool=tool)
        else:
            abstract_test_q = self._session.query(AbstractTest).filter_by(name=test.name, description=test.description, testfunction=testfunction)
        # check if all parameter entries are in the abstract test and vice versa by their ids
        parameter_entry_ids_data = [p.id for p in parameter_entries]
        for abstract_test in abstract_test_q.all():
            # check if all parameter entries are in the abstract test
            parameter_entry_ids_abstract_test = [p.id for p in abstract_test.parameters]
            if set(parameter_entry_ids_data) == set(parameter_entry_ids_abstract_test):
                abstract_test_obj = abstract_test

        # if abstract test does not exist, create it
        if not abstract_test_obj:
            abstract_test_obj = AbstractTest(name=test.name, description=test.description, testfunction=testfunction, tool=tool)

            # add parameter entries to abstract test
            for parameter_entry in parameter_entries:
                # add parameter entry to abstract test
                abstract_test_obj.parameters.append(parameter_entry)

            self._session.add(abstract_test_obj)
            self._session.commit()

        return abstract_test_obj

    def __get_result_entry_by_name(self, data: list, name: str) -> dict:
        if not data:
            return {}
        for result_entry in data:
            if result_entry['name'] == name:
                return result_entry
        return {}


    def __add_logfile(self, name:str , path: str):
        logfile = LogFile(name=name, path=path)
        self._session.add(logfile)
        self._session.commit()
        return logfile


    def __get_tool(self, name: str, command: str):
        """
            Get/Creates the tool from the tool data.
        """
        tool = self._session.query(Tool).filter_by(name=name, command=command).first()
        if not tool:
            tool = Tool(name=name, command=command)
            self._session.add(tool)
            self._session.commit()
        return tool


    def __get_abstracttests_from_testsetfile(self, testset: FTestsetFile) -> list[AbstractTest]:
        """
            Get/Creates the tests from the testset file.
        """
        abstract_tests = []
        for test in testset.tests:
            if type(test) == FTest:
                abstract_test = self.__get_abstract_test(test)
                abstract_tests.append(abstract_test)
            elif type(test) == FToolTest:
                tool = self.__get_tool(test.tool, test.command)
                for inner_test in test.tests:
                    abstract_test = self.__get_abstract_test(inner_test, tool=tool)
                    abstract_tests.append(abstract_test)
            else:
                log.error(f'unknown test type {type(test)}')

        return abstract_tests


    def get_experiment(self, os_info: OsInfo, action_file: Path, testset_file: Path, environment: Environment) -> (Experiment, bool):
        """
        gets/creates an experiment to the database.
        :param os_info: dict with os info
        :param action_file: path to action file
        :param testset_file: path to testset file
        :param environment: environment object
        :return: (experiment, bool) where bool is true if the experiment already existed
        """
        # generate experiment hash
        sha256_action_file = hash_file_sha256(action_file)
        sha256_testset_file = hash_file_sha256(testset_file)
        sha256_osinfo = hash_dict_sha256(os_info)
        experiment_hash = combine_hashes([sha256_osinfo, sha256_action_file, sha256_testset_file])

        # check if experiment exists
        experiment_q = self._session.query(Experiment).filter_by(experiment_hash=experiment_hash, os_info=os_info, environment=environment)
        if experiment_q.count() > 0:
            experiment = experiment_q.first()
            return experiment, True

        testset: FTestsetFile = parse_testsetfile(testset_file)

        # create abstract test objects from test data
        abstract_test_objects: list = self.__get_abstracttests_from_testsetfile(testset)

        # if experiment does not exist, create it
        publish_status = self._session.query(PublishStatus).filter_by(name='unknown').first()
        if not publish_status:
            log.error(f'publish status unknown not found in database')
            return
        experiment = Experiment(
            name=testset.name,
            description=testset.description,
            os_info=os_info,
            action_file=action_file.as_posix(),
            testset_file=testset_file.as_posix(),
            experiment_hash=experiment_hash,
            publish_status=publish_status,
            environment=environment,
        )
        for obj in abstract_test_objects:
            if obj:
                experiment.abstract_tests.append(obj)
        self._session.add(experiment)
        self._session.commit()

        log.debug(f'added experiment {experiment.uuid} to database')

        return experiment, False


    def get_scenario_by_uuid(self, uuid: str):
        """
            Returns the scenario with the given id.
        """
        scenario = self._session.query(Scenario).filter_by(uuid=uuid).first()
        return scenario

    def create_experiment_run(self, experiment: Experiment, timestamp_start: datetime, logfile_data: dict):
        """
        creates an experiment run for the given experiment.
        :param experiment:
        :param logfile_data:
        :param timestamp_start:
        :return:
        """
        # get status
        status_not_reached = self._session.query(Status).filter_by(name='not reached').first()
        status_in_progress = self._session.query(Status).filter_by(name='in progress').first()
        pulbish_status_unknown = self._session.query(PublishStatus).filter_by(name='unknown').first()

        run = ExperimentRun(
            experiment=experiment,
            timestamp_start=timestamp_start,
            status=status_in_progress,
            status_action=status_not_reached,
            status_test=status_not_reached,
            status_vagrant=status_in_progress,
            publish_status=pulbish_status_unknown,
            logfile_vagrant=self.__add_logfile('vagrant', logfile_data['vagrant']),
            logfile_action=self.__add_logfile('action', logfile_data['action']),
            logfile_test=self.__add_logfile('test', logfile_data['test']),
            logfile_postsetup_installations=self.__add_logfile('postsetup installations', logfile_data['postsetup_installations']),
            logfile_installed_packages=self.__add_logfile('installed packages', logfile_data['installed_packages']),
            logfile_run_experiment=self.__add_logfile('experiment', logfile_data['run_experiment']),
            tests=[],
        )

        self._session.add(run)
        self._session.commit()

        return run

    def get_experiment_runs(self, project_name: str, env_name: str, experiment_name: str):
        """
            Returns all experiment runs for a given project, environment and experiment.
        """
        # get environment
        environment = self._session.query(Environment).filter_by(name=env_name).join(Environment.project).filter_by(name=project_name).first()
        if not environment:
            log.error(f'environment {env_name} not found in database')
            return
        # get experiment
        experiment = self._session.query(Experiment).filter_by(name=experiment_name, environment=environment).first()
        if not experiment:
            log.error(f'experiment {experiment_name} not found in database')
            return
        # get experiment runs
        return experiment.runs


    def get_experiment_run_by_uuid(self, uuid: str):
        """
            Returns the experiment run with the given id.
        """
        experiment_run = self._session.query(ExperimentRun).filter_by(uuid=uuid).first()
        return experiment_run


    def update_experiment_run(self, uuid: str, result_data: list, status_data: dict, timestamp_end: datetime):
        # get experiment run by uuid
        experiment_run = self._session.query(ExperimentRun).filter_by(uuid=uuid).first()

        # generate test results
        if result_data:
            for abs_test in experiment_run.experiment.abstract_tests:
                result_dict = self.__get_result_entry_by_name(result_data, abs_test.name)
                if not result_dict:
                    log.error(f'no result found for test {abs_test.name}')
                    continue

                status = self._session.query(Status).filter_by(name=result_dict['result']['status']).first()
                if not status:
                    log.error(f'status {result_dict["result"]["status"]} not found')
                    continue

                result = Result(
                    status=status,
                    details=json.dumps(result_dict['details']),
                )

                new_test = Test(
                    abstracttest=abs_test,
                    result=result,
                )
                experiment_run.tests.append(new_test)

        # update experiment run
        experiment_run.timestamp_end = timestamp_end

        # update status
        experiment_run.status = self._session.query(Status).filter_by(name=status_data['total']).first()
        experiment_run.status_vagrant = self._session.query(Status).filter_by(name=status_data['vagrant']).first()
        experiment_run.status_action = self._session.query(Status).filter_by(name=status_data['action']).first()
        experiment_run.status_test = self._session.query(Status).filter_by(name=status_data['test']).first()

        # commit changes
        self._session.commit()
