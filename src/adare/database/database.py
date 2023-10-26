import sqlalchemy
from sqlalchemy.orm import sessionmaker
from datetime import datetime
import adare.config.database as config_database
from adare.database.models.login import UserSession, Base as LoginBase
from adare.database.models.experiments import Scenario, PublishStatus, TestParameter, TestParameterEntry, Experiment, ExperimentRun, Status, TestFunction, AbstractTest, Test, Tool, Result, OsInfo, LogFile, Request, Base as ExperimentsBase
import adare.config as config
from pathlib import Path
from adare.helperFunctions.dict.dict import get_value_if_missing_key
from adare.helperFunctions.pyfileanalyze import PyModuleAnalyzer
from adare.helperFunctions.hash import hash_file_sha256, combine_hashes

# configure logging
import logging
log = logging.getLogger(__name__)

class ProgramDatabase:
    _session: sqlalchemy.orm.Session

    def __init__(self, db_path: Path = config_database.get_database_location()):
        self.engine = sqlalchemy.create_engine('sqlite:///' + db_path.as_posix())
        self.conn = self.engine.connect()
        self.metadata = sqlalchemy.MetaData()
        self.session_starter = sessionmaker(autoflush=False)
        self.session_starter.configure(bind=self.engine)
        LoginBase.metadata.create_all(self.engine)
        ExperimentsBase.metadata.create_all(self.engine)


    def __enter__(self):
        self.__start_sqlalchemy_session()
        if not self._session:
            log.error(f'Could not start sqlalchemy session.')
            return None
        log.info(f'Started sqlalchemy session.')
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if self._session:
            self.__stop_sqlalchemy_session()
            log.info(f'Stopped sqlalchemy session.')
        else:
            log.error(f'Could not stop sqlalchemy session, because session was not created.')

    def __start_sqlalchemy_session(self):
        self._session = self.session_starter()
        self._session.begin()

    def __stop_sqlalchemy_session(self):
        self._session.commit()
        self._session.close()


class ExperimentApi(ProgramDatabase):
    testfunction_locations: dict = {
        'default': config.PCK_PARSEANDTEST_TESTFUNCTION_DIRS
    }
    def __init__(self, db_path: Path = config_database.get_database_location()):
        super().__init__(db_path)
        ExperimentsBase.metadata.create_all(self.engine)

    def __enter__(self):
        super().__enter__()
        for status in config_database.DB_STATUS_LIST:
            self.add_status(status)
            log.info(f'Added preconfigured status ({status}) to database.')
        for publishstatus in config_database.DB_PUBLISH_STATUS_LIST:
            self.add_publishstatus(publishstatus)
            log.info(f'Added preconfigured publishstatus ({publishstatus}) to database.')
        self.update_testfunctions()
        log.info(f'Updated testfunctions in database by analyzing provided python files.')
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        super().__exit__(exc_type, exc_val, exc_tb)


    def add_testfunction_location(self, name:str, location:str):
        """
            Adds a location to the list of locations where testfunctions are searched for.
        """
        if name in self.testfunction_locations:
            self.testfunction_locations[name].append(location)
        else:
            self.testfunction_locations[name] = [location]

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

    def update_testfunctions(self):
        """
            Updates the database with testfunction found in python files in various specified locations.
        """
        locations = []
        for location in self.testfunction_locations.values():
            locations.extend(location)

        for directory in locations:
            for path in Path(directory).rglob('*.py'):
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
                            testfunction_query = self._session.query(TestFunction).filter_by(type=t_func_class.name)
                            db_testfunction_objects = list(testfunction_query)
                            if db_testfunction_objects:
                                db_testfunction_obj = db_testfunction_objects[0]
                                if db_testfunction_obj.name != test_name:
                                    db_testfunction_obj.name = test_name
                                    log.info(f'test function name of test function class {t_func_class.name} changed to {test_name}')
                                if db_testfunction_obj.description != test_description:
                                    db_testfunction_obj.description = test_description
                                    log.info(
                                        f'test description of test function class {t_func_class.name} changed to {test_description}')
                            else:
                                db_testfunction_obj = TestFunction(type=test_name,
                                                                   name=t_func_class.name,
                                                                   description=test_description)

                            # add parameter to testfunction in database
                            for db_para_obj in db_parameter_objects.values():
                                db_testfunction_obj.possible_parameters.append(db_para_obj)

                            self._session.add(db_testfunction_obj)
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
        if status_obj:
            log.info(f"Status {status} already exists in database")
        else:
            status = Status(name=status)
            self._session.add(status)
            log.debug(f"Added status {status} to database")
        self._session.commit()

    def add_publishstatus(self, publishstatus: str):
        """
            adds a publishstatus to the database.
        """
        publishstatus_obj = self._session.query(PublishStatus).filter_by(name=publishstatus).first()
        if publishstatus_obj:
            log.info(f"Publishstatus {publishstatus} already exists in database")
        else:
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


    def __get_abstract_test(self, test_data: dict, tool: Tool = None):
        """
        adds an abstract test to the database
        :param test_data: dict containing the abstract test data
        :return:
        """
        name = test_data['name']
        description = test_data['description']
        testfunction = self._session.query(TestFunction).filter_by(type=test_data['type']).first()
        if not testfunction:
            log.error(f'testfunction {test_data["type"]} does not exist')
            return

        parameter_entries = []
        for p_key, p_val in test_data['params'].items():
            # get the parameter from the database
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
            abstract_test_q = self._session.query(AbstractTest).filter_by(name=name, description=description, testfunction=testfunction, tool=tool)
        else:
            abstract_test_q = self._session.query(AbstractTest).filter_by(name=name, description=description, testfunction=testfunction)
        # check if all parameter entries are in the abstract test and vice versa by their ids
        parameter_entry_ids_data = [p.id for p in parameter_entries]
        for abstract_test in abstract_test_q.all():
            # check if all parameter entries are in the abstract test
            parameter_entry_ids_abstract_test = [p.id for p in abstract_test.parameters]
            if set(parameter_entry_ids_data) == set(parameter_entry_ids_abstract_test):
                abstract_test_obj = abstract_test

        # if abstract test does not exist, create it
        if not abstract_test_obj:
            abstract_test_obj = AbstractTest(name=name, description=description, testfunction=testfunction, tool=tool)

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

    def __get_experiment(self, experiment_name: str, experiment_description: str, os_info: dict, tests_data: list, action_file: Path, testset_file:Path):

        # create or get os info entry
        os_info_obj = self._session.query(OsInfo).filter_by(**os_info).first()
        if not os_info_obj:
            os_info_obj = OsInfo(**os_info)
            self._session.add(os_info_obj)
        self._session.commit()

        # create abstract test objects from test data
        abstract_test_objects = {}
        for t_data in tests_data:
            # used for tests that are associated with a tool
            if 'tests' in t_data.keys():
                tool = self._session.query(Tool).filter_by(name=t_data['tool'], command=t_data['command']).first()
                if not tool:
                    tool = Tool(name=t_data['tool'], command=t_data['command'])
                    self._session.add(tool)
                    self._session.commit()
                for tool_t_data in t_data['tests']:
                    abstract_test = self.__get_abstract_test(tool_t_data, tool=tool)
                    abstract_test_objects[tool_t_data['name']] = abstract_test
            else:
                abstract_test = self.__get_abstract_test(t_data)
                abstract_test_objects[t_data['name']] = abstract_test

        # generate experiment hash
        sha256_action_file = hash_file_sha256(action_file)
        sha256_testset_file = hash_file_sha256(testset_file)
        experiment_hash = combine_hashes([sha256_action_file, sha256_testset_file])

        # check if experiment exists
        experiment = None
        experiment_q = self._session.query(Experiment).filter_by(experiment_hash=experiment_hash)
        # check if query does exactly return one experiment
        if experiment_q.count() > 0:
            experiment = experiment_q.first()

        # if experiment does not exist, create it
        if not experiment:
            publish_status = self._session.query(PublishStatus).filter_by(name='unknown').first()
            if not publish_status:
                log.error(f'publish status unknown not found in database')
                return
            experiment = Experiment(name=experiment_name, description=experiment_description, os_info=os_info_obj, action_file=action_file.as_posix(), testset_file=testset_file.as_posix(), experiment_hash=experiment_hash, publish_status=publish_status)
            for abstract_test_object in abstract_test_objects.values():
                experiment.abstract_tests.append(abstract_test_object)
            self._session.add(experiment)
            self._session.commit()

        return experiment

    def get_scenario_by_uuid(self, uuid: str):
        """
            Returns the scenario with the given id.
        """
        scenario = self._session.query(Scenario).filter_by(uuid=uuid).first()
        return scenario

    def add_experiment_run(self, testset_data: dict, action_file: Path, testset_file:Path, result_data: list, logfile_data: dict, status_data: dict, timestamps: dict, os_info: dict, sha256_validation_hash: str):
        experiment_name = testset_data['name']
        experiment_description = get_value_if_missing_key(testset_data, 'description', dtype=str)

        # check if test section exists in testset data
        if 'tests' not in testset_data.keys():
            log.error(f'no tests found in testset data')
            return

        # get status
        status_list = [
            'TOTAL',
            'INSTALL_gui',
            'INSTALL_parseandtest',
            'RUN_gui',
            'RUN_parseandtest',
            'VAGRANT',
            'gui',
            'parseandtest',
        ]

        status_obj_dict = dict()
        for status in status_data.keys():
            status_obj = self._session.query(Status).filter_by(name=status_data[status]).first()
            if not status_obj:
                log.error(f'status {status_data[status]} not found in database!')
                return
            status_obj_dict[status] = status_obj

        not_reached_status = self._session.query(Status).filter_by(name='not reached').first()
        for status_name in status_list:
            if status_name not in status_obj_dict.keys():
                status_obj_dict[status_name] = not_reached_status

        # check if experiment for this run exists
        experiment = self.__get_experiment(experiment_name, experiment_description, os_info, testset_data['tests'], action_file=action_file, testset_file=testset_file)


        # create experiment entry

        exp = ExperimentRun(
            experiment=experiment,
            timestamp_start=timestamps['timestamp_start'],
            timestamp_end=timestamps['timestamp_end'],
            status=status_obj_dict['TOTAL'],
            status_gui_automation=status_obj_dict['gui'],
            status_parse_and_test=status_obj_dict['parseandtest'],
            status_vagrant=status_obj_dict['VAGRANT'],
            logfile_vagrant=self.__add_logfile('vagrant', logfile_data['logfile_vagrant']),
            logfile_gui_automation=self.__add_logfile('gui automation', logfile_data['logfile_gui_automation']),
            logfile_parse_and_test=self.__add_logfile('parse and test', logfile_data['logfile_parse_and_test']),
            logfile_postsetup_installations=self.__add_logfile('postsetup installations', logfile_data['logfile_postsetup_installations']),
            logfile_installed_packages=self.__add_logfile('installed packages', logfile_data['logfile_installed_packages']),
            logfile_run_experiment=self.__add_logfile('experiment', logfile_data['logfile_run_experiment']),
            sha256_validation_hash=sha256_validation_hash,
        )

        # add tests to the experiment
        if result_data:
            for test in testset_data['tests']:
                if 'tests' in test.keys():
                    for inner_test in test['tests']:
                        # get the abstract test object from experiment
                        abstract_test = self.__get_abstract_test(inner_test)
                        test_obj = self.__add_test(abstract_test, self.__get_result_entry_by_name(result_data, inner_test['name']))
                        exp.tests.append(test_obj)
                else:
                    abstract_test = self.__get_abstract_test(test)
                    test_obj = self.__add_test(abstract_test, self.__get_result_entry_by_name(result_data, test['name']))
                    exp.tests.append(test_obj)

        self._session.add(exp)
        self._session.commit()
        log.info(f'added experiment run {exp.uuid} to database')


class UserSessionApi(ProgramDatabase):
    def __init__(self, db_path: Path = config_database.get_database_location()):
        super().__init__(db_path)

    def __enter__(self):
        super().__enter__()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        super().__exit__(exc_type, exc_val, exc_tb)

    def add_user_session(self, username: str, token: str, expiration_date: datetime):
        self._session.add(UserSession(username=username, token=token, expirationdate=expiration_date))
        self._session.commit()
        log.debug(f'added user session for user {username} (expiration date {expiration_date})')

    def remove_user_session(self, username: str):
        user_session = self._session.query(UserSession).filter_by(username=username).first()
        if user_session:
            self._session.delete(user_session)
            self._session.commit()
            log.debug(f'removed user session for user {username}')

    def remove_expired_user_sessions(self):
        for user_session in self._session.query(UserSession).all():
            if user_session.expirationdate < datetime.now():
                self._session.delete(user_session)
                log.info(f'deleted user session for user {user_session.username}, because it expired')
        self._session.commit()

    def get_user_session(self, username: str):
        return self._session.query(UserSession).filter_by(username=username).first()

    def get_first_user_session(self):
        return self._session.query(UserSession).first()

    def check_user_session(self):
        for user_session in self._session.query(UserSession).all():
            if user_session.expirationdate < datetime.now():
                self._session.delete(user_session)
                log.info(f'deleted user session for user {user_session.username}, because it expired')


class RequestSessionApi(ProgramDatabase):
    def __init__(self, db_path: Path = config_database.get_database_location()):
        super().__init__(db_path)

    def __enter__(self):
        super().__enter__()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        super().__exit__(exc_type, exc_val, exc_tb)

    def add_request(self, req_type: str, title: str = '', description: str = '', experiment_uuid: str = None, scenario_uuid: str = None):
        if req_type not in ['experiment', 'scenario']:
            log.error(f'invalid request type {req_type}')
            return None, 'invalid request type'
        # add request to database (with status 'open')
        status_obj = self._session.query(PublishStatus).filter_by(name='not published').first()
        if not status_obj:
            log.error(f'publish status "not published" not found in database')
            return None, 'publish status "not published" not found in database'
        # get experiment and scenario objects
        experiment_obj = None
        scenario_obj = None
        if experiment_uuid:
            experiment_obj = self._session.query(Experiment).filter_by(uuid=experiment_uuid).first()
        if scenario_uuid:
            scenario_obj = self._session.query(Scenario).filter_by(uuid=scenario_uuid).first()
        if not experiment_obj and not scenario_obj:
            log.error(f'could not find experiment or scenario with uuid {experiment_uuid if experiment_uuid else scenario_uuid}')
            return None, f'could not find experiment or scenario with uuid {experiment_uuid if experiment_uuid else scenario_uuid}'
        req = Request(title=title, description=description, type=req_type, experiment=experiment_obj, scenario=scenario_obj, status=status_obj)
        self._session.add(req)
        self._session.commit()
        log.debug(f'added request to database (uuid: {req.uuid}, type: {req_type})')
        return req.uuid, ''

    def get_request_by_uuid(self, uuid: str):
        return self._session.query(Request).filter_by(uuid=uuid).first()

    def get_all_requests(self):
        all_requests = self._session.query(Request).all()
        log.debug(f'got all requests from database (count: {len(all_requests)})')
        return all_requests