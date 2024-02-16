# external imports
import pkg_resources
from importlib import import_module
from pkgutil import iter_modules
from inspect import isclass
import cattrs
from cattrs.errors import ClassValidationError

# internal imports
from parseandtest.tester.testresult import TestOutcome
from parseandtest.tester.testcontainer import TestContainer
from parseandtest.tester.basictest import BasicTest
import parseandtest.config as config
from parseandtest.helperfunctions.yaml import yaml_to_dict

# configure logging
import logging
log = logging.getLogger(__name__)


def import_basictest_subclasses_from_package():
    subclass_dict_BasicTest = dict()
    package_dir = pkg_resources.resource_filename('parseandtest.testfunctions', '')
    for (_, module_name, _) in iter_modules([package_dir]):

        # import the module and iterate through its attributes
        module = import_module(f"parseandtest.testfunctions.{module_name}")
        for attribute_name in dir(module):
            attribute = getattr(module, attribute_name)

            if isclass(attribute) and issubclass(attribute, BasicTest):
                globals()[attribute_name] = attribute
                subclass_dict_BasicTest[getattr(attribute, 'testname')] = attribute
    return subclass_dict_BasicTest


class Tester:
    input = None
    outcome: TestOutcome = None
    supported_classes: dict or None = None
    unsupported_types: list = None

    def __init__(self):
        self.supported_classes = import_basictest_subclasses_from_package()
        self.unsupported_types = []

    def set_input(self, input):
        self.input = input

    def test(self):
        status = 'success'
        if not self.input:
            log.error('no input for parser set')
            return 'failed'
        testoutcome = TestOutcome()
        unsupported_types = []

        # list of tests (dict)
        tests = self.input['tests']

        vars_tmp_file = config.VARIABLES_FILE
        try:
            variables = yaml_to_dict(vars_tmp_file)
        except FileNotFoundError:
            variables = {}

        for test in tests:
            if type(test) != dict:
                log.error(f'test {test} was not of type dict and will be therefore ignored')
                status = 'warning'
                continue
            keys_test = test.keys()

            test_container = None
            if 'type' in keys_test:
                test_container = TestContainer([test])
            elif 'tool' in test.keys():
                try:
                    test_container = cattrs.structure(test, TestContainer)
                except ClassValidationError as e:
                    log.error(f'an test has missing/wrong parameters in the input file -> see exception below')
                    log.error(e, exc_info=True)
                    continue
            if test_container:
                unsupported, testresults = test_container.test(variables, self.supported_classes)
                for result in testresults:
                    testoutcome.add_test_result(result)
                unsupported_types += unsupported

        self.unsupported_types = unsupported_types
        self.outcome = testoutcome
        return status
