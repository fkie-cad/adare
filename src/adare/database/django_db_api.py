# external imports
from pathlib import Path
from django.utils.timezone import make_aware

# internal imports
import adare.config as config
import adare.config.database as config_database
from adare.helperFunctions.pyfileanalyze import PyModuleAnalyzer
from adare.helperFunctions.dict.dict import get_value_if_missing_key
from adare.django_adareGUI.models import Status, OsInfo, Experiment, Test, TestParameter, TestParameterEntries, \
    TestFunction, Result, Tool
from adare.helperFunctions.django.orm import get_or_none

# configure logging
import logging
log = logging.getLogger(__name__)


class DjangoDbApi:

    def __init__(self):
        self.__update_database()

    def __update_database(self):
        """
            initialize/update the database with pre-set data for certain tables
        """
        self.__update_status(cleanup=True)
        self.__update_testfunctionsparameter()

    def __update_testfunctionsparameter(self, python_file_dir: list = config.PCK_PARSEANDTEST_TESTFUNCTION_DIRS):
        for directory in python_file_dir:
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
                                try:
                                    db_testparameter_obj = TestParameter.objects.get(name=attr['name'])
                                except TestParameter.DoesNotExist:
                                    db_testparameter_obj = TestParameter.objects.create(
                                        id=None, name=attr['name'], dtype=attr['type']
                                    )
                                db_parameter_objects[attr['name']] = db_testparameter_obj
                            # add testfunction to db
                            test_name = t_func_class.get_attribute('testname').get_value()
                            test_description = t_func_class.get_attribute('testdescription').get_value()
                            try:
                                db_testfunction_obj = TestFunction.objects.get(name=t_func_class.name)
                                if db_testfunction_obj.test_name != test_name:
                                    db_testfunction_obj.test_name = test_name
                                    log.info(
                                        f'test function name of test function class {t_func_class.name} changed to {test_name}')
                                    db_testfunction_obj.save()
                                if db_testfunction_obj.test_description != test_description:
                                    db_testfunction_obj.test_description = test_description
                                    log.info(
                                        f'test description of test function class {t_func_class.name} changed to {test_description}')
                                    db_testfunction_obj.save()
                            except TestFunction.DoesNotExist:
                                db_testfunction_obj = TestFunction.objects.create(id=None, name=t_func_class.name,
                                                                                  test_name=test_name,
                                                                                  test_description=test_description)
                            # add parameter to testfunction in database
                            for db_parameter_objects in db_parameter_objects.values():
                                db_testfunction_obj.possible_parameters.add(db_parameter_objects)
                        else:
                            log.warning(f'parameter class for testfunction class {t_func_class.name} is missing')
                    else:
                        log.warning(f'testfunction class {t_func_class.name} is missing the mandatory params attribute')

    def __update_status(self, status_list: list = config_database.DB_STATUS_LIST, cleanup: bool = False):
        """
            initialize/update the status table with pre-set data
        """
        for status in status_list:
            if not Status.objects.filter(name=status).exists():
                Status(id=None, name=status).save()
                log.info(f'status {status} added to database')
        if cleanup:
            status_list_db = Status.objects.values('name')
            for status in status_list_db:
                if status['name'] not in status_list:
                    Status.objects.filter(name=status['name']).delete()
                    log.info(f'status {status} got deleted')

    def __add_test(self, test: dict, test_result: dict, tool: Tool = None):
        name = test['name']
        description = test['description']
        testfunction = get_or_none(TestFunction, test_name=test['type'])
        if not testfunction:
            log.error(f'testfunction {test["type"]} does not exist')
            return
        status_name = test_result['result']['status']
        status_obj = get_or_none(Status, name=status_name)
        if not status_obj:
            log.fatal(f'status {status_name} does not exist')
            return
        # result_details = '||'.join(test_result['details'])
        result_details = ''
        result_obj = get_or_none(Result, status=status_obj, details=result_details)
        if not result_obj:
            result_obj = Result(status=status_obj, details=result_details)
            result_obj.save()
        test_obj = Test(name=name, description=description, testfunction=testfunction, result=result_obj, tool=tool)
        test_obj.save()
        for p_key, p_val in test['params'].items():
            parameter = get_or_none(TestParameter, name=p_key)
            test_parameter_entry_obj = TestParameterEntries(parameter=parameter, value=str(p_val))
            test_parameter_entry_obj.save()
            test_obj.parameters.add(test_parameter_entry_obj)
        return test_obj

    def __get_result_entry_by_name(self, data: list, name: str) -> dict:
        for result_entry in data:
            if result_entry['name'] == name:
                return result_entry
        return dict()

    def add_experiment(self, name: str, inputdata: dict, resultdata: list, logfiledata: dict, statusdata: dict, timestamps: dict, os_info: dict):
        """
        add experiment outcome to database
        :param inputdata: dict containing the data provided as an input for the test
        :param resultdata:
        :param details:
        :param os_info: dict containing information about the os the experiment was run on
        """
        if 'tests' not in inputdata.keys():
            log.error(f'input file does not contain a tests section')
            return

        # create or get os info entry
        try:
            os_info_obj = OsInfo.objects.get(**os_info)
        except OsInfo.DoesNotExist:
            os_info_obj = OsInfo(**os_info)
            os_info_obj.save()

        # get status
        try:
            status = Status.objects.get(name=statusdata['status'])
            status_gui_automation = Status.objects.get(name=statusdata['status_gui_automation'])
            status_parse_and_test = Status.objects.get(name=statusdata['status_parse_and_test'])
            status_vagrant = Status.objects.get(name=statusdata['status_vagrant'])
        except Status.DoesNotExist as e:
            log.error(e, exc_info=True)
            log.fatal(f'status not found in database!')
            return

        # create experiment entry
        exp = Experiment(
            name=name,
            timestamp_start=make_aware(timestamps['timestamp_start']),
            timestamp_end=make_aware(timestamps['timestamp_end']),
            description=get_value_if_missing_key(inputdata, 'description', dtype=str),
            os_info=os_info_obj,
            status=status,
            status_gui_automation=status_gui_automation,
            status_parse_and_test=status_parse_and_test,
            status_vagrant=status_vagrant,
            logfile_vagrant=get_value_if_missing_key(logfiledata, 'logfile_vagrant', dtype=str),
            logfile_gui_automation=get_value_if_missing_key(logfiledata, 'logfile_gui_automation', dtype=str),
            logfile_parse_and_test=get_value_if_missing_key(logfiledata, 'logfile_parse_and_test', dtype=str),
            logfile_postsetup_installations=get_value_if_missing_key(logfiledata, 'logfile_postsetup_installations', dtype=str),
            logfile_installed_packages=get_value_if_missing_key(logfiledata, 'logfile_installed_packages', dtype=str),
        )
        exp.save()

        # add tests to the experiment
        tests = inputdata['tests']
        for test in tests:
            if 'tests' in test.keys():
                for inner_test in test['tests']:
                    tool = get_or_none(Tool, name=test['tool'], command=test['command'])
                    if not tool:
                        tool = Tool(name=test['tool'], command=test['command'])
                        tool.save()
                    test_obj = self.__add_test(inner_test, self.__get_result_entry_by_name(resultdata, inner_test['name']), tool=tool)
                    exp.tests.add(test_obj)
            else:
                test_obj = self.__add_test(test, self.__get_result_entry_by_name(resultdata, test['name']))
                exp.tests.add(test_obj)