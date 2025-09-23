"""
Playbook Controller for WebSocket-based Experiment Execution.

This module provides the main PlaybookController class that orchestrates experiment
execution by coordinating between specialized modules for action execution, event
management, variable resolution, and test loading.
"""

import logging
from pathlib import Path
from typing import Dict, List, Optional, Any
from dataclasses import dataclass
import time

# Playbook and test imports
from adare.types.playbook import (
    parse_playbook, Playbook, ActionType, ActionTestAction, PullAction, PauseAction, SaveTimestampAction
)

# WebSocket client import
from adare.backend.experiment.websocket_client import AdareVMClient

# Target resolution using MCP GUI server
from adare.backend.experiment.target_resolver import MCPTargetResolver, MCPConditionChecker

# Specialized modules for clean separation of concerns
from adare.backend.experiment.action_executor import ActionExecutor, ActionResult
from adare.backend.experiment.event_manager import EventManager
from adare.backend.experiment.variable_resolver import VariableResolver
from adare.backend.experiment.test_loader import TestLoader

# Action event imports for flow console display
from adare.backend.events.emitters import emit_action

# Import playbook analysis utility
from adare.helperfunctions.playbook_analysis import collect_pull_action_files

log = logging.getLogger(__name__)


@dataclass
class PlaybookExecutionResult:
    """Result of complete playbook execution."""
    success: bool
    total_actions: int
    successful_actions: int
    failed_actions: int
    execution_time: float
    action_results: List[ActionResult]
    error_message: Optional[str] = None
    # Test statistics
    total_tests: int = 0
    successful_tests: int = 0
    failed_tests: int = 0


class PlaybookController:
    """
    Controller for executing YAML playbooks via WebSocket.
    
    This controller orchestrates experiment execution by coordinating between
    specialized modules for different aspects of playbook execution.
    """
    
    def __init__(self, websocket_client: AdareVMClient, experiment_dir: Path, project_dir: Path,
                 mcp_gui_url: str = "http://localhost:13109/mcp", debug_screenshots: bool = False,
                 screenshots_dir: Path = None, playbook: Optional[Playbook] = None,
                 experiment_id: Optional[str] = None, experiment_run_id: Optional[str] = None,
                 vm: Optional['VirtualBoxVM'] = None, experiment_run_directory: Optional[Path] = None,
                 vm_os: Optional[str] = None, vm_user: Optional[str] = None, flow_console = None,
                 test_mode: bool = False):
        """
        Initialize the playbook controller.
        
        Args:
            websocket_client: Connected WebSocket client to adarevm
            experiment_dir: Path to experiment directory (for images/)
            project_dir: Path to project directory (for testfunctions/)
            mcp_gui_url: URL of the MCP GUI server for CV/OCR
            debug_screenshots: Whether to save screenshots for debugging
            screenshots_dir: Directory to save debug screenshots
            playbook: Pre-parsed playbook (optional, will parse if not provided)
            experiment_id: Experiment ID for database linking
            experiment_run_id: Experiment run ID for execution tracking
            flow_console: Flow console for interactive display and input
            test_mode: Whether running in test mode (affects test action execution)
        """
        self.client = websocket_client
        self.experiment_dir = experiment_dir
        self.project_dir = project_dir
        self.execution_context = {}
        self.action_results: List[ActionResult] = []
        self.debug_screenshots = debug_screenshots
        self.screenshots_dir = screenshots_dir
        self.playbook = playbook
        self.vm = vm  # VirtualBox VM instance for file operations
        self.experiment_run_directory = experiment_run_directory  # Run directory for artifacts
        self.vm_os = vm_os  # VM OS for automatic variables
        self.vm_user = vm_user  # VM user for automatic variables
        self.flow_console = flow_console  # Flow console for interactive actions
        self.test_mode = test_mode  # Test mode flag
        
        # Database integration
        self.experiment_id = experiment_id
        self.experiment_run_id = experiment_run_id
        self.playbook_items_map: Dict[int, str] = {}  # Maps action index to playbook_item_id
        
        # Initialize playbook items mapping if experiment tracking enabled
        if self.experiment_id:
            self._initialize_playbook_items_mapping()
        
        # Target resolution using MCP GUI server
        self.target_resolver = MCPTargetResolver(experiment_dir, mcp_gui_url, experiment_run_id)
        self.condition_checker = MCPConditionChecker(self.target_resolver)
        
        # Initialize specialized modules
        self._initialize_modules()

        # Performance tracking
        self.start_time: Optional[float] = None
        self.action_timings: Dict[str, float] = {}

        # Auto-pull on test failure tracking
        self._auto_pull_files: List[str] = []
        self._auto_pull_executed: bool = False
    
    def _initialize_modules(self):
        """Initialize specialized modules for clean separation of concerns."""
        # Get variable registry from playbook and add automatic variables
        variable_registry = getattr(self.playbook, 'variables', None) if self.playbook else None

        # Add automatic variables if we have VM information
        if self.vm_os and self.vm_user and variable_registry:
            from adarelib.common.automatic_variables import AutomaticVariables
            automatic_vars = AutomaticVariables.get_automatic_variables(self.vm_os, self.vm_user)
            # Merge automatic variables with existing user variables
            variable_registry = AutomaticVariables.merge_with_user_variables(automatic_vars, variable_registry)
        elif self.vm_os and self.vm_user:
            # No user variables, create registry with just automatic variables
            from adarelib.common.automatic_variables import AutomaticVariables
            variable_registry = AutomaticVariables.get_automatic_variables(self.vm_os, self.vm_user)

        # Variable resolver for template processing
        self.variable_resolver = VariableResolver(
            variable_registry=variable_registry,
            jinja_env=self._create_jinja_environment()
        )
        
        # Event manager for action event creation and emission
        self.event_manager = EventManager(
            experiment_run_id=self.experiment_run_id,
            playbook_items_map=self.playbook_items_map
        )
        
        # Action executor for individual action execution
        self.action_executor = ActionExecutor(
            websocket_client=self.client,
            target_resolver=self.target_resolver,
            condition_checker=self.condition_checker,
            experiment_run_id=self.experiment_run_id,
            playbook=self.playbook,
            execution_context=self.execution_context,
            debug_screenshots=self.debug_screenshots,
            screenshots_dir=self.screenshots_dir,
            vm=self.vm,
            experiment_run_directory=self.experiment_run_directory,
            flow_console=self.flow_console
        )
        
        # Test loader for test loading and resolution
        self.test_loader = TestLoader(
            experiment_dir=self.experiment_dir,
            project_dir=self.project_dir,
            playbook=self.playbook,
            variable_resolver=self.variable_resolver
        )
        
        # Connect test loader to action executor
        self.action_executor.test_loader = self.test_loader
    
    def _create_jinja_environment(self):
        """Create Jinja environment with all necessary filters."""
        import jinja2
        
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
    
    def _initialize_playbook_items_mapping(self):
        """Initialize mapping from action index to playbook_item_id."""
        if not self.experiment_id:
            return
        
        try:
            from adare.database.api.playbook import PlaybookApi
            
            with PlaybookApi() as playbook_api:
                # Get playbook from database
                playbook = playbook_api.get_playbook_by_experiment_id(self.experiment_id)
                if not playbook:
                    log.warning(f"No playbook found for experiment {self.experiment_id}")
                    return
                
                # Get playbook items ordered by sequence
                items = playbook_api.get_playbook_items(playbook.id)
                
                # Map action index to playbook_item_id
                for item in items:
                    self.playbook_items_map[item.sequence_order] = item.id
                    
                log.debug(f"Initialized playbook items mapping: {len(self.playbook_items_map)} items")
            
        except Exception as e:
            log.error(f"Failed to initialize playbook items mapping: {e}")
    
    async def execute_experiment(self, experiment_dir: Path) -> PlaybookExecutionResult:
        """
        Execute complete experiment: playbook actions + tests.
        
        Args:
            experiment_dir: Path to experiment directory
            
        Returns:
            PlaybookExecutionResult with execution summary
        """
        log.info(f"Starting experiment execution in {experiment_dir}")
        self.start_time = time.time()
        
        # 1. Load testfunctions and testset (dependencies should already be installed)
        await self.test_loader.load_tests(self.client)
        
        # 2. Execute playbook actions (can now use loaded tests)
        playbook_path = experiment_dir / "playbook.yml"
        if playbook_path.exists():
            log.info("Executing playbook actions...")
            playbook_result = await self.execute_playbook()
            if not playbook_result.success:
                return playbook_result
        else:
            log.warning("No playbook.yml found, skipping GUI actions")
        
        # Tests are now executed inline during playbook execution via 'test:' actions
        
        execution_time = time.time() - self.start_time
        log.info(f"Experiment completed successfully in {execution_time:.2f}s")
        
        # Count test statistics
        test_results = [r for r in self.action_results if self._is_test_action_result(r)]
        total_tests = len(test_results)
        successful_tests = sum(1 for r in test_results if r.success)
        failed_tests = total_tests - successful_tests
        
        # Count only actions that should be included in execution statistics (exclude utility actions)
        countable_results = [r for r in self.action_results if r.data and r.data.get('is_countable', True)]

        return PlaybookExecutionResult(
            success=True,
            total_actions=len(countable_results),
            successful_actions=sum(1 for r in countable_results if r.success),
            failed_actions=sum(1 for r in countable_results if not r.success),
            execution_time=execution_time,
            action_results=self.action_results,  # Keep all results for debugging/logging
            total_tests=total_tests,
            successful_tests=successful_tests,
            failed_tests=failed_tests
        )
    
    async def execute_playbook(self) -> PlaybookExecutionResult:
        """
        Execute YAML playbook actions in order.
        
        Returns:
            PlaybookExecutionResult with execution details
        """
        playbook = self.playbook
        
        # Set up experiment variables and playbook access
        self.execution_context['playbook'] = playbook
        if hasattr(playbook, 'variables') and playbook.variables:
            log.info("Loading experiment variables...")
            # CLAUDE: Debug what variables are in the registry
            log.info(f"CLAUDE: Variables in registry: {list(playbook.variables.variables.keys())}")
            for name, var in playbook.variables.variables.items():
                log.info(f"CLAUDE: Variable '{name}' = '{var.value}' (type: {var.type})")

            # Convert VariableRegistry to execution context format (for actions - full resolution)
            var_dict = playbook.variables.to_execution_context(for_tests=False)
            log.info(f"CLAUDE: Variables in execution context: {list(var_dict.keys())}")
            self.execution_context.update(var_dict)
            log.debug(f"Loaded {len(playbook.variables.variables)} variables into execution context")
        
        # Collect files to auto-pull on test failure if setting is enabled
        if hasattr(playbook, 'settings') and playbook.settings and playbook.settings.auto_pull_on_test_failure:
            self._auto_pull_files = collect_pull_action_files(playbook)
            if self._auto_pull_files:
                log.info(f"Auto-pull on test failure enabled - collected {len(self._auto_pull_files)} files: {self._auto_pull_files}")
            else:
                log.debug("Auto-pull on test failure enabled but no pull actions found in playbook")

        # Execute actions sequentially
        total_actions = len(playbook.actions)
        log.info(f"Executing {total_actions} playbook actions...")
        
        for i, action in enumerate(playbook.actions):
            action_name = type(action).__name__
            log.info(f"Executing action {i+1}/{total_actions}: {action_name}")

            # Skip pause actions when not in test mode
            if isinstance(action, PauseAction) and not self.test_mode:
                log.info(f"Skipping pause action {action_name} - not running in test mode")
                # Create a successful result to indicate the action was skipped
                skipped_result = ActionResult(
                    success=True,
                    message=f"Pause action skipped (not in test mode)",
                    execution_time=0.0,
                    data={
                        'is_countable': self._is_countable_action(action),
                        'is_test_action': False,
                        'is_utility_action': self._is_utility_action(action),
                        'skipped': True
                    }
                )
                self.action_results.append(skipped_result)
                continue

            # Create database execution record if tracking enabled
            execution_id = None
            if self.experiment_run_id and i in self.playbook_items_map:
                execution_id = await self._create_database_execution_record(i)
            
            # Resolve variables early for consistent display and execution
            resolved_action = self.variable_resolver.resolve_action_variables(action, self.execution_context)
            
            # Create unique action ID for event tracking
            action_id = f"action_{i}_{action_name.lower()}_{int(time.time()*1000)}"
            
            # Emit action start event for flow console display using resolved action
            if self.experiment_run_id:
                try:
                    start_event = self.event_manager.create_action_start_event(resolved_action, i, action_id)
                    emit_action(self.experiment_run_id, start_event, action_id)
                    log.info(f"Emitted start event for action {i}: {action_name}, ID: {action_id}")
                except Exception as e:
                    log.error(f"Failed to emit start event for action {i}: {e}", exc_info=True)
            
            # Execute the action using action executor
            start_time = time.time()
            result = await self.action_executor.execute_action(
                action, 
                parent_event_id=action_id, 
                event_emitter=self.event_manager,
                variable_resolver=self.variable_resolver
            )
            execution_time = time.time() - start_time
            
            result.execution_time = execution_time

            # Add metadata to track if this action should be counted in statistics
            if not result.data:
                result.data = {}
            result.data['is_countable'] = self._is_countable_action(action)
            result.data['is_test_action'] = self._is_test_action(action)
            result.data['is_utility_action'] = self._is_utility_action(action)

            self.action_results.append(result)
            self.action_timings[f"action_{i+1}_{action_name}"] = execution_time
            
            # Emit action complete event for flow console display using resolved action
            if self.experiment_run_id:
                try:
                    complete_event = self.event_manager.create_action_complete_event(resolved_action, i, action_id, result)
                    emit_action(self.experiment_run_id, complete_event, action_id)
                    log.info(f"Emitted complete event for action {i}: {action_name}, Success: {result.success}, ID: {action_id}")
                except Exception as e:
                    log.error(f"Failed to emit complete event for action {i}: {e}", exc_info=True)
            
            # Update database execution record
            if execution_id:
                await self._update_database_execution_record(execution_id, result, execution_time)
            
            if not result.success:
                log.error(f"Action {i+1} failed: {result.message}")
                
                # Check if we should continue on test failure
                should_continue = False
                if self._is_test_action(resolved_action):
                    # This is a test action - check settings
                    if hasattr(playbook, 'settings') and playbook.settings:
                        # Auto-pull files on test failure if enabled
                        if playbook.settings.auto_pull_on_test_failure and self._auto_pull_files and not self._auto_pull_executed:
                            log.info(f"Test failed - triggering auto-pull of {len(self._auto_pull_files)} files")
                            await self._execute_auto_pull()
                            self._auto_pull_executed = True  # Only auto-pull once per execution

                        # Check continue_on_test_failure setting
                        if playbook.settings.continue_on_test_failure:
                            log.info(f"Test action failed but continuing due to continue_on_test_failure setting")
                            should_continue = True

                if not should_continue:
                    # Stop execution after failed action
                    break
            
            # Apply global idle setting
            if hasattr(playbook, 'settings') and playbook.settings and playbook.settings.idle:
                await self.client.idle(playbook.settings.idle)
        
        successful = sum(1 for r in self.action_results if r.success)
        failed = len(self.action_results) - successful
        
        # Count test statistics
        test_results = [r for r in self.action_results if self._is_test_action_result(r)]
        total_tests = len(test_results)
        successful_tests = sum(1 for r in test_results if r.success)
        failed_tests = total_tests - successful_tests
        
        return PlaybookExecutionResult(
            success=failed == 0,
            total_actions=total_actions,
            successful_actions=successful,
            failed_actions=failed,
            execution_time=sum(self.action_timings.values()),
            action_results=self.action_results,
            total_tests=total_tests,
            successful_tests=successful_tests,
            failed_tests=failed_tests
        )
    
    async def _create_database_execution_record(self, action_index: int) -> Optional[str]:
        """Create database execution record for action tracking."""
        try:
            from adare.database.api.playbook import PlaybookApi
            
            with PlaybookApi() as playbook_api:
                execution = playbook_api.create_action_execution(
                    playbook_item_id=self.playbook_items_map[action_index],
                    experiment_run_id=self.experiment_run_id,
                    status='pending'
                )
                playbook_api.update_action_execution_start(execution.id)
                log.debug(f"Created execution record {execution.id} for action {action_index}")
                return execution.id
        except Exception as e:
            log.warning(f"Failed to create execution record for action {action_index}: {e}")
            return None
    
    async def _update_database_execution_record(self, execution_id: str, result: ActionResult, execution_time: float):
        """Update database execution record with results."""
        try:
            from adare.database.api.playbook import PlaybookApi
            
            with PlaybookApi() as playbook_api:
                playbook_api.update_action_execution_complete(
                    execution_id=execution_id,
                    success=result.success,
                    result_data={
                        'coordinates': getattr(result, 'coordinates', None),
                        'data': getattr(result, 'data', None),
                        'execution_time': execution_time
                    },
                    error_message=result.message if not result.success else None
                )
                log.debug(f"Updated execution record {execution_id}")
        except Exception as e:
            log.warning(f"Failed to update execution record {execution_id}: {e}")
    
    def _is_test_action(self, action: ActionType) -> bool:
        """Check if an action is a test action."""
        return isinstance(action, ActionTestAction)

    def _is_utility_action(self, action: ActionType) -> bool:
        """Check if an action is a utility action that shouldn't count toward execution statistics."""
        return isinstance(action, (PullAction, PauseAction, SaveTimestampAction))

    def _is_countable_action(self, action: ActionType) -> bool:
        """Check if an action should be counted in execution statistics."""
        return not self._is_utility_action(action)
    
    def _is_test_action_result(self, action_result: ActionResult) -> bool:
        """Check if an action result corresponds to a test execution."""
        if action_result.data and isinstance(action_result.data, dict):
            # Check if this was a test action by looking at the result data structure
            result_data = action_result.data.get('result', {})
            return 'status' in result_data and 'details' in result_data
        return False

    async def _execute_auto_pull(self):
        """Execute auto-pull of files mentioned in playbook after test failure."""
        log.info("Executing auto-pull for test failure analysis")

        for file_path in self._auto_pull_files:
            try:
                # Resolve variables in file path
                resolved_path = self.variable_resolver.replace_variables(file_path, self.execution_context)

                # Create a programmatic pull action
                auto_pull_action = PullAction(
                    src=resolved_path,
                    description=f"Auto-pull on test failure: {resolved_path}"
                )

                log.info(f"Auto-pulling file: {resolved_path}")

                # Execute the pull using the action executor
                result = await self.action_executor.execute_programmatic_pull(
                    src_path=resolved_path,
                    description=f"Auto-pull on test failure: {resolved_path}"
                )

                if result.success:
                    log.info(f"Successfully auto-pulled: {resolved_path}")
                else:
                    log.warning(f"Failed to auto-pull {resolved_path}: {result.message}")

            except Exception as e:
                log.error(f"Error during auto-pull of {file_path}: {e}", exc_info=True)