import importlib
from inspect import isclass
import cattrs
from cattrs.errors import ClassValidationError
from pathlib import Path

from adarevm.testset.testresult import TestOutcome
from adarevm.testset.testcontainer import TestContainer
from adarevm.testset.basictest import BasicTest
import adarevm.config as config
from adarelib.helperfunctions.yaml import yaml_to_dict


import logging
log = logging.getLogger(__name__)


def import_basictest_subclasses(directory: Path) -> dict:
    testdict = {}
    for file in directory.glob('*.py'):  # Simplified iteration
        module_name = file.stem
        module = importlib.import_module(module_name)  # Simplified import
        for attribute_name in dir(module):
            attribute = getattr(module, attribute_name)
            if isclass(attribute) and issubclass(attribute, BasicTest):
                globals()[attribute_name] = attribute
                testdict[getattr(attribute, 'testname')] = attribute
    return testdict


def load_variables():
    try:
        return yaml_to_dict(config.VARIABLES_FILE)
    except FileNotFoundError:
        return {}


def create_test_container(test):
    if 'type' in test:
        return TestContainer([test])
    elif 'tool' in test:
        try:
            return cattrs.structure(test, TestContainer)
        except ClassValidationError as e:
            log.error('an test has missing/wrong parameters in the testset file -> see exception below')
            log.error(e, exc_info=True)
            return None


class Testset:
    testsetfile_data: dict
    outcome: TestOutcome

    supported_classes: dict
    unsupported_types: list

    testsetfile_tests: dict


    def __init__(self, testfunctions_directory: Path, testsetfile_data: dict):
        self.supported_classes = import_basictest_subclasses(testfunctions_directory)
        self.unsupported_types = []
        self.testsetfile_data = testsetfile_data
        self.testsetfile_tests = {}
        self.outcome = TestOutcome()


    def __parse_testsetfile_data(self):
        for test in self.testsetfile_data.get('tests', []):
            if test['name'] in self.testsetfile_tests:
                log.error(f'test {test["name"]} is defined more than once')
                return 'failed'
            if not isinstance(test, dict):
                log.error(f'test {test} was not of type dict and will be therefore ignored')
                continue
            self.testsetfile_tests[test['name']] = test


    def testall(self):
        if not self.testsetfile_data:
            log.error('data of testsetfile is empty')
            return 'failed'
        unsupported_types = []

        variables = load_variables()

        for test in self.testsetfile_tests.values():
            if test_container := create_test_container(test):
                unsupported, testresults = test_container.test(variables, self.supported_classes)
                for result in testresults:
                    self.outcome.add_test_result(result)
                unsupported_types.extend(unsupported)  # Simplified list concatenation

        self.unsupported_types = unsupported_types
        return 'success'

    def test(self, name: str):
        if not self.testsetfile_data:
            log.error('data of testsetfile is empty')
            return 'failed'
        variables = load_variables()

        if test := self.testsetfile_tests.get(name):
            if test_container := create_test_container(test):
                return self._run_test_in_container(test_container, variables)

    def _run_test_in_container(self, test_container, variables):
        unsupported, testresults = test_container.test(variables, self.supported_classes)
        for result in testresults:
            self.outcome.add_test_result(result)
        unsupported_types = []
        unsupported_types.extend(unsupported)
        self.unsupported_types = unsupported_types
        return 'success'
    

