import importlib
import importlib.util
from inspect import isclass
from pathlib import Path
import cattrs
import attrs

from adarevm.testset.basictest import BasicTest
from adarelib.testsetfile.fileformat import TestsetFile
from adarelib.helperfunctions.module import import_module_from_pyfile

import logging
log = logging.getLogger(__name__)


def import_basictest_subclasses(directory: Path) -> dict:
    testdict = {}

    for file in directory.glob('*.py'):
        module = import_module_from_pyfile(file)
        testdict[file.stem] = {}

        for attribute_name in dir(module):
            attribute = getattr(module, attribute_name)
            if isclass(attribute) and issubclass(attribute, BasicTest):
                globals()[attribute_name] = attribute
                testdict[file.stem][getattr(attribute, 'testname')] = attribute

    return testdict


def check_if_tests_exist(testset: TestsetFile, testfunction_collection: dict):
    # todo: change here since testfunction collection is more nested
    return [
        test.type
        for test in testset.tests
        if test.type not in testfunction_collection
    ]


def structure_tests(testset: TestsetFile, testfunction_collection: dict) -> (dict, dict):
    if check_if_tests_exist(testset, testfunction_collection):
        raise ValueError('testset contains tests that are not supported by the testfunction collection')

    structure_error_dict = {}
    tests = {}

    for test in testset.tests:
        testclass = testfunction_collection[test.type]
        try:
            testclass_instance = cattrs.structure(attrs.asdict(test), testclass)
        except cattrs.errors.ClassValidationError as e:
            log.error('an test has missing/wrong parameters in the testset file -> see exception below')
            log.error(e, exc_info=True)
            structure_error_dict[test.type] = e.message
            continue
        tests[test.name] = testclass_instance

    return tests, structure_error_dict

