import sqlalchemy
from sqlalchemy.orm import sessionmaker
from datetime import datetime
import adare.config.database as config_database
from adare.database.models.login import UserSession, Base as LoginBase
from adare.database.models.experiments import TestParameter, TestParameterEntry, Experiment, Status, TestFunction, Test, Tool, Result, OsInfo, LogFile, Base as ExperimentsBase
import adare.config as config
from pathlib import Path
from adare.helperFunctions.dict.dict import get_value_if_missing_key
from adare.helperFunctions.pyfileanalyze import PyModuleAnalyzer

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
        log.info(f'Added preconfigured status to database.')
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

    def get_experiment_by_uuid(self, uuid: str):
        """
            Returns the experiment with the given id.
        """
        experiment = self._session.query(Experiment).filter_by(uuid=uuid).first()
        return experiment

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
                            testfunction_query = self._session.query(TestFunction).filter_by(name=t_func_class.name)
                            db_testfunction_objects = list(testfunction_query)
                            if db_testfunction_objects:
                                db_testfunction_obj = db_testfunction_objects[0]
                                if db_testfunction_obj.test_name != test_name:
                                    db_testfunction_obj.test_name = test_name
                                    log.info(f'test function name of test function class {t_func_class.name} changed to {test_name}')
                                if db_testfunction_obj.test_description != test_description:
                                    db_testfunction_obj.test_description = test_description
                                    log.info(
                                        f'test description of test function class {t_func_class.name} changed to {test_description}')
                            else:
                                db_testfunction_obj = TestFunction(name=t_func_class.name,
                                                                   test_name=test_name,
                                                                   test_description=test_description)

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

    def add_testparameter(self, name, dtype):
        """
            adds a testparameter to the database.
        """
        testparameter = TestParameter(name=name, dtype=dtype)
        self._session.add(testparameter)
        self._session.commit()
        return testparameter

    def add_testparameterentry(self, parameter, value):
        """
            adds a testparameterentry to the database.
        """
        testparameterentry = TestParameterEntry(parameter=parameter, value=value)
        self._session.add(testparameterentry)
        self._session.commit()

    def __add_test(self, test: dict, test_result: dict, tool: Tool = None):
        """
            adds a test to the database
        """
        name = test['name']
        description = test['description']
        testfunction = self._session.query(TestFunction).filter_by(test_name=test['type']).first()
        if not testfunction:
            log.error(f'testfunction {test["type"]} does not exist')
            return
        status_name = test_result['result']['status']
        status_obj = self._session.query(Status).filter_by(name=status_name).first()
        if not status_obj:
            log.fatal(f'status {status_name} does not exist')
            return
        # result_details = '||'.join(test_result['details'])
        result_obj = self._session.query(Result).filter_by(status=status_obj).first()
        if not result_obj:
            result_details = ''
            result_obj = Result(status=status_obj, details=result_details)
            self._session.add(result_obj)
        test_obj = Test(name=name, description=description, testfunction=testfunction, result=result_obj, tool=tool)
        for p_key, p_val in test['params'].items():
            parameter = self._session.query(TestParameter).filter_by(name=p_key).first()
            test_parameter_entry_obj = TestParameterEntry(parameter=parameter, value=str(p_val))
            self._session.add(test_parameter_entry_obj)
            test_obj.testparameterentry.append(test_parameter_entry_obj)
        self._session.add(test_obj)
        self._session.commit()
        return test_obj

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

    def add_experiment(self, name: str, inputdata: dict, resultdata: list, logfiledata: dict, statusdata: dict, timestamps: dict, os_info: dict):
        if 'tests' not in inputdata.keys():
            log.error(f'input file does not contain a tests section')
            return

        # create or get os info entry
        os_info_obj = self._session.query(OsInfo).filter_by(**os_info).first()
        if not os_info_obj:
            os_info_obj = OsInfo(**os_info)
            self._session.add(os_info_obj)

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
        for status in statusdata.keys():
            status_obj = self._session.query(Status).filter_by(name=statusdata[status]).first()
            if not status_obj:
                log.error(f'status {statusdata[status]} not found in database!')
                return
            status_obj_dict[status] = status_obj

        not_reached_status = self._session.query(Status).filter_by(name='not reached').first()
        for status_name in status_list:
            if status_name not in status_obj_dict.keys():
                status_obj_dict[status_name] = not_reached_status

        # create experiment entry
        exp = Experiment(
            name=name,
            timestamp_start=timestamps['timestamp_start'],
            timestamp_end=timestamps['timestamp_end'],
            description=get_value_if_missing_key(inputdata, 'description', dtype=str),
            os_info=os_info_obj,
            status=status_obj_dict['TOTAL'],
            status_gui_automation=status_obj_dict['gui'],
            status_parse_and_test=status_obj_dict['parseandtest'],
            status_vagrant=status_obj_dict['VAGRANT'],
            logfile_vagrant=self.__add_logfile('vagrant', logfiledata['logfile_vagrant']),
            logfile_gui_automation=self.__add_logfile('gui automation', logfiledata['logfile_gui_automation']),
            logfile_parse_and_test=self.__add_logfile('parse and test', logfiledata['logfile_parse_and_test']),
            logfile_postsetup_installations=self.__add_logfile('postsetup installations', logfiledata['logfile_postsetup_installations']),
            logfile_installed_packages=self.__add_logfile('installed packages', logfiledata['logfile_installed_packages']),
            logfile_run_experiment=self.__add_logfile('experiment', logfiledata['logfile_run_experiment']),
        )

        # add tests to the experiment
        tests = inputdata['tests']
        if resultdata:
            for test in tests:
                if 'tests' in test.keys():
                    for inner_test in test['tests']:
                        tool = self._session.query(Tool).filter_by(name=test['tool'], command=test['command']).first()
                        if not tool:
                            tool = Tool(name=test['tool'], command=test['command'])
                            self._session.add(tool)
                        test_obj = self.__add_test(inner_test, self.__get_result_entry_by_name(resultdata, inner_test['name']), tool=tool)
                        exp.tests.append(test_obj)
                else:
                    test_obj = self.__add_test(test, self.__get_result_entry_by_name(resultdata, test['name']))
                    exp.tests.append(test_obj)

        self._session.add(exp)
        self._session.commit()


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

