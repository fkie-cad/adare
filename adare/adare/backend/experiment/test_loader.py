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
    
    async def load_tests(self, websocket_client):
        """
        Load testfunctions and testset for use during playbook execution.
        
        Args:
            websocket_client: WebSocket client for uploading testfunctions
        """
        log.info("Loading testfunctions and testset...")
        
        # First, install dependencies for testfunctions
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
            except Exception as e:
                log.error(f"Failed to install testfunction dependencies: {e}")
                # Continue anyway - some tests might still work
        else:
            log.debug("No testfunction dependencies to install")
        
        # Upload testfunctions directory (Python classes) from project directory
        testfunctions_path = self.project_dir / "testfunctions"
        if testfunctions_path.exists():
            log.info("Uploading testfunctions...")
            try:
                await websocket_client.upload_testfunctions(testfunctions_path)
            except Exception as e:
                log.error(f"Failed to upload testfunctions: {e}")
        else:
            log.warning("No testfunctions directory found")
        
        # Individual tests are sent via WebSocket when executed
        # No need to upload entire testset file to VM
    
    def _collect_testfunction_dependencies(self) -> List[str]:
        """Collect all dependencies from loaded testfunctions in the project."""
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
                log.info(f"Collected {len(dependencies_list)} unique dependencies: {dependencies_list}")
            else:
                log.debug("No dependencies found in testfunctions")
            
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
                    
                    # After processing, check if variable registry now has placeholder metadata
                    if (hasattr(self.playbook, 'variables') and self.playbook.variables and
                        hasattr(self.playbook.variables, '_placeholder_metadata') and 
                        self.playbook.variables._placeholder_metadata):
                        resolved_test['_VARIABLE_METADATA'] = self.playbook.variables._placeholder_metadata
                        log.info(f"Added variable metadata to resolved test: {list(self.playbook.variables._placeholder_metadata.keys())}")
                    else:
                        log.debug("No placeholder metadata found after template processing")
                    
                    log.debug(f"Resolved test '{test_name}' data: {resolved_test}")
                    return resolved_test
            
            return None
        except Exception as e:
            log.error(f"Failed to resolve test '{test_name}' locally: {e}")
            return None
    
    def _resolve_test_content(self, test_data: Dict[str, Any]) -> Dict[str, Any]:
        """Enhanced test content resolution using unified variable resolver."""
        if not self.variable_resolver:
            log.warning("No variable resolver available, returning test data as-is")
            return test_data
        
        variable_registry = getattr(self.playbook, 'variables', None) if hasattr(self, 'playbook') else None
        
        # Create enhanced resolver with Jinja environment
        jinja_env = self._create_jinja_environment()
        template_context = self.variable_resolver.get_formatted_context(for_tests=True)
        
        # Single call handles everything - YAML tags AND Jinja templates
        resolver = self.variable_resolver.__class__(
            variable_registry=variable_registry, 
            jinja_env=jinja_env
        )
        
        resolved_test = resolver.process_data(test_data, template_context)
        
        # Add metadata to resolved test
        metadata = resolver.get_placeholder_metadata()
        if metadata:
            resolved_test['_VARIABLE_METADATA'] = metadata
            log.info(f"Added unified variable metadata: {list(metadata.keys())}")
        
        log.debug(f"Unified resolver completed processing")
        
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
        except Exception as e:
            log.warning(f"Failed to replace variables in test text '{text}': {e}")
            return text
    
    def _is_test_action_result(self, action_result) -> bool:
        """Check if an action result corresponds to a test execution."""
        if hasattr(action_result, 'data') and action_result.data and isinstance(action_result.data, dict):
            # Check if this was a test action by looking at the result data structure
            result_data = action_result.data.get('result', {})
            return 'status' in result_data and 'details' in result_data
        return False