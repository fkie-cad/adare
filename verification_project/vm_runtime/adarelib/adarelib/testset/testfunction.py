from inspect import isclass
from pathlib import Path
import cattrs
import attrs

from adarelib.testset.basictest import BasicTest
from adarelib.testset.type import TestsetFile
from adarelib.helper.module import import_module_from_pyfile
from adarelib.common.variables import VariableRegistry

import logging
log = logging.getLogger(__name__)


def import_basictest_subclasses(source=None, directory=None) -> dict:
    """
    Import BasicTest subclasses from either database records or directory scanning.

    Args:
        source: Optional list of (name, path) tuples from database
        directory: Optional directory path for filesystem scanning (fallback)

    Returns:
        dict: Nested dictionary {file_name: {testname: test_class}}
    """
    testdict = {}

    if source:
        # Database-driven approach: use provided (name, path) tuples
        for name, file_path in source:
            file_path = Path(file_path)
            if not file_path.exists():
                log.warning(f"Testfunction file not found: {file_path}")
                continue

            try:
                module = import_module_from_pyfile(file_path)
                testdict[name] = {}

                for attribute_name in dir(module):
                    attribute = getattr(module, attribute_name)
                    if isclass(attribute) and issubclass(attribute, BasicTest):
                        globals()[attribute_name] = attribute
                        testdict[name][getattr(attribute, 'testname')] = attribute
            except Exception as e:
                log.error(f"Error loading testfunction module {file_path}: {e}")
                continue

    elif directory:
        # Filesystem scanning approach (existing logic)
        directory = Path(directory)
        if not directory.exists():
            log.warning(f"Testfunctions directory not found: {directory}")
            return testdict

        for testfunction_dir in directory.iterdir():
            if not testfunction_dir.is_dir():
                continue

            file = testfunction_dir / f'{testfunction_dir.name}.py'
            if not file.exists():
                continue

            try:
                module = import_module_from_pyfile(file)
                testdict[file.stem] = {}

                for attribute_name in dir(module):
                    attribute = getattr(module, attribute_name)
                    if isclass(attribute) and issubclass(attribute, BasicTest):
                        globals()[attribute_name] = attribute
                        testdict[file.stem][getattr(attribute, 'testname')] = attribute
            except Exception as e:
                log.error(f"Error loading testfunction module {file}: {e}")
                continue
    else:
        raise ValueError("Either 'source' or 'directory' parameter must be provided")

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
            # Convert test to dict and ensure variables are properly handled
            test_dict = attrs.asdict(test)
            
            # Convert variables to VariableRegistry if present
            if 'variables' in test_dict and test_dict['variables']:
                if not isinstance(test_dict['variables'], VariableRegistry):
                    test_dict['variables'] = VariableRegistry.from_dict(test_dict['variables'])
            
            testclass_instance = cattrs.structure(test_dict, testclass)
        except cattrs.errors.ClassValidationError as e:
            log.error('an test has missing/wrong parameters in the testset file -> see exception below')
            log.error(e, exc_info=True)
            structure_error_dict[test.function] = e.message
            continue
        tests[test.name] = testclass_instance

    return tests, structure_error_dict

