from inspect import isclass
from pathlib import Path
import cattrs
import attrs

from adarelib.testset.basictest import BasicTest
from adarelib.testset.type import TestsetFile
from adarelib.helper.module import import_module_from_pyfile

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
    missing = []
    for test in testset.tests:
        testclass = get_testclass_from_testfunction(test.function, testfunction_collection)
        if not testclass:
            missing.append(test.function)
            log.error(f"Missing testfunction: {test.function}")
            log.debug(f"Available testfunctions: {testfunction_collection}")
    
    if missing:
        log.error(f"Missing testfunctions: {missing}")
        log.debug(f"Available testfunction collections: {list(testfunction_collection.keys())}")
        for collection_name, functions in testfunction_collection.items():
            log.debug(f"Collection '{collection_name}': {list(functions.keys())}")
    
    return missing


def structure_tests(testset: TestsetFile, testfunction_collection: dict) -> tuple[dict, dict]:
    if get_missing_testfunctions(testset, testfunction_collection):
        raise ValueError('testset contains tests that are not supported by the testfunction collection')

    structure_error_dict = {}
    tests = {}

    for test in testset.tests:
        testclass = get_testclass_from_testfunction(test.function, testfunction_collection)
        try:
            testclass_instance = cattrs.structure(attrs.asdict(test), testclass)
        except cattrs.errors.ClassValidationError as e:
            log.error('an test has missing/wrong parameters in the testset file -> see exception below')
            log.error(e, exc_info=True)
            structure_error_dict[test.function] = e.message
            continue
        tests[test.name] = testclass_instance

    return tests, structure_error_dict

