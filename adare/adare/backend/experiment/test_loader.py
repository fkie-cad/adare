"""
Test Loader for Playbook Controller

This module handles loading and resolution of tests from playbooks, providing
clean separation of test loading logic from action execution.
"""

import logging
from typing import Dict, List, Optional, Any
from pathlib import Path
import yaml
import jinja2

log = logging.getLogger(__name__)


class TestLoader:
    """
    Handles loading and local resolution of tests from playbooks.
    
    This class contains all test loading and resolution logic that was previously
    in PlaybookController, providing clean separation of concerns.
    """
    
    def __init__(self, experiment_dir: Path, project_dir: Path, playbook = None, 
                 variable_resolver = None):
        """
        Initialize the test loader.
        
        Args:
            experiment_dir: Path to experiment directory
            project_dir: Path to project directory (for testfunctions)
            playbook: Playbook reference for variable access
            variable_resolver: Variable resolver for template processing
        """
        self.experiment_dir = experiment_dir
        self.project_dir = project_dir
        self.playbook = playbook
        self.variable_resolver = variable_resolver
    
    async def _install_dependencies_only(self, websocket_client):
        """
        Install only testfunction dependencies without uploading files.

        Args:
            websocket_client: WebSocket client for installing dependencies
        """
        log.info("Installing testfunction dependencies...")

        dependencies = self._collect_testfunction_dependencies()
        if dependencies:
            log.info(f"Installing {len(dependencies)} testfunction dependencies in VM...")
            try:
                result = await websocket_client.install_testfunction_dependencies(dependencies)
                if result.get("status") != "success":
                    log.error(f"Failed to install dependencies: {result.get('message')}")
                    # Continue anyway - some tests might still work
                else:
                    log.info("Successfully installed all testfunction dependencies")
            except (OSError, subprocess.SubprocessError, ConnectionError) as e:
                log.error(f"Failed to install testfunction dependencies: {e}")
                # Continue anyway - some tests might still work
            except Exception as e:
                log.error(f"Unexpected error installing testfunction dependencies: {e}", exc_info=True)
                # Continue anyway - some tests might still work
        else:
            log.debug("No testfunction dependencies to install")

    async def load_tests(self, websocket_client):
        """
        Load testfunctions and testset for use during playbook execution.
        Note: Dependencies should already be installed by this point.

        Args:
            websocket_client: WebSocket client for uploading testfunctions
        """
        log.info("Loading testfunctions and testset...")

        # Dependencies should already be installed, just note that here
        log.debug("Skipping dependency installation (should already be done)")
        
        # Upload only testfunctions that are actually used in the playbook
        from adare.config.configdirectory import STATE_DIR
        global_testfunctions_path = STATE_DIR / 'testfunctions'

        if global_testfunctions_path.exists():
            # Extract which testfunctions are used in the playbook
            used_function_names = self._extract_used_testfunction_names()

            if used_function_names:
                # Map function names to their file paths
                required_files = self._get_testfunction_files_for_functions(used_function_names)

                if required_files:
                    log.info(f"Uploading {len(required_files)} testfunction files for functions: {sorted(used_function_names)}")
                    try:
                        await websocket_client.upload_testfunctions(global_testfunctions_path, required_files)
                    except (OSError, IOError) as e:
                        log.error(f"Failed to upload testfunctions due to file system error: {e}")
                    except (ValueError, TypeError) as e:
                        log.error(f"Failed to upload testfunctions due to invalid data: {e}")
                else:
                    log.warning("No testfunction files found for the used functions - uploading nothing")
            else:
                log.info("No testfunctions used in playbook - skipping testfunction upload")
        else:
            log.warning(f"Global testfunctions directory not found: {global_testfunctions_path}")
            log.info("Load testfunctions using 'adare testfunction load-global <path>' to enable testfunction uploads")
        
        # Individual tests are sent via WebSocket when executed
        # No need to upload entire testset file to VM
    
    def _collect_testfunction_dependencies(self) -> List[str]:
        """Collect dependencies only from testfunctions actually used in the playbook."""
        dependencies = set()

        try:
            # First, determine which testfunctions are actually used
            used_function_names = self._extract_used_testfunction_names()
            if not used_function_names:
                log.debug("No testfunctions used in playbook - no dependencies needed")
                return []

            # Get the files that contain these functions
            required_files = self._get_testfunction_files_for_functions(used_function_names)
            if not required_files:
                log.debug("No testfunction files mapped - no dependencies needed")
                return []

            log.debug(f"Collecting dependencies only for files: {[f.name for f in required_files]}")

            # Read requirements files only for the required testfunction files
            for testfunction_file in required_files:
                # Construct requirements file path (should be in same directory)
                requirements_file = testfunction_file.parent / "requirements.txt"
                if requirements_file.exists():
                    log.debug(f"Reading requirements from: {requirements_file}")
                    try:
                        content = requirements_file.read_text().strip()
                        if content:
                            # Parse requirements.txt format
                            for line in content.splitlines():
                                line = line.strip()
                                # Skip comments and empty lines
                                if line and not line.startswith('#'):
                                    dependencies.add(line)
                    except (OSError, IOError, UnicodeDecodeError) as e:
                        log.warning(f"Failed to read requirements from {requirements_file}: {e}")

            dependencies_list = list(dependencies)
            if dependencies_list:
                log.info(f"Collected {len(dependencies_list)} unique dependencies for used testfunctions: {dependencies_list}")
            else:
                log.debug("No dependencies found in used testfunction files")

            return dependencies_list

        except (ImportError, ModuleNotFoundError, SyntaxError, FileNotFoundError) as e:
            log.error(f"Failed to collect testfunction dependencies: {e}")
            # Fallback to collecting all dependencies if there's an error
            return self._collect_all_testfunction_dependencies()
        except Exception as e:
            log.error(f"Unexpected error collecting testfunction dependencies: {e}", exc_info=True)
            # Fallback to collecting all dependencies if there's an error
            return self._collect_all_testfunction_dependencies()

    def _collect_all_testfunction_dependencies(self) -> List[str]:
        """Fallback: collect all dependencies from all testfunctions in the project (original behavior)."""
        dependencies = set()

        try:
            # Get testfunction data from database for this project
            from adare.backend.testfunction.database import get_testfunction_files_data
            testfunction_files = get_testfunction_files_data(
                project_path=self.project_dir,
                fields=['requirements_path']
            )

            # Read each requirements file and collect dependencies
            for tf_data in testfunction_files:
                requirements_path = tf_data.get('requirements_path')
                if requirements_path:
                    req_file = Path(requirements_path)
                    if req_file.exists():
                        log.debug(f"Reading requirements from: {req_file}")
                        try:
                            content = req_file.read_text().strip()
                            if content:
                                # Parse requirements.txt format
                                for line in content.splitlines():
                                    line = line.strip()
                                    # Skip comments and empty lines
                                    if line and not line.startswith('#'):
                                        dependencies.add(line)
                        except (OSError, IOError, UnicodeDecodeError) as e:
                            log.warning(f"Failed to read requirements from {req_file}: {e}")

            dependencies_list = list(dependencies)
            if dependencies_list:
                log.info(f"Collected {len(dependencies_list)} unique dependencies (fallback - all files): {dependencies_list}")
            else:
                log.debug("No dependencies found in any testfunctions (fallback)")

            return dependencies_list

        except ImportError as e:
            log.error(f"Failed to import testfunction database module: {e}")
            return []

    async def resolve_test_locally(self, test_name: str) -> Optional[Dict[str, Any]]:
        """Load and resolve a specific test locally with variable substitution."""
        try:
            # Load tests from playbook instead of separate testset file
            playbook_path = self.experiment_dir / "playbook.yml"
            if not playbook_path.exists():
                return None
            
            from adarelib.testset.yaml.customloader import get_custom_loader
            playbook_yaml = playbook_path.read_text()
            playbook_data = yaml.load(playbook_yaml, Loader=get_custom_loader())
            
            if 'tests' not in playbook_data:
                return None
            
            # Get execution context for test resolution
            if self.variable_resolver:
                formatted_context = self.variable_resolver.get_formatted_context(for_tests=True)
            else:
                formatted_context = {}
            
            log.debug(f"Resolving test '{test_name}' with execution context keys: {list(formatted_context.keys())}")
            log.debug(f"Execution context values: {formatted_context}")
            
            # Find the test by name
            for test in playbook_data['tests']:
                if test.get('name') == test_name:
                    log.debug(f"Found test '{test_name}' raw data: {test}")
                    # Apply variable substitution to all string values in the test
                    resolved_test = self._resolve_test_content(test)
                    
                    # Metadata is now handled by the unified resolver in _resolve_test_content
                    
                    log.debug(f"Resolved test '{test_name}' data: {resolved_test}")
                    return resolved_test
            
            return None
        except (ImportError, ModuleNotFoundError, AttributeError, SyntaxError) as e:
            log.error(f"Failed to resolve test '{test_name}' locally: {e}")
            return None
        except Exception as e:
            log.error(f"Unexpected error resolving test '{test_name}' locally: {e}", exc_info=True)
            return None

    async def resolve_test_with_runtime_context(self, test_name: str, runtime_execution_context: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Load and resolve a specific test with runtime execution context for variables set during action execution."""
        try:
            # Load tests from playbook
            playbook_path = self.experiment_dir / "playbook.yml"
            if not playbook_path.exists():
                return None

            from adarelib.testset.yaml.customloader import get_custom_loader
            playbook_yaml = playbook_path.read_text()
            playbook_data = yaml.load(playbook_yaml, Loader=get_custom_loader())

            if 'tests' not in playbook_data:
                return None

            # Get combined execution context (existing + runtime)
            if self.variable_resolver:
                base_context = self.variable_resolver.get_formatted_context(for_tests=True)
            else:
                base_context = {}

            # Merge with runtime context (runtime context takes precedence)
            combined_context = {**base_context, **runtime_execution_context}

            log.info(f"Resolving test '{test_name}' with runtime context. Base context keys: {list(base_context.keys())}, Runtime context keys: {list(runtime_execution_context.keys())}")
            log.info(f"Combined context: {combined_context}")

            # Find the test by name
            for test in playbook_data['tests']:
                if test.get('name') == test_name:
                    log.debug(f"Found test '{test_name}' raw data: {test}")

                    # Re-process with variable resolver using runtime context
                    if self.variable_resolver:
                        # Re-run the full variable resolution process with runtime context
                        resolved_test = self.variable_resolver.process_data(test, combined_context)
                        log.info(f"Re-processed test '{test_name}' with variable resolver and runtime context")
                        log.debug(f"Resolved test data: {resolved_test}")

                        # Also capture any new metadata generated
                        metadata = self.variable_resolver.get_placeholder_metadata()
                        if metadata:
                            resolved_test['_VARIABLE_METADATA'] = metadata
                            log.info(f"Generated metadata during runtime resolution: {list(metadata.keys())}")

                        return resolved_test
                    else:
                        log.warning("No variable resolver available for runtime resolution")
                        return test

            return None
        except (ImportError, ModuleNotFoundError, AttributeError, SyntaxError) as e:
            log.error(f"Failed to resolve test '{test_name}' with runtime context: {e}")
            return None
        except Exception as e:
            log.error(f"Unexpected error resolving test '{test_name}' with runtime context: {e}", exc_info=True)
            return None

    def _resolve_test_content(self, test_data: Dict[str, Any]) -> Dict[str, Any]:
        """Enhanced test content resolution using unified variable resolver with lazy loading."""
        if not self.variable_resolver:
            log.warning("No variable resolver available, returning test data as-is")
            return test_data

        variable_registry = getattr(self.playbook, 'variables', None) if hasattr(self, 'playbook') else None

        # Extract variables that are actually referenced in this test
        referenced_variables = set()
        if variable_registry:
            referenced_variables = variable_registry.extract_referenced_variables(test_data)
            log.debug(f"Test '{test_data.get('name', 'unknown')}' references variables: {referenced_variables}")

        # Create enhanced resolver with Jinja environment
        jinja_env = self._create_jinja_environment()

        # Use lazy context - only process variables that are actually referenced
        if variable_registry and referenced_variables:
            template_context = variable_registry.to_execution_context_lazy(referenced_variables, for_tests=True)
            log.debug(f"Using lazy context with {len(template_context)} variables")
        else:
            # Fallback to empty context if no variables referenced
            template_context = {}
            log.debug("No variables referenced, using empty context")

        # Single call handles everything - YAML tags AND Jinja templates
        resolver = self.variable_resolver.__class__(
            variable_registry=variable_registry,
            jinja_env=jinja_env
        )

        resolved_test = resolver.process_data(test_data, template_context)

        # Add metadata to resolved test (now only contains metadata for referenced variables)
        metadata = resolver.get_placeholder_metadata()
        if metadata:
            resolved_test['_VARIABLE_METADATA'] = metadata
            log.info(f"Added lazy variable metadata: {list(metadata.keys())}")

        log.debug(f"Lazy resolver completed processing")

        return resolved_test
    
    def _create_jinja_environment(self):
        """Create Jinja environment with all necessary filters."""
        # Get filters from variable registry if available
        filters = {}
        if hasattr(self.playbook, 'variables') and self.playbook.variables:
            from adarelib.common.variables import TimestampMetadata
            metadata = TimestampMetadata()  # Create temp metadata object
            filters.update(metadata.get_jinja_filters(self.playbook.variables))
        
        env = jinja2.Environment()
        env.filters.update(filters)
        log.debug(f"Created Jinja environment with filters: {list(filters.keys())}")
        return env
    
    def _resolve_test_content_recursive(self, test_data: Any) -> Any:
        """Recursively apply variable substitution without re-processing YAML custom tags."""
        if isinstance(test_data, dict):
            return {key: self._resolve_test_content_recursive(value) for key, value in test_data.items()}
        elif isinstance(test_data, list):
            return [self._resolve_test_content_recursive(item) for item in test_data]
        elif isinstance(test_data, str):
            return self._replace_variables_for_tests(test_data)
        else:
            return test_data
    
    def _extract_used_testfunction_names(self) -> set[str]:
        """Extract all testfunction names used in the current playbook."""
        try:
            playbook_path = self.experiment_dir / "playbook.yml"
            if not playbook_path.exists():
                log.warning("No playbook.yml found, cannot extract testfunction names")
                return set()

            from adarelib.testset.yaml.customloader import get_custom_loader
            playbook_yaml = playbook_path.read_text()
            playbook_data = yaml.load(playbook_yaml, Loader=get_custom_loader())

            if 'tests' not in playbook_data:
                log.debug("No tests section in playbook")
                return set()

            used_functions = set()
            for test in playbook_data['tests']:
                if 'function' in test:
                    function_name = test['function']
                    used_functions.add(function_name)
                    log.debug(f"Found testfunction usage: {function_name}")

            log.info(f"Extracted {len(used_functions)} unique testfunction names from playbook: {sorted(used_functions)}")
            return used_functions

        except (OSError, IOError, UnicodeDecodeError) as e:
            log.error(f"Failed to read playbook file: {e}")
            return set()
        except (yaml.YAMLError, ImportError) as e:
            log.error(f"Failed to parse playbook YAML: {e}")
            return set()
        except (KeyError, TypeError, AttributeError) as e:
            log.error(f"Failed to extract testfunction names from playbook data: {e}")
            return set()

    def _get_testfunction_files_for_functions(self, function_names: set[str]) -> set[Path]:
        """Map testfunction names to their file paths."""
        try:
            from adare.database.api.testfunction import TestfunctionDbApi
            from adare.database.models.global_models import TestFunctionFile

            testfunction_files = set()
            with TestfunctionDbApi() as api:
                # Get all testfunctions grouped by file
                testfunctions_by_file = api.get_testfunctions_by_file()

                for file_name, testfunctions in testfunctions_by_file.items():
                    for testfunction in testfunctions:
                        # Check for exact match first
                        if testfunction['name'] in function_names:
                            # Find the actual file path for this testfunction file
                            testfunction_file_obj = api._session.query(TestFunctionFile).filter_by(name=file_name).first()
                            if testfunction_file_obj:
                                file_path = Path(testfunction_file_obj.path)
                                testfunction_files.add(file_path)
                                log.debug(f"Mapped function '{testfunction['name']}' to file: {file_path}")
                            break

                        # Check for unprefixed standard functions (e.g., 'file_exists' should match 'standard.file_exists')
                        if '.' in testfunction['name']:
                            collection, func_name = testfunction['name'].split('.', 1)
                            if collection == 'standard' and func_name in function_names:
                                # Find the actual file path for this testfunction file
                                testfunction_file_obj = api._session.query(TestFunctionFile).filter_by(name=file_name).first()
                                if testfunction_file_obj:
                                    file_path = Path(testfunction_file_obj.path)
                                    testfunction_files.add(file_path)
                                    log.debug(f"Mapped unprefixed function '{func_name}' to standard file: {file_path}")
                                break

            log.info(f"Mapped {len(function_names)} functions to {len(testfunction_files)} files: {[f.name for f in testfunction_files]}")
            return testfunction_files

        except (ImportError, AttributeError) as e:
            log.error(f"Failed to import or access testfunction database API: {e}")
            return set()
        except (KeyError, ValueError) as e:
            log.error(f"Database query or data processing error: {e}")
            return set()
        except OSError as e:
            log.error(f"File system error while mapping testfunction files: {e}")
            return set()

    def _replace_variables_for_tests(self, text: str) -> str:
        """Replace variables in test content using test-aware context with smart resolution."""
        if not text or '{{' not in text:
            return text

        # Skip processing our variable resolver placeholders - they should stay as placeholders
        if '_resolved' in text and '{{' in text and '}}' in text:
            # Check if this looks like one of our placeholders (regex_N_resolved, timestamp_N_resolved, etc.)
            import re
            if re.match(r'^\{\{\s*(regex|timestamp)_\d+_resolved\s*\}\}$', text.strip()):
                log.debug(f"Skipping variable replacement for placeholder: '{text}'")
                return text

        try:
            if not self.variable_resolver:
                log.warning(f"No variable resolver available for test template: '{text}'")
                return text

            # Use test-aware context that creates placeholders for variables with test-specific filters
            formatted_context = self.variable_resolver.get_formatted_context(for_tests=True)

            log.debug(f"Processing test template: '{text}' with context keys: {list(formatted_context.keys())}")
            template = jinja2.Template(text)

            # Add custom filters for metadata capture
            custom_filters = self.variable_resolver.get_custom_filters() if hasattr(self.variable_resolver, 'get_custom_filters') else {}
            template.environment.filters.update(custom_filters)

            result = template.render(formatted_context)
            log.debug(f"Test template result: '{result}'")

            return result
        except (ValueError, TypeError, KeyError) as e:
            log.warning(f"Failed to replace variables in test text '{text}': {e}")
            return text
        except Exception as e:
            log.warning(f"Unexpected error replacing variables in test text '{text}': {e}", exc_info=True)
            return text
    
    def _is_test_action_result(self, action_result) -> bool:
        """Check if an action result corresponds to a test execution."""
        if hasattr(action_result, 'data') and action_result.data and isinstance(action_result.data, dict):
            # Check if this was a test action by looking at the result data structure
            result_data = action_result.data.get('result', {})
            return 'status' in result_data and 'details' in result_data
        return False

    def get_test_class(self, test_name: str) -> Optional[type]:
        """
        Get test class definition for a test by loading from database.

        Args:
            test_name: Name of the test from playbook

        Returns:
            Test class type or None if not found
        """
        try:
            # Load test definition to get function name
            playbook_path = self.experiment_dir / "playbook.yml"
            if not playbook_path.exists():
                log.warning(f"Playbook not found: {playbook_path}")
                return None

            from adarelib.testset.yaml.customloader import get_custom_loader
            playbook_yaml = playbook_path.read_text()
            playbook_data = yaml.load(playbook_yaml, Loader=get_custom_loader())

            if 'tests' not in playbook_data:
                return None

            # Find test by name
            test_function = None
            for test in playbook_data['tests']:
                if test.get('name') == test_name:
                    test_function = test.get('function')
                    break

            if not test_function:
                log.warning(f"Test '{test_name}' not found in playbook")
                return None

            # Load testfunction classes from database
            from adare.config.configdirectory import STATE_DIR
            from adarelib.testset.testfunction import import_basictest_subclasses

            global_testfunctions_path = STATE_DIR / 'testfunctions'
            if not global_testfunctions_path.exists():
                log.warning(f"Global testfunctions not found: {global_testfunctions_path}")
                return None

            # Import testfunction classes
            testfunction_collection = import_basictest_subclasses(directory=global_testfunctions_path)

            # Get test class from collection
            from adarelib.testset.testfunction import get_testclass_from_testfunction
            test_class = get_testclass_from_testfunction(test_function, testfunction_collection)

            return test_class

        except (OSError, IOError, yaml.YAMLError) as e:
            log.error(f"Failed to load test class for '{test_name}': {e}")
            return None
        except Exception as e:
            log.error(f"Unexpected error loading test class for '{test_name}': {e}", exc_info=True)
            return None

    async def structure_host_test(self, test_name: str, resolved_test: Dict[str, Any]):
        """
        Structure test instance for host execution.

        This method takes a resolved test dict and converts it to a
        structured test instance (BasicTest subclass) for host execution.

        Args:
            test_name: Name of the test
            resolved_test: Resolved test dict with substituted variables

        Returns:
            Structured test instance (BasicTest subclass)

        Raises:
            ValueError: If test cannot be structured
        """
        try:
            # Get test class
            test_class = self.get_test_class(test_name)
            if not test_class:
                raise ValueError(f"Test class not found for '{test_name}'")

            # Structure the test using cattrs
            import cattrs
            test_instance = cattrs.structure(resolved_test, test_class)

            log.debug(f"Test Loader: Structured host test '{test_name}' as {test_class.__name__}")
            return test_instance

        except cattrs.errors.ClassValidationError as e:
            log.error(f"Test Loader: Validation error structuring test '{test_name}': {e}")
            raise ValueError(f"Invalid test parameters: {e.message}")
        except Exception as e:
            log.error(f"Test Loader: Failed to structure test '{test_name}': {e}", exc_info=True)
            raise ValueError(f"Failed to structure test: {e}")