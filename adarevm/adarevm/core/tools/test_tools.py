"""
Test tool methods for AdareVMServer.

Provides testfunction upload, variable management, and test execution
capabilities for the VM guest agent.
"""

from __future__ import annotations

import base64
import binascii
import json
import logging
import shutil
import tempfile
from pathlib import Path
from typing import Any, Dict, TYPE_CHECKING

if TYPE_CHECKING:
    pass

from adarelib.websocket.protocol import EventType

log = logging.getLogger(__name__)


class TestToolsMixin:
    """Mixin providing test management tool methods."""

    async def _upload_testfunctions(self, websocket, testfunctions_data: str):
        """Upload testfunction files."""
        await self.send_event(websocket, EventType.LOG, {"message": "Uploading testfunctions"})

        try:
            # Decode base64 data
            zip_data = base64.b64decode(testfunctions_data)

            # Create temporary directory
            self.testfunctions_dir = Path(tempfile.mkdtemp(prefix="adare_testfunctions_"))

            # Write and extract zip
            zip_path = self.testfunctions_dir / "testfunctions.zip"
            with open(zip_path, 'wb') as f:
                f.write(zip_data)

            shutil.unpack_archive(zip_path, self.testfunctions_dir)
            zip_path.unlink()

            await self.send_event(websocket, EventType.LOG, {
                "message": f"Testfunctions uploaded to {self.testfunctions_dir}"
            })

            return {
                "status": "success",
                "message": f"Testfunctions uploaded to {self.testfunctions_dir}",
                "path": str(self.testfunctions_dir)
            }

        except binascii.Error as e:
            log.error(f"Invalid base64 data: {e}")
            await self.send_event(websocket, EventType.ERROR, {"message": f"Invalid base64 data: {e}"})
            return {"status": "error", "message": f"Invalid base64 data: {e}"}
        except (OSError, FileNotFoundError) as e:
            log.error(f"File operation failed: {e}")
            await self.send_event(websocket, EventType.ERROR, {"message": f"File operation failed: {e}"})
            return {"status": "error", "message": f"File operation failed: {e}"}
        except shutil.ReadError as e:
            log.error(f"Archive extraction failed: {e}")
            await self.send_event(websocket, EventType.ERROR, {"message": f"Archive extraction failed: {e}"})
            return {"status": "error", "message": f"Archive extraction failed: {e}"}
        except Exception as e:
            log.error(f"Unexpected upload error: {e}", exc_info=True)
            await self.send_event(websocket, EventType.ERROR, {"message": f"Upload failed: {e}"})
            return {"status": "error", "message": str(e)}

    async def _set_variables(self, websocket, variables: str):
        """Set variables for test execution."""
        log.info(f"Setting variables: {variables[:100]}...")
        try:
            new_variables = json.loads(variables)
            self.current_variables.update(new_variables)

            await self.send_event(websocket, EventType.LOG, {
                "message": f"Set {len(new_variables)} variables"
            })

            return {
                "status": "success",
                "message": f"Set {len(new_variables)} variables",
                "variables": self.current_variables
            }
        except json.JSONDecodeError as e:
            log.error(f"Invalid JSON in variables: {e}")
            await self.send_event(websocket, EventType.ERROR, {"message": f"Invalid JSON format: {e}"})
            return {"status": "error", "message": f"Invalid JSON format: {e}"}
        except Exception as e:
            log.error(f"Unexpected variable setting error: {e}", exc_info=True)
            await self.send_event(websocket, EventType.ERROR, {"message": f"Variable setting failed: {e}"})
            return {"status": "error", "message": str(e)}

    def _execute_resolved_test_data(self, resolved_test_data: Dict[str, Any]) -> Dict[str, Any]:
        """Execute a test using pre-resolved test data."""
        log.info(f"CLAUDE: Starting test execution with resolved_test_data: {resolved_test_data}")

        try:
            # Validate resolved_test_data is not None
            if resolved_test_data is None:
                error_msg = "No test data provided - resolved_test_data is None"
                log.error(error_msg)
                # This is a system error, not a test failure
                from adarelib.event.event import TestResult
                from adarelib.constants import StatusEnum
                return TestResult.error([error_msg])

            # Check if testfunctions directory is available
            if not self.testfunctions_dir or not self.testfunctions_dir.exists():
                error_msg = "No testfunctions directory available. Please upload testfunctions first."
                log.error(error_msg)
                # This is a system error, not a test failure
                from adarelib.event.event import TestResult
                from adarelib.constants import StatusEnum
                return TestResult.error([error_msg])

            # Import test function class based on function name
            from adarelib.testset.testfunction import import_basictest_subclasses, get_testclass_from_testfunction
            from adarelib.event.event import TestResult
            from adarelib.constants import StatusEnum

            try:
                # Load testfunctions ONCE per server instance (cached after first test)
                if self._testfunction_cache is None:
                    log.info("Discovering testfunctions (first test execution)...")
                    import time
                    start_time = time.time()

                    # Clear any previous load failures before importing
                    from adarelib.testset.testfunction import clear_module_load_failures
                    clear_module_load_failures()

                    self._testfunction_cache = import_basictest_subclasses(directory=self.testfunctions_dir)

                    elapsed = time.time() - start_time
                    log.info(
                        f"Loaded {len(self._testfunction_cache)} testfunction modules "
                        f"in {elapsed:.2f}s (cached for subsequent tests)"
                    )

                    # Check if any modules failed to load
                    from adarelib.testset.testfunction import get_module_load_failures
                    load_failures = get_module_load_failures()

                    if load_failures:
                        log.warning(f"Some testfunction modules failed to load: {list(load_failures.keys())}")
                        for name, failure in load_failures.items():
                            log.warning(f"  - {failure.get_user_friendly_message()}")
                        # Continue execution - the specific test might not need the failed module

                supported_tests = self._testfunction_cache

            except ModuleNotFoundError as e:
                log.error(f"Critical error: Missing required module for testfunction loading: {e}", exc_info=True)
                return TestResult.execution_error(e, "Missing required module for testfunction system")

            except ImportError as e:
                log.error(f"Critical import error during testfunction loading: {e}", exc_info=True)
                return TestResult.execution_error(e, "Failed to import testfunction system")

            except (OSError, FileNotFoundError) as e:
                log.error(f"File system error loading testfunctions: {e}", exc_info=True)
                return TestResult.execution_error(e, "File system error loading testfunctions")

            function_name = resolved_test_data.get('function')
            if not function_name:
                return TestResult.error(["No test function specified"])

            # Get test class using the proper helper function
            test_class = get_testclass_from_testfunction(function_name, supported_tests)
            if not test_class:
                # Check if this is due to a failed module load
                from adarelib.testset.testfunction import get_module_load_failures

                if '.' in function_name:
                    collection_name = function_name.split('.', 1)[0]
                else:
                    collection_name = 'standard'

                load_failures = get_module_load_failures()
                if collection_name in load_failures:
                    failure = load_failures[collection_name]
                    error_msg = f"Test function '{function_name}' unavailable: {failure.get_user_friendly_message()}"
                    log.error(error_msg)

                    # Extract dependency name for hint
                    hint_lines = [error_msg]
                    if failure.exception_type == 'ModuleNotFoundError':
                        import re
                        match = re.search(r"No module named '([^']+)'", failure.exception_message)
                        if match:
                            dep_name = match.group(1)
                            hint_lines.append(f"Install missing dependency: uv add {dep_name}")
                            hint_lines.append(f"Or run experiment with dependency auto-installation enabled")

                    return TestResult.error(hint_lines)
                else:
                    available_functions = []
                    for coll_name, coll_funcs in supported_tests.items():
                        for func_name in coll_funcs.keys():
                            available_functions.append(f"{coll_name}.{func_name}")

                    return TestResult.error([
                        f"Test function '{function_name}' not found",
                        f"Available: {', '.join(sorted(available_functions)[:10])}{'...' if len(available_functions) > 10 else ''}"
                    ])

            # Create test instance with required arguments
            test_name = resolved_test_data.get('name', 'unknown_test')
            test_description = resolved_test_data.get('description', '')

            # No complex timestamp processing - use resolved test data as-is
            processed_test_data = resolved_test_data

            try:
                # Create proper parameter instance using the test class's parameter class
                parameter_instance = None
                if 'parameter' in processed_test_data:
                    # Get parameter class from the test class's type annotations
                    import typing
                    type_hints = typing.get_type_hints(test_class)

                    if 'parameter' not in type_hints:
                        return TestResult.error([f"No parameter type annotation found for {test_class.__name__}"])

                    parameter_class = type_hints['parameter']
                    parameter_instance = parameter_class(**processed_test_data['parameter'])

                variable_metadata = processed_test_data.get('_VARIABLE_METADATA', {})
                log.info(f"CLAUDE: Creating test instance with variable_metadata: {variable_metadata}")

                test_instance = test_class(
                    name=test_name,
                    parameter=parameter_instance,
                    description=test_description,
                    variable_metadata=variable_metadata
                )
            except Exception as e:
                log.error(f"Error creating test instance: {e}", exc_info=True)
                return TestResult.execution_error(e, f"Failed to create test instance for {function_name}")

            # Execute the test - this returns a TestResult object
            try:
                test_result = test_instance.test()
                if test_result is None:
                    return TestResult.error(["Test returned None result"])
                return test_result
            except Exception as e:
                # Test execution threw an exception - this is an ERROR, not a FAILED test
                log.error(f"Test execution threw exception: {e}")
                return TestResult.execution_error(e, f"Test {test_name} threw exception during execution")

        except Exception as e:
            # System-level exception during test setup/teardown
            log.error(f"System error executing resolved test data: {e}")
            from adarelib.event.event import TestResult
            return TestResult.execution_error(e, "System error during test execution")

    async def _run_test(self, websocket, test_name: str, resolved_test_data: dict):
        """Run a test with pre-resolved test data (variables already substituted)."""
        from adarevm.testing.testset import TestsetExecutionError
        log.info(f"Running test: {test_name}")
        log.debug(f"Test '{test_name}' resolved_test_data: {resolved_test_data}")
        try:
            await self.send_event(websocket, EventType.TEST_START, {"test_name": test_name})

            # Execute test with resolved data by creating temporary test instance
            test_result = self._execute_resolved_test_data(resolved_test_data)

            # Use TestResultLogger to handle logging and formatting
            from adarevm.testing.result_logger import TestResultLogger
            TestResultLogger.log_test_result(test_name, test_result)
            result_data = TestResultLogger.format_result_for_response(test_name, test_result)

            await self.send_event(websocket, EventType.TEST_COMPLETE, {"test_name": test_name})
            log.info(f"Test execution completed: {test_name}")

            return {"status": "success", "message": f"Test '{test_name}' executed", "result": result_data}

        except TestsetExecutionError as e:
            log.error(f"Test execution error: {test_name}: {e}")
            await self.send_event(websocket, EventType.TEST_FAILED, {
                "test_name": test_name, "error": str(e)
            })
            return {"status": "error", "message": f"Test execution failed: {e}"}
        except Exception as e:
            log.error(f"Unexpected test error: {test_name}: {e}", exc_info=True)
            await self.send_event(websocket, EventType.TEST_FAILED, {
                "test_name": test_name, "error": str(e)
            })
            return {"status": "error", "message": str(e)}
