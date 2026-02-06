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


# Module load failure tracking
@attrs.define
class ModuleLoadFailure:
    """Track failed testfunction module loads with context."""
    module_name: str
    file_path: str
    exception_type: str
    exception_message: str

    def get_user_friendly_message(self) -> str:
        """Generate user-friendly error message."""
        if self.exception_type == 'ModuleNotFoundError':
            # Extract dependency name from exception message
            import re
            match = re.search(r"No module named '([^']+)'", self.exception_message)
            if match:
                dep_name = match.group(1)
                return f"Testfunction '{self.module_name}' requires missing dependency: {dep_name}"
            return f"Testfunction '{self.module_name}' has missing dependency: {self.exception_message}"
        elif self.exception_type == 'ImportError':
            return f"Testfunction '{self.module_name}' import failed: {self.exception_message}"
        elif self.exception_type == 'SyntaxError':
            return f"Testfunction '{self.module_name}' has syntax error: {self.exception_message}"
        else:
            return f"Testfunction '{self.module_name}' failed to load: {self.exception_type}: {self.exception_message}"


# Global registry of failed module loads
_module_load_failures: dict[str, ModuleLoadFailure] = {}


def get_module_load_failures() -> dict[str, ModuleLoadFailure]:
    """Get registry of all failed module loads."""
    return _module_load_failures.copy()


def clear_module_load_failures():
    """Clear the module load failure registry."""
    global _module_load_failures
    _module_load_failures = {}


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

            except ModuleNotFoundError as e:
                # Missing dependency (e.g., pandas, openpyxl)
                log.error(f"Missing dependency loading testfunction '{name}' from {file_path}: {e}")
                _module_load_failures[name] = ModuleLoadFailure(
                    module_name=name,
                    file_path=str(file_path),
                    exception_type='ModuleNotFoundError',
                    exception_message=str(e)
                )
                continue

            except ImportError as e:
                # General import failure
                log.error(f"Import error loading testfunction '{name}' from {file_path}: {e}")
                _module_load_failures[name] = ModuleLoadFailure(
                    module_name=name,
                    file_path=str(file_path),
                    exception_type='ImportError',
                    exception_message=str(e)
                )
                continue

            except SyntaxError as e:
                # Code syntax error
                log.error(f"Syntax error in testfunction '{name}' at {file_path}: {e}")
                _module_load_failures[name] = ModuleLoadFailure(
                    module_name=name,
                    file_path=str(file_path),
                    exception_type='SyntaxError',
                    exception_message=str(e)
                )
                continue

            except (AttributeError, TypeError) as e:
                # Attribute or type issues during module inspection
                log.error(f"Attribute/Type error loading testfunction '{name}' from {file_path}: {e}")
                _module_load_failures[name] = ModuleLoadFailure(
                    module_name=name,
                    file_path=str(file_path),
                    exception_type=type(e).__name__,
                    exception_message=str(e)
                )
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

            except ModuleNotFoundError as e:
                # Missing dependency (e.g., pandas, openpyxl)
                log.error(f"Missing dependency loading testfunction '{file.stem}' from {file}: {e}")
                _module_load_failures[file.stem] = ModuleLoadFailure(
                    module_name=file.stem,
                    file_path=str(file),
                    exception_type='ModuleNotFoundError',
                    exception_message=str(e)
                )
                continue

            except ImportError as e:
                # General import failure
                log.error(f"Import error loading testfunction '{file.stem}' from {file}: {e}")
                _module_load_failures[file.stem] = ModuleLoadFailure(
                    module_name=file.stem,
                    file_path=str(file),
                    exception_type='ImportError',
                    exception_message=str(e)
                )
                continue

            except SyntaxError as e:
                # Code syntax error
                log.error(f"Syntax error in testfunction '{file.stem}' at {file}: {e}")
                _module_load_failures[file.stem] = ModuleLoadFailure(
                    module_name=file.stem,
                    file_path=str(file),
                    exception_type='SyntaxError',
                    exception_message=str(e)
                )
                continue

            except (AttributeError, TypeError) as e:
                # Attribute or type issues during module inspection
                log.error(f"Attribute/Type error loading testfunction '{file.stem}' from {file}: {e}")
                _module_load_failures[file.stem] = ModuleLoadFailure(
                    module_name=file.stem,
                    file_path=str(file),
                    exception_type=type(e).__name__,
                    exception_message=str(e)
                )
                continue
    else:
        raise ValueError("Either 'source' or 'directory' parameter must be provided")

    return testdict


def get_testclass_from_testfunction(testfunction: str, testfunction_collection: dict):
    """
    Get test class from testfunction collection.

    Returns None if testfunction module or function not found.
    Handles both 'standard.function' and 'function' formats.
    """
    if '.' not in testfunction:
        # No prefix - assume standard collection
        standard_collection = testfunction_collection.get('standard', {})
        return standard_collection.get(testfunction)

    # Has prefix - split and lookup
    testfunction_list, testfunction_name = testfunction.split('.', 1)

    # Defensive lookup - use .get() to avoid KeyError
    collection = testfunction_collection.get(testfunction_list)
    if collection is None:
        # Collection not found - check if it failed to load
        if testfunction_list in _module_load_failures:
            failure = _module_load_failures[testfunction_list]
            log.error(f"Testfunction collection '{testfunction_list}' is unavailable: {failure.get_user_friendly_message()}")
        else:
            log.error(f"Testfunction collection '{testfunction_list}' not found in available collections: {list(testfunction_collection.keys())}")
        return None

    return collection.get(testfunction_name)


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

