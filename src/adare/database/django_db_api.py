# external imports
from pathlib import Path

# internal imports
import adare.config as config
import adare.config.database as config_database
from adare.helperFunctions.pyfileanalyze import PyModuleAnalyzer
from adare.django_adareGUI.models import Status, OsInfo, Experiment, Test, TestParameter, TestParameterEntries, TestFunction

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
                                    log.info(f'test function name of test function class {t_func_class.name} changed to {test_name}')
                                    db_testfunction_obj.save()
                                if db_testfunction_obj.test_description != test_description:
                                    db_testfunction_obj.test_description = test_description
                                    log.info(f'test description of test function class {t_func_class.name} changed to {test_description}')
                                    db_testfunction_obj.save()
                            except TestFunction.DoesNotExist:
                                db_testfunction_obj = TestFunction.objects.create(id=None, name=t_func_class.name, test_name=test_name, test_description=test_description)
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


