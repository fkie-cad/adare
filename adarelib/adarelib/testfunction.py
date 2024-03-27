import importlib
import importlib.util
from inspect import isclass
from pathlib import Path
import cattrs
import attrs

from adarevm.testset.basictest import BasicTest
from adarelib.types import TestsetFile
from adarelib.helperfunctions.module import import_module_from_pyfile

import logging
log = logging.getLogger(__name__)


def import_basictest_subclasses(directory: Path) -> dict:
    testdict = {}

    for testfunction_dir in directory.iterdir():
        file = testfunction_dir / f'{testfunction_dir.name}.py'
        if not (testfunction_dir / f'{testfunction_dir.name}.py').exists():
            continue
        module = import_module_from_pyfile(file)
        testdict[file.stem] = {}

        for attribute_name in dir(module):
            attribute = getattr(module, attribute_name)
            if isclass(attribute) and issubclass(attribute, BasicTest):
                globals()[attribute_name] = attribute
                testdict[file.stem][getattr(attribute, 'testname')] = attribute

    return testdict


def get_testclass_from_testfunction(testfunction: str, testfunction_collection: dict):
    if '.' not in testfunction:
        return testfunction_collection['standard'].get(testfunction)
    testfunction_list, testfunction = testfunction.split('.', 1)
    return testfunction_collection[testfunction_list].get(testfunction)


def get_missing_testfunctions(testset: TestsetFile, testfunction_collection: dict):
    return [
        test.type
        for test in testset.tests
        if not get_testclass_from_testfunction(
            test.type, testfunction_collection
        )
    ]


def structure_tests(testset: TestsetFile, testfunction_collection: dict) -> (dict, dict):
    if get_missing_testfunctions(testset, testfunction_collection):
        raise ValueError('testset contains tests that are not supported by the testfunction collection')

    structure_error_dict = {}
    tests = {}

    for test in testset.tests:
        testclass = get_testclass_from_testfunction(test.type, testfunction_collection)
        try:
            testclass_instance = cattrs.structure(attrs.asdict(test), testclass)
        except cattrs.errors.ClassValidationError as e:
            log.error('an test has missing/wrong parameters in the testset file -> see exception below')
            log.error(e, exc_info=True)
            structure_error_dict[test.type] = e.message
            continue
        tests[test.name] = testclass_instance

    return tests, structure_error_dict

