"""
Playbook Controller for WebSocket-based Experiment Execution.

This module provides the PlaybookController class that translates YAML playbook
actions and tests into WebSocket commands for execution on the VM. It handles
local CV/OCR for target resolution and maintains proper execution order.
"""

import logging
from pathlib import Path
from typing import Dict, List, Tuple, Optional, Any
from dataclasses import dataclass
import time
import jinja2


# Removed TimestampTransform class - no longer needed with simplified approach

# Playbook and test imports
from adare.types.playbook import (
    parse_playbook, Playbook, ActionType, Target, SaveTimestampAction,
    ClickAction, RightClickAction, DoubleClickAction, DragAction,
    KeyboardAction, IdleAction, ScrollAction, GotoAction, 
    CommandAction, ScreenshotAction, BlockAction, ActionTestAction,
    ExistsCondition, NotExistsCondition
)

# WebSocket client import
from adare.backend.experiment.websocket_client import AdareVMClient
from adarelib.websocket.protocol import ToolRegistry

# Target resolution using MCP GUI server
from adare.backend.experiment.target_resolver import MCPTargetResolver, MCPConditionChecker

# Action event imports for flow console display
from adare.backend.events.emitters import emit_action

# Internal step actions for step event tracking
from adare.types.step_actions import FindAction, ExecuteAction
from adare.types.actions import (
    ClickActionStartEvent, ClickActionCompleteEvent,
    RightClickActionStartEvent, RightClickActionCompleteEvent,
    DoubleClickActionStartEvent, DoubleClickActionCompleteEvent,
    KeyboardActionStartEvent, KeyboardActionCompleteEvent,
    CommandActionStartEvent, CommandActionCompleteEvent,
    TestActionStartEvent, TestActionCompleteEvent,
    ScreenshotActionStartEvent, ScreenshotActionCompleteEvent,
    ScrollActionStartEvent, ScrollActionCompleteEvent,
    IdleActionStartEvent, IdleActionCompleteEvent,
    DragActionStartEvent, DragActionCompleteEvent,
    GotoActionStartEvent, GotoActionCompleteEvent,
    BlockActionStartEvent, BlockActionCompleteEvent,
    SaveTimestampActionStartEvent, SaveTimestampActionCompleteEvent,
    FindActionStartEvent, FindActionCompleteEvent,
    ExecuteActionStartEvent, ExecuteActionCompleteEvent
)

log = logging.getLogger(__name__)


@dataclass
class ActionResult:
    """Result of a playbook action execution."""
    success: bool
    message: str = ""
    coordinates: Optional[Tuple[int, int]] = None
    data: Optional[Dict] = None
    execution_time: Optional[float] = None


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
    
    This controller translates playbook actions into WebSocket tool calls,
    performs local CV/OCR for target resolution, and maintains proper
    execution order with timing and conditional logic.
    """
    
    def __init__(self, websocket_client: AdareVMClient, experiment_dir: Path, project_dir: Path, mcp_gui_url: str = "http://localhost:13109/mcp", debug_screenshots: bool = False, screenshots_dir: Path = None, playbook: Optional[Playbook] = None, experiment_id: Optional[str] = None, experiment_run_id: Optional[str] = None):
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
        """
        self.client = websocket_client
        self.experiment_dir = experiment_dir
        self.project_dir = project_dir
        self.execution_context = {}
        self.action_results: List[ActionResult] = []
        self.debug_screenshots = debug_screenshots
        self.screenshots_dir = screenshots_dir
        self.screenshot_counter = 0
        self.playbook = playbook
        
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
        
        # Performance tracking
        self.start_time: Optional[float] = None
        self.action_timings: Dict[str, float] = {}
    
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
    
    def _create_action_start_event(self, action: ActionType, action_index: int, action_id: str, parent_event_id: str = None):
        """Create appropriate start event for the given action type."""
        action_type = type(action).__name__
        description = getattr(action, 'description', '')
        
        # Common event data
        event_data = {
            'action_id': action_id,
            'action_description': description,
            'sequence_order': action_index,
            'playbook_item_id': self.playbook_items_map.get(action_index),
            'experiment_run_id': self.experiment_run_id,
            'parent_event_id': parent_event_id  # Include parent information
        }
        
        # Create type-specific start event
        if isinstance(action, ClickAction):
            return ClickActionStartEvent(target_info=self._get_target_info(getattr(action, 'target', None)), **event_data)
        elif isinstance(action, RightClickAction):
            return RightClickActionStartEvent(target_info=self._get_target_info(getattr(action, 'target', None)), **event_data)
        elif isinstance(action, DoubleClickAction):
            return DoubleClickActionStartEvent(target_info=self._get_target_info(getattr(action, 'target', None)), **event_data)
        elif isinstance(action, KeyboardAction):
            return KeyboardActionStartEvent(keys=getattr(action, 'keys', None), **event_data)
        elif isinstance(action, CommandAction):
            return CommandActionStartEvent(command=getattr(action, 'command', None), **event_data)
        elif isinstance(action, ActionTestAction):
            return TestActionStartEvent(test_name=getattr(action, 'name', ''), **event_data)
        elif isinstance(action, ScreenshotAction):
            return ScreenshotActionStartEvent(**event_data)
        elif isinstance(action, ScrollAction):
            return ScrollActionStartEvent(
                direction=getattr(action, 'direction', None),
                amount=getattr(action, 'amount', None),
                **event_data
            )
        elif isinstance(action, IdleAction):
            return IdleActionStartEvent(duration=getattr(action, 'duration', None), **event_data)
        elif isinstance(action, DragAction):
            return DragActionStartEvent(
                source_target=self._get_target_info(getattr(action, 'source', None)),
                dest_target=self._get_target_info(getattr(action, 'target', None)),
                **event_data
            )
        elif isinstance(action, GotoAction):
            return GotoActionStartEvent(url=getattr(action, 'url', None), **event_data)
        elif isinstance(action, BlockAction):
            return BlockActionStartEvent(
                action_count=len(getattr(action, 'actions', [])),
                conditions=self._get_condition_info(getattr(action, 'when', None)),
                **event_data
            )
        elif isinstance(action, SaveTimestampAction):
            return SaveTimestampActionStartEvent(variable=getattr(action, 'variable', None), **event_data)
        elif isinstance(action, FindAction):
            return FindActionStartEvent(target_info=getattr(action, 'target_info', None), **event_data)
        elif isinstance(action, ExecuteAction):
            return ExecuteActionStartEvent(coordinates=getattr(action, 'coordinates', None), **event_data)
        else:
            # Generic start event for unknown action types
            from adare.types.actions import ActionEvent
            return ActionEvent(**event_data)
    
    def _create_action_complete_event(self, action: ActionType, action_index: int, action_id: str, result: ActionResult, parent_event_id: str = None):
        """Create appropriate complete event for the given action type and result."""
        action_type = type(action).__name__
        description = getattr(action, 'description', '')
        
        # Common event data
        event_data = {
            'action_id': action_id,
            'action_description': description,
            'sequence_order': action_index,
            'playbook_item_id': self.playbook_items_map.get(action_index),
            'experiment_run_id': self.experiment_run_id,
            'success': result.success,
            'execution_time': result.execution_time,
            'parent_event_id': parent_event_id  # Include parent information
        }
        
        # Create type-specific complete event
        if isinstance(action, ClickAction):
            event = ClickActionCompleteEvent(coordinates=result.coordinates, target_info=self._get_target_info(getattr(action, 'target', None)), **event_data)
        elif isinstance(action, RightClickAction):
            event = RightClickActionCompleteEvent(coordinates=result.coordinates, target_info=self._get_target_info(getattr(action, 'target', None)), **event_data)
        elif isinstance(action, DoubleClickAction):
            event = DoubleClickActionCompleteEvent(coordinates=result.coordinates, target_info=self._get_target_info(getattr(action, 'target', None)), **event_data)
        elif isinstance(action, KeyboardAction):
            event = KeyboardActionCompleteEvent(keys_sent=getattr(action, 'keys', None), **event_data)
        elif isinstance(action, CommandAction):
            event = CommandActionCompleteEvent(
                command_executed=getattr(action, 'command', None),
                output=result.data.get('output') if result.data else None,
                return_code=result.data.get('return_code') if result.data else None,
                **event_data
            )
        elif isinstance(action, ActionTestAction):
            event = TestActionCompleteEvent(
                test_name=getattr(action, 'name', ''),
                test_output=result.data.get('result', {}).get('details') if result.data else None,
                **event_data
            )
        elif isinstance(action, ScreenshotAction):
            event = ScreenshotActionCompleteEvent(
                screenshot_path=result.data.get('screenshot_path') if result.data else None,
                **event_data
            )
        elif isinstance(action, ScrollAction):
            event = ScrollActionCompleteEvent(**event_data)
        elif isinstance(action, IdleAction):
            event = IdleActionCompleteEvent(actual_duration=result.execution_time, **event_data)
        elif isinstance(action, DragAction):
            event = DragActionCompleteEvent(
                source_coordinates=result.data.get('source_coordinates') if result.data else None,
                dest_coordinates=result.coordinates,
                **event_data
            )
        elif isinstance(action, GotoAction):
            event = GotoActionCompleteEvent(
                final_url=result.data.get('final_url') if result.data else None,
                **event_data
            )
        elif isinstance(action, BlockAction):
            event = BlockActionCompleteEvent(
                actions_executed=result.data.get('actions_executed', 0) if result.data else 0,
                **event_data
            )
        elif isinstance(action, SaveTimestampAction):
            event = SaveTimestampActionCompleteEvent(
                variable=getattr(action, 'variable', None),
                timestamp_value=result.data.get(getattr(action, 'variable', 'timestamp')) if result.data else None,
                **event_data
            )
        elif isinstance(action, FindAction):
            event = FindActionCompleteEvent(
                target_info=getattr(action, 'target_info', None),
                coordinates=result.coordinates,
                **event_data
            )
        elif isinstance(action, ExecuteAction):
            event = ExecuteActionCompleteEvent(
                coordinates=result.coordinates,
                **event_data
            )
        else:
            # Generic complete event for unknown action types
            from adare.types.actions import ActionEvent
            event = ActionEvent(**event_data)
        
        # Error information is handled at the database/execution level
        return event
    
    def _get_target_info(self, target) -> Optional[Dict[str, Any]]:
        """Extract target information for event logging."""
        if not target:
            return None
        
        info = {}
        if hasattr(target, 'image') and target.image:
            info['image'] = target.image
        if hasattr(target, 'text') and target.text:
            info['text'] = target.text
        if hasattr(target, 'position') and target.position:
            info['position'] = target.position
        if hasattr(target, 'strategy') and target.strategy:
            strategy_name = target.strategy.__class__.__name__
            info['strategy'] = strategy_name
            # Add strategy parameters if available
            if hasattr(target.strategy, '__dict__'):
                import attrs
                if attrs.has(target.strategy):
                    strategy_params = attrs.asdict(target.strategy)
                    if strategy_params:
                        info['strategy_params'] = strategy_params
        
        return info if info else None
    
    def _serialize_target(self, target) -> Optional[Dict[str, Any]]:
        """Serialize Target object for JSON storage."""
        if not target:
            return None
        from adare.types.actions import converter
        return converter.unstructure(target)
    
    def _get_condition_info(self, conditions) -> Optional[Dict[str, Any]]:
        """Extract condition information for event logging."""
        if not conditions:
            return None
        
        # If conditions is a list, extract basic info from each
        if isinstance(conditions, list):
            return {
                'count': len(conditions),
                'types': [type(cond).__name__ for cond in conditions]
            }
        else:
            return {'type': type(conditions).__name__}
        
        return None
        
        
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
        
        # 1. Load testfunctions and testset FIRST (required for playbook test actions)
        await self.load_tests(experiment_dir)
        
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
        
        return PlaybookExecutionResult(
            success=True,
            total_actions=len(self.action_results),
            successful_actions=sum(1 for r in self.action_results if r.success),
            failed_actions=sum(1 for r in self.action_results if not r.success),
            execution_time=execution_time,
            action_results=self.action_results,
            total_tests=total_tests,
            successful_tests=successful_tests,
            failed_tests=failed_tests
        )
    
    async def execute_playbook(self) -> PlaybookExecutionResult:
        """
        Execute YAML playbook actions in order.
        
        Args:
            playbook_path: Path to playbook.yml file
            
        Returns:
            PlaybookExecutionResult with execution details
        """
        playbook = self.playbook
        
        # Set up experiment variables and playbook access
        self.execution_context['playbook'] = playbook
        if hasattr(playbook, 'variables') and playbook.variables:
            log.info("Loading experiment variables...")
            # Convert VariableRegistry to execution context format (for actions - full resolution)
            var_dict = playbook.variables.to_execution_context(for_tests=False)
            self.execution_context.update(var_dict)
            log.debug(f"Loaded {len(playbook.variables.variables)} variables into execution context")
        
        # Execute actions sequentially
        total_actions = len(playbook.actions)
        log.info(f"Executing {total_actions} playbook actions...")
        
        for i, action in enumerate(playbook.actions):
            action_name = type(action).__name__
            log.info(f"Executing action {i+1}/{total_actions}: {action_name}")
            
            # Create database execution record if tracking enabled
            execution_id = None
            if self.experiment_run_id and i in self.playbook_items_map:
                try:
                    from adare.database.api.playbook import PlaybookApi
                    
                    with PlaybookApi() as playbook_api:
                        execution = playbook_api.create_action_execution(
                            playbook_item_id=self.playbook_items_map[i],
                            experiment_run_id=self.experiment_run_id,
                            status='pending'
                        )
                        execution_id = execution.id
                        playbook_api.update_action_execution_start(execution_id)
                        log.debug(f"Created execution record {execution_id} for action {i}")
                except Exception as e:
                    log.warning(f"Failed to create execution record for action {i}: {e}")
            
            # Resolve variables early for consistent display and execution
            resolved_action = self._resolve_action_variables(action)
            
            # Create unique action ID for event tracking
            action_id = f"action_{i}_{action_name.lower()}_{int(time.time()*1000)}"
            
            # Emit action start event for flow console display using resolved action
            if self.experiment_run_id:
                try:
                    start_event = self._create_action_start_event(resolved_action, i, action_id)
                    emit_action(self.experiment_run_id, start_event, action_id)
                    log.info(f"Emitted start event for action {i}: {action_name}, ID: {action_id}")
                except Exception as e:
                    log.error(f"Failed to emit start event for action {i}: {e}", exc_info=True)
            
            # Execute the action (level 2 for main playbook actions) - pass original action since execute_action handles resolution
            start_time = time.time()
            result = await self.execute_action(action, parent_event_id=action_id)
            execution_time = time.time() - start_time
            
            result.execution_time = execution_time
            self.action_results.append(result)
            self.action_timings[f"action_{i+1}_{action_name}"] = execution_time
            
            # Emit action complete event for flow console display using resolved action
            if self.experiment_run_id:
                try:
                    complete_event = self._create_action_complete_event(resolved_action, i, action_id, result)
                    emit_action(self.experiment_run_id, complete_event, action_id)
                    log.info(f"Emitted complete event for action {i}: {action_name}, Success: {result.success}, ID: {action_id}")
                except Exception as e:
                    log.error(f"Failed to emit complete event for action {i}: {e}", exc_info=True)
            
            # Update database execution record
            if execution_id:
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
            
            if not result.success:
                log.error(f"Action {i+1} failed: {result.message}")
                # Stop execution by default after failed action
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
    
    async def execute_action(self, action: ActionType, parent_event_id: str = None) -> ActionResult:
        """
        Execute a single playbook action by translating to WebSocket calls.
        
        Args:
            action: Playbook action to execute
            parent_event_id: Parent event ID for nested actions
            
        Returns:
            ActionResult with execution details
        """
        try:
            # Resolve variables in action fields first
            resolved_action = self._resolve_action_variables(action)
            
            action_type = type(resolved_action).__name__
            description = getattr(resolved_action, 'description', '')
            log.debug(f"Executing {action_type}: {description}")
            
            # Dispatch to appropriate handler using resolved action
            if isinstance(resolved_action, ClickAction):
                return await self._execute_click(resolved_action, parent_event_id)
            elif isinstance(resolved_action, RightClickAction):
                return await self._execute_right_click(resolved_action, parent_event_id)
            elif isinstance(resolved_action, DoubleClickAction):
                return await self._execute_double_click(resolved_action, parent_event_id)
            elif isinstance(resolved_action, DragAction):
                return await self._execute_drag(resolved_action, parent_event_id)
            elif isinstance(resolved_action, KeyboardAction):
                return await self._execute_keyboard(resolved_action, parent_event_id)
            elif isinstance(resolved_action, IdleAction):
                return await self._execute_idle(resolved_action, parent_event_id)
            elif isinstance(resolved_action, ScrollAction):
                return await self._execute_scroll(resolved_action, parent_event_id)
            elif isinstance(resolved_action, GotoAction):
                return await self._execute_goto(resolved_action, parent_event_id)
            elif isinstance(resolved_action, ScreenshotAction):
                return await self._execute_screenshot(resolved_action, parent_event_id)
            elif isinstance(resolved_action, CommandAction):
                return await self._execute_command(resolved_action, parent_event_id)
            elif isinstance(resolved_action, ActionTestAction):
                return await self._execute_test(resolved_action, parent_event_id)
            elif isinstance(resolved_action, BlockAction):
                return await self._execute_block(resolved_action, parent_event_id)
            elif isinstance(resolved_action, SaveTimestampAction):
                return await self._execute_save_timestamp(resolved_action, parent_event_id)
            else:
                return ActionResult(
                    success=False,
                    message=f"Unknown action type: {action_type}"
                )
                
        except Exception as e:
            log.error(f"Error executing action: {e}")
            return ActionResult(
                success=False,
                message=f"Exception: {str(e)}"
            )
    
    async def load_tests(self, experiment_dir: Path):
        """
        Load testfunctions and testset for use during playbook execution.
        
        Args:
            experiment_dir: Path to experiment directory
        """
        log.info("Loading testfunctions and testset...")
        
        # Upload testfunctions directory (Python classes) from project directory
        testfunctions_path = self.project_dir / "testfunctions"
        if testfunctions_path.exists():
            log.info("Uploading testfunctions...")
            try:
                await self.client.upload_testfunctions(testfunctions_path)
            except Exception as e:
                log.error(f"Failed to upload testfunctions: {e}")
        else:
            log.warning("No testfunctions directory found")
        
        # Individual tests are sent via WebSocket when executed
        # No need to upload entire testset file to VM
    
    
    # Simplified method - just add steps under existing action events
    async def _execute_action_with_steps(self, action, execute_func, parent_action_id: str = None) -> ActionResult:
        """Execute an action with steps for target resolution and execution."""
        import time
        
        try:
            # Resolve target with find step (emitted as action event)
            coords = await self._resolve_target_with_steps(action.target, parent_action_id)
            if not coords:
                return ActionResult(
                    success=False,
                    message=f"Could not resolve target: {action.target}"
                )
            
            x, y = int(coords[0]), int(coords[1])
            
            # Create and emit execution step events
            execute_action_id = f"execute_step_{int(time.time()*1000)}"
            
            if self.experiment_run_id:
                # Create execution step action
                execute_step = ExecuteAction(
                    description=f"executing at ({x}, {y})",
                    coordinates=(x, y)
                )
                
                # Emit execution start event using existing unified pattern
                start_event = self._create_action_start_event(execute_step, -1, execute_action_id, parent_action_id)
                emit_action(self.experiment_run_id, start_event, execute_action_id)
            
            # Execute the action
            start_time = time.time()
            result = await execute_func(x, y)
            execution_time = time.time() - start_time
            execution_success = result.get('status') == 'success'
            
            # Emit execution complete event
            if self.experiment_run_id:
                execute_result = ActionResult(
                    success=execution_success,
                    message=result.get('message', ''),
                    execution_time=execution_time,
                    coordinates=(x, y)
                )
                complete_event = self._create_action_complete_event(execute_step, -1, execute_action_id, execute_result, parent_action_id)
                emit_action(self.experiment_run_id, complete_event, execute_action_id)
            
            return ActionResult(
                success=execution_success,
                message=result.get('message', ''),
                coordinates=(x, y),
                data={'target': self._serialize_target(action.target)}
            )
            
        except Exception as e:
            return ActionResult(
                success=False,
                message=str(e),
                data={'target': self._serialize_target(action.target)}
            )
    
    async def _resolve_target_with_steps(self, target: Target, parent_action_id: str = None) -> Optional[Tuple[int, int]]:
        """Resolve target with find step emitted as action event."""
        import time
        
        # Apply smart defaults if no strategy specified (before creating find step description)
        if target.strategy is None:
            from adare.types.playbook import BestConfidenceStrategy, TopLeftStrategy
            if target.image:
                target.strategy = BestConfidenceStrategy()  # Images: best visual match
                log.debug("Applied default BestConfidence strategy for image target")
            elif target.text:
                target.strategy = TopLeftStrategy()  # Text: natural reading order
                log.debug("Applied default TopLeft strategy for text target")
            else:
                target.strategy = TopLeftStrategy()  # Fallback
                log.debug("Applied fallback TopLeft strategy for position target")
        
        # Create and emit find step events
        find_action_id = f"find_step_{int(time.time()*1000)}"
        
        if self.experiment_run_id:
            # Create find step action
            target_desc = target.image or target.text or f"position {target.position}" if target else "target"
            
            # Include strategy in description if available
            strategy_desc = ""
            if hasattr(target, 'strategy') and target.strategy:
                strategy_name = target.strategy.__class__.__name__
                strategy_desc = f" using {strategy_name}"
            
            find_step = FindAction(
                description=f"finding {target_desc}{strategy_desc}",
                target_info=self._get_target_info(target)
            )
            
            # Emit find start event using existing unified pattern
            start_event = self._create_action_start_event(find_step, -1, find_action_id, parent_action_id)
            emit_action(self.experiment_run_id, start_event, find_action_id)
        
        try:
            # Get screenshot for target resolution
            start_time = time.time()
            screenshot_base64 = await self._get_current_screenshot()
            if not screenshot_base64:
                log.error("Failed to get screenshot for target resolution")
                
                # Emit find failure event
                if self.experiment_run_id:
                    execution_time = time.time() - start_time
                    find_result = ActionResult(success=False, message="Failed to get screenshot", execution_time=execution_time)
                    complete_event = self._create_action_complete_event(find_step, -1, find_action_id, find_result, parent_action_id)
                    emit_action(self.experiment_run_id, complete_event, find_action_id)
                
                return None
            
            # Resolve using MCP target resolver
            match = await self.target_resolver.resolve_target(target, screenshot_base64)
            execution_time = time.time() - start_time
            
            # Emit find complete event
            if self.experiment_run_id:
                success = match is not None
                coords = match.coordinates if match else None
                find_result = ActionResult(
                    success=success,
                    message="Target found" if success else "Target not found",
                    execution_time=execution_time,
                    coordinates=coords
                )
                complete_event = self._create_action_complete_event(find_step, -1, find_action_id, find_result, parent_action_id)
                emit_action(self.experiment_run_id, complete_event, find_action_id)
            
            return match.coordinates if match else None
                
        except Exception as e:
            execution_time = time.time() - start_time if 'start_time' in locals() else 0
            log.error(f"Error resolving target: {e}")
            
            # Emit find failure event  
            if self.experiment_run_id:
                find_result = ActionResult(success=False, message=str(e), execution_time=execution_time)
                complete_event = self._create_action_complete_event(find_step, -1, find_action_id, find_result, parent_action_id)
                emit_action(self.experiment_run_id, complete_event, find_action_id)
            
            return None
    
    # Action execution methods - unified approach
    
    def __init_action_handlers(self):
        """Initialize action handlers mapping for unified execution."""
        self._action_handlers = {
            ClickAction: lambda x, y: self.client.click(x, y),
            RightClickAction: lambda x, y: self.client.right_click(x, y),
            DoubleClickAction: lambda x, y: self.client.double_click(x, y),
            GotoAction: lambda x, y: self.client.goto(x, y),
        }
    
    async def _execute_action_with_target(self, action, parent_event_id: str = None) -> ActionResult:
        """Execute any action that requires target resolution with steps."""
        if not hasattr(self, '_action_handlers'):
            self.__init_action_handlers()
        
        action_type = type(action)
        if action_type in self._action_handlers:
            return await self._execute_action_with_steps(
                action,
                self._action_handlers[action_type],
                parent_event_id
            )
        else:
            return ActionResult(
                success=False,
                message=f"No handler found for action type: {action_type.__name__}"
            )
    
    async def _execute_click(self, action: ClickAction, parent_event_id: str = None) -> ActionResult:
        """Execute click action with steps."""
        return await self._execute_action_with_target(action, parent_event_id)
    
    async def _get_current_screenshot(self) -> Optional[str]:
        """
        Get current screenshot from WebSocket client.
        
        Returns:
            Base64 encoded screenshot data, None if failed
        """
        try:
            # Take new screenshot via WebSocket
            result = await self.client.screenshot()
            if result and 'image' in result:
                # Extract base64 data from result
                if 'data' in result['image']:
                    screenshot_base64 = result['image']['data']
                else:
                    screenshot_base64 = result['image']
                
                # Save screenshot to disk if debug mode is enabled
                if hasattr(self, 'debug_screenshots') and self.debug_screenshots:
                    await self._save_debug_screenshot(screenshot_base64)
                
                log.debug("Screenshot captured")
                return screenshot_base64
            else:
                log.error("Screenshot result missing image data")
                return None
                
        except Exception as e:
            log.error(f"Failed to capture screenshot: {e}")
            return None
    
    async def _save_debug_screenshot(self, screenshot_base64: str):
        """
        Save screenshot to disk for debugging purposes.
        
        Args:
            screenshot_base64: Base64 encoded screenshot data
        """
        try:
            if not self.screenshots_dir:
                return
                
            import base64
            from datetime import datetime
            
            # Create screenshots directory if it doesn't exist
            self.screenshots_dir.mkdir(parents=True, exist_ok=True)
            
            # Generate filename with timestamp and counter
            timestamp = datetime.now().strftime("%H-%M-%S")
            self.screenshot_counter += 1
            filename = f"screenshot_{timestamp}_{self.screenshot_counter:03d}.png"
            filepath = self.screenshots_dir / filename
            
            # Decode and save the image
            image_data = base64.b64decode(screenshot_base64)
            with open(filepath, 'wb') as f:
                f.write(image_data)
                
            log.debug(f"Debug screenshot saved: {filepath}")
            
        except Exception as e:
            log.error(f"Failed to save debug screenshot: {e}")
    
    async def _resolve_target_with_events(self, target: Target, parent_action_id: str) -> Optional[Tuple[int, int]]:
        """
        Resolve target to screen coordinates with sub-action event emission.
        
        Args:
            target: Target to resolve
            parent_action_id: ID of the parent action for sub-action events
            
        Returns:
            Coordinates if found, None otherwise
        """
        # Create sub-action ID for find operation
        find_action_id = f"{parent_action_id}_find"
        
        # Emit find start event
        if self.experiment_run_id:
            try:
                from adare.types.actions import ActionEvent
                find_start_event = ActionEvent(
                    action_id=find_action_id,
                    action_description=f"find {target.image or target.text or 'target'}",
                    experiment_run_id=self.experiment_run_id
                )
                emit_action(self.experiment_run_id, find_start_event, find_action_id)
            except Exception as e:
                log.error(f"Failed to emit find start event: {e}")
        
        # Perform target resolution
        coords = await self._resolve_target(target)
        
        # Emit find complete event
        if self.experiment_run_id:
            try:
                find_complete_event = ActionEvent(
                    action_id=find_action_id,
                    action_description=f"find {target.image or target.text or 'target'}",
                    experiment_run_id=self.experiment_run_id,
                    success=coords is not None,
                    error_message=f"Could not find {target.image or target.text or 'target'}" if coords is None else None,
                    coordinates=coords
                )
                emit_action(self.experiment_run_id, find_complete_event, find_action_id)
            except Exception as e:
                log.error(f"Failed to emit find complete event: {e}")
                
        return coords

    async def _resolve_target(self, target: Target) -> Optional[Tuple[int, int]]:
        """
        Resolve target to screen coordinates using MCP GUI server.
        
        Args:
            target: Target to resolve
            
        Returns:
            Coordinates if found, None otherwise
        """
        try:
            # Strategy defaults are now applied in _resolve_target_with_steps
            
            # Get fresh screenshot for image/text targets
            screenshot_base64 = None
            if target.image or target.text:
                log.debug(f"Taking screenshot for target resolution: image={target.image}, text={target.text}")
                screenshot_base64 = await self._get_current_screenshot()
                if not screenshot_base64:
                    log.error("Could not get screenshot for target resolution")
                    return None
                log.debug(f"Screenshot captured, length: {len(screenshot_base64)} characters")
            
            # Resolve target using screenshot data
            log.debug(f"Resolving target via MCP: {target}")
            match = await self.target_resolver.resolve_target(target, screenshot_base64)
            if match:
                log.debug(f"Target resolved to coordinates: {match.coordinates}")
                return match.coordinates
            else:
                log.warning(f"Target resolution failed - no match found: {target}")
            return None
        except Exception as e:
            log.error(f"Error resolving target: {e}")
            return None
    
    # Additional action handlers (placeholder implementations)
    
    async def _execute_keyboard(self, action: KeyboardAction, parent_event_id: str = None) -> ActionResult:
        """Execute keyboard action."""
        try:
            if action.keys:
                result = await self.client.keyboard("type", action.keys)
            elif action.combination:
                combo = "+".join(action.combination)
                result = await self.client.keyboard("hotkey", combo)
            else:
                return ActionResult(
                    success=False,
                    message="No keys or combination specified"
                )
            
            return ActionResult(
                success=result.get('status') == 'success',
                message=result.get('message', '')
            )
        except Exception as e:
            return ActionResult(success=False, message=str(e))
    
    async def _execute_idle(self, action: IdleAction, parent_event_id: str = None) -> ActionResult:
        """Execute idle action."""
        try:
            log.info(f"Starting idle action for {action.duration} seconds")
            result = await self.client.idle(action.duration)
            log.info(f"Idle action completed, result: {result}")
            
            # Handle different possible response formats
            if isinstance(result, dict):
                success = result.get('status') == 'success' or result.get('success', False)
                message = result.get('message', '') or result.get('error', '')
            else:
                # If result is not a dict, assume success if no exception was thrown
                success = True
                message = f"Idle completed ({action.duration}s)"
            
            return ActionResult(
                success=success,
                message=message
            )
        except Exception as e:
            log.error(f"Idle action failed: {e}")
            return ActionResult(success=False, message=str(e))
    
    async def _execute_screenshot(self, action: ScreenshotAction, parent_event_id: str = None) -> ActionResult:
        """Execute screenshot action."""
        try:
            result = await self.client.screenshot(
                action.x, action.y, action.width, action.height
            )
            return ActionResult(
                success=result.get('status') == 'success',
                message=result.get('message', ''),
                data=result
            )
        except Exception as e:
            return ActionResult(success=False, message=str(e))
    
    async def _execute_test(self, action: ActionTestAction, parent_event_id: str = None) -> ActionResult:
        """Execute individual test action with local variable substitution."""
        try:
            # Load and resolve test locally with current execution context
            resolved_test = await self._resolve_test_locally(action.name)
            if not resolved_test:
                return ActionResult(
                    success=False,
                    message=f"Test '{action.name}' not found in playbook tests"
                )
            
            # Send resolved test to VM for execution
            result = await self.client.run_test(action.name, resolved_test)
            
            # Use TestResultProcessor to handle result processing
            from adare.backend.experiment.test_result_processor import TestResultProcessor
            return TestResultProcessor.process_test_result(action.name, result)
        except Exception as e:
            error_msg = str(e)
            if "No testset loaded" in error_msg or "testset" in error_msg.lower():
                return ActionResult(
                    success=False, 
                    message=f"No tests loaded - ensure playbook.yml contains tests section and loads successfully before test actions"
                )
            return ActionResult(success=False, message=error_msg)
    
    async def _execute_block(self, action: BlockAction, parent_event_id: str = None) -> ActionResult:
        """Execute conditional block action with MCP-based condition checking."""
        # Check conditions if present
        if hasattr(action, 'when') and action.when:
            try:
                # Get screenshot for condition checking
                screenshot_base64 = await self._get_current_screenshot()
                conditions_met = await self.condition_checker.check_conditions(action.when, screenshot_base64)
                if not conditions_met:
                    return ActionResult(
                        success=True,
                        message="Block conditions not met, skipping"
                    )
            except Exception as e:
                log.error(f"Error checking block conditions: {e}")
                return ActionResult(
                    success=False,
                    message=f"Condition check failed: {str(e)}"
                )
        
        # Use the block's parent_event_id as parent context for sub-actions
        block_parent_event_id = parent_event_id  # Use block parent_event_id directly as parent reference
        
        # Execute all actions in block at level 3 (sub-actions)
        results = []
        for i, block_action in enumerate(action.actions):
            # Create sub-action ID (use a timestamp-based ID since we don't have action_id here)
            sub_action_id = f"block_sub_{i}_{int(time.time()*1000)}"
            
            # Emit sub-action start event
            if self.experiment_run_id:
                try:
                    sub_start_event = self._create_action_start_event(block_action, i, sub_action_id, parent_event_id=block_parent_event_id)
                    emit_action(self.experiment_run_id, sub_start_event, sub_action_id)
                except Exception as e:
                    log.error(f"Failed to emit sub-action start event: {e}")
            
            # Execute the sub-action
            start_time = time.time()
            result = await self.execute_action(block_action, parent_event_id=block_parent_event_id)
            execution_time = time.time() - start_time
            result.execution_time = execution_time
            
            # Emit sub-action complete event
            if self.experiment_run_id:
                try:
                    sub_complete_event = self._create_action_complete_event(block_action, i, sub_action_id, result, parent_event_id=block_parent_event_id)
                    emit_action(self.experiment_run_id, sub_complete_event, sub_action_id)
                except Exception as e:
                    log.error(f"Failed to emit sub-action complete event: {e}")
            
            results.append(result)
            if not result.success:
                # Handle testset-related errors specifically
                if "No testset loaded" in result.message:
                    return ActionResult(
                        success=False,
                        message=f"Block action failed: {result.message}"
                    )
                return ActionResult(
                    success=False,
                    message=f"Block action failed: {result.message}"
                )
        
        return ActionResult(
            success=True,
            message=f"Block executed successfully ({len(results)} actions)",
            data={'actions_executed': len(results)}
        )
    
    async def _execute_right_click(self, action: RightClickAction, parent_event_id: str = None) -> ActionResult:
        """Execute right-click action with steps."""
        return await self._execute_action_with_target(action, parent_event_id)
    
    async def _execute_double_click(self, action: DoubleClickAction, parent_event_id: str = None) -> ActionResult:
        """Execute double-click action with steps."""
        return await self._execute_action_with_target(action, parent_event_id)
    
    async def _execute_drag(self, action: DragAction, parent_event_id: str = None) -> ActionResult:
        """Execute drag action - special handling for two targets."""
        import time
        
        try:
            # Resolve both targets (each will emit their own find steps with proper parent)
            src_coords = await self._resolve_target_with_steps(action.source, parent_event_id)
            dst_coords = await self._resolve_target_with_steps(action.destination, parent_event_id)
            
            if not src_coords or not dst_coords:
                return ActionResult(success=False, message="Could not resolve targets")
            
            # Create and emit execution step
            execute_action_id = f"execute_step_{int(time.time()*1000)}"
            
            if self.experiment_run_id:
                # Create execution step action
                execute_step = ExecuteAction(
                    description=f"dragging from ({src_coords[0]}, {src_coords[1]}) to ({dst_coords[0]}, {dst_coords[1]})",
                    coordinates=src_coords  # Use source coordinates
                )
                
                # Emit execution start event
                start_event = self._create_action_start_event(execute_step, -1, execute_action_id, parent_event_id)
                emit_action(self.experiment_run_id, start_event, execute_action_id)
            
            # Execute the drag
            start_time = time.time()
            result = await self.client.drag(src_coords[0], src_coords[1], dst_coords[0], dst_coords[1])
            execution_time = time.time() - start_time
            success = result.get('status') == 'success'
            
            # Emit execution complete event
            if self.experiment_run_id:
                execute_result = ActionResult(
                    success=success,
                    message=result.get('message', ''),
                    execution_time=execution_time,
                    coordinates=dst_coords,  # Use destination coordinates as final result
                    data={'source_coordinates': src_coords, 'dest_coordinates': dst_coords}
                )
                complete_event = self._create_action_complete_event(execute_step, -1, execute_action_id, execute_result, parent_event_id)
                emit_action(self.experiment_run_id, complete_event, execute_action_id)
            
            return ActionResult(
                success=success,
                message=result.get('message', ''),
                coordinates=src_coords,
                data={'source': action.source, 'destination': action.destination, 'source_coordinates': src_coords, 'dest_coordinates': dst_coords}
            )
            
        except Exception as e:
            return ActionResult(success=False, message=str(e))
    
    async def _execute_scroll(self, action: ScrollAction, parent_event_id: str = None) -> ActionResult:
        result = await self.client.scroll(action.direction, action.amount or 3)
        return ActionResult(success=result.get('status') == 'success')
    
    async def _execute_goto(self, action: GotoAction, parent_event_id: str = None) -> ActionResult:
        """Execute goto action with steps."""
        return await self._execute_action_with_target(action, parent_event_id)
    
    def _resolve_action_variables(self, action: ActionType) -> ActionType:
        """Resolve variables in action fields that support templating.
        
        Returns a copy of the action with variables resolved in applicable fields.
        """
        import copy
        from adare.types.playbook import (
            CommandAction, KeyboardAction, ActionTestAction, SaveTimestampAction,
            Target, ClickAction, RightClickAction, DoubleClickAction, GotoAction, DragAction
        )
        
        # Create a deep copy to avoid modifying the original
        resolved_action = copy.deepcopy(action)
        
        # Resolve description for all actions
        if hasattr(resolved_action, 'description') and resolved_action.description:
            resolved_action.description = self._replace_variables(resolved_action.description)
        
        # Resolve fields specific to each action type
        if isinstance(action, CommandAction):
            if resolved_action.command:
                resolved_action.command = self._replace_variables(resolved_action.command)
            if resolved_action.cwd:
                resolved_action.cwd = self._replace_variables(resolved_action.cwd)
            if resolved_action.env:
                resolved_action.env = {k: self._replace_variables(str(v)) for k, v in resolved_action.env.items()}
        
        elif isinstance(action, KeyboardAction):
            if resolved_action.keys:
                resolved_action.keys = self._replace_variables(resolved_action.keys)
        
        elif isinstance(action, ActionTestAction):
            if resolved_action.name:
                resolved_action.name = self._replace_variables(resolved_action.name)
        
        elif isinstance(action, SaveTimestampAction):
            if resolved_action.variable:
                resolved_action.variable = self._replace_variables(resolved_action.variable)
        
        # Resolve Target fields for actions that have targets
        if hasattr(resolved_action, 'target') and resolved_action.target:
            resolved_action.target = self._resolve_target_variables(resolved_action.target)
        
        # Resolve Source/Destination targets for DragAction
        if isinstance(action, DragAction):
            if resolved_action.source:
                resolved_action.source = self._resolve_target_variables(resolved_action.source)
            if resolved_action.destination:
                resolved_action.destination = self._resolve_target_variables(resolved_action.destination)
        
        return resolved_action
    
    def _resolve_target_variables(self, target: Target) -> Target:
        """Resolve variables in Target fields."""
        import copy
        resolved_target = copy.deepcopy(target)
        
        if resolved_target.image:
            resolved_target.image = self._replace_variables(resolved_target.image)
        if resolved_target.text:
            resolved_target.text = self._replace_variables(resolved_target.text)
        
        return resolved_target

    def _replace_variables(self, text: str) -> str:
        """Replace Jinja2 template variables in text with values or metadata placeholders.
        
        Variables with metadata are resolved to placeholders (e.g., VARTIMESTAMP_RESOLVED)
        and the metadata is captured for server-side processing.
        """
        if not text or '{{' not in text:
            return text
        
        try:
            result = text
            max_iterations = 10  # Prevent infinite loops
            previous_results = set()  # Track previous results to detect cycles
            
            for i in range(max_iterations):
                # If no more variables to replace, we're done
                if '{{' not in result:
                    break
                
                # Check for cycles (same result appearing again)
                if result in previous_results:
                    log.warning(f"Circular variable reference detected in: {text}")
                    break
                
                previous_results.add(result)
                
                # Create formatted context with metadata-aware variable handling  
                formatted_context = self._get_formatted_context(for_tests=False)
                
                # Perform template replacement with metadata capture
                log.debug(f"Processing template: '{result}' with context keys: {list(formatted_context.keys())}")
                template = jinja2.Template(result)
                
                # Add custom filters for metadata capture
                template.environment.filters.update(self._get_custom_filters())
                
                new_result = template.render(formatted_context)
                log.debug(f"Template result: '{new_result}'")
                
                
                # If no change occurred, break to avoid infinite loops
                if new_result == result:
                    break
                    
                result = new_result
            
            # Warn if we hit max iterations (possible infinite loop)
            if i == max_iterations - 1 and '{{' in result:
                log.warning(f"Variable replacement hit max iterations for: {text}")
            
            return result
        except Exception as e:
            log.warning(f"Failed to replace variables in '{text}': {e}")
            return text
    
    
    def _get_formatted_context(self, for_tests: bool = False) -> Dict[str, Any]:
        """Get execution context with smart variable handling based on usage."""
        # If we have a variable registry, use its smart execution context
        if hasattr(self.playbook, 'variables') and self.playbook.variables:
            registry_context = self.playbook.variables.to_execution_context(for_tests=for_tests)
            # Merge with existing execution context
            merged_context = self.execution_context.copy()
            merged_context.update(registry_context)
            return merged_context
        
        # Fallback to simple execution context copy
        return self.execution_context.copy()
    
    
    def _get_custom_filters(self) -> Dict[str, Any]:
        """Get custom Jinja2 filters from variable registry metadata."""
        # Get filters from variable registry if available
        if hasattr(self.playbook, 'variables') and self.playbook.variables:
            registry_filters = self.playbook.variables.get_all_jinja_filters()
            if registry_filters:
                log.debug(f"Using {len(registry_filters)} filters from variable registry: {list(registry_filters.keys())}")
                return registry_filters
        
        # Fallback to empty dict - no custom filters available
        log.debug("No variable registry filters available, using no custom filters")
        return {}
    
    async def _resolve_test_locally(self, test_name: str) -> Optional[Dict[str, Any]]:
        """Load and resolve a specific test locally with variable substitution."""
        try:
            # Load tests from playbook instead of separate testset file
            playbook_path = self.experiment_dir / "playbook.yml"
            if not playbook_path.exists():
                return None
            
            import yaml
            from adarelib.testset.yaml.customloader import get_custom_loader
            playbook_yaml = playbook_path.read_text()
            playbook_data = yaml.load(playbook_yaml, Loader=get_custom_loader())
            
            if 'tests' not in playbook_data:
                return None
            
            # Debug: Log current execution context before test resolution (use test context)
            formatted_context = self._get_formatted_context(for_tests=True)
            log.debug(f"Resolving test '{test_name}' with execution context keys: {list(formatted_context.keys())}")
            log.debug(f"Execution context values: {formatted_context}")
            
            # Find the test by name
            for test in playbook_data['tests']:
                if test.get('name') == test_name:
                    log.debug(f"Found test '{test_name}' raw data: {test}")
                    # Apply variable substitution to all string values in the test
                    resolved_test = self._resolve_test_content(test)
                    
                    # After processing, check if variable registry now has placeholder metadata
                    if hasattr(self.playbook, 'variables') and self.playbook.variables:
                        if hasattr(self.playbook.variables, '_placeholder_metadata') and self.playbook.variables._placeholder_metadata:
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
        from adare.backend.experiment.variable_resolver import VariableResolver
        
        variable_registry = getattr(self.playbook, 'variables', None) if hasattr(self, 'playbook') else None
        
        # Create enhanced resolver with Jinja environment
        jinja_env = self._create_jinja_environment()
        template_context = self._get_formatted_context(for_tests=True)
        
        resolver = VariableResolver(
            variable_registry=variable_registry, 
            jinja_env=jinja_env
        )
        
        # Single call handles everything - YAML tags AND Jinja templates
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
            # Use test-aware context that creates placeholders for variables with test-specific filters
            formatted_context = self._get_formatted_context(for_tests=True)
            
            log.debug(f"Processing test template: '{text}' with context keys: {list(formatted_context.keys())}")
            template = jinja2.Template(text)
            
            # Add custom filters for metadata capture
            template.environment.filters.update(self._get_custom_filters())
            
            result = template.render(formatted_context)
            log.debug(f"Test template result: '{result}'")
            
            return result
        except Exception as e:
            log.warning(f"Failed to replace variables in test text '{text}': {e}")
            return text
    
    async def _execute_command(self, action: CommandAction, parent_event_id: str = None) -> ActionResult:
        try:
            # Get the command (variables already resolved)
            command = action.command
            cwd = action.cwd
            env = action.env
        
            # Calculate WebSocket timeout with buffer for long-running commands
            websocket_timeout = None
            if action.timeout:
                # Add 10 second buffer to shell timeout for WebSocket communication
                websocket_timeout = action.timeout + 10
        
            # Execute raw shell command directly with options
            result = await self.client.execute_shell(
                shell_command=command,
                cwd=cwd,
                env=env,
                timeout=action.timeout,
                shell=action.shell,
                websocket_timeout=websocket_timeout
            )
            return ActionResult(
                success=result.get('status') == 'success',
                message=result.get('message', ''),
                data=result
            )
        except Exception as e:
            return ActionResult(success=False, message=str(e))
    
    async def _execute_save_timestamp(self, action: SaveTimestampAction, parent_event_id: str = None) -> ActionResult:
        """Save current timestamp to execution context and variable registry."""
        try:
            current_timestamp = time.time()
            
            # Save to execution context for immediate use
            self.execution_context[action.variable] = current_timestamp
            
            # Also save to variable registry if available for metadata support
            if hasattr(self.playbook, 'variables') and self.playbook.variables:
                from adarelib.common.variables import Variable, VariableType
                import datetime
                timestamp_dt = datetime.datetime.utcfromtimestamp(current_timestamp)
                timestamp_var = Variable(timestamp_dt, VariableType.TIMESTAMP)
                self.playbook.variables.add(action.variable, timestamp_var)
                log.debug(f"Added timestamp variable '{action.variable}' to variable registry")
            
            log.info(f"Saved timestamp {current_timestamp} to variable {action.variable}")
            
            return ActionResult(
                success=True,
                message=f"Timestamp saved to {action.variable}",
                data={action.variable: current_timestamp}
            )
        except Exception as e:
            return ActionResult(success=False, message=str(e))
    
    def _is_test_action_result(self, action_result: ActionResult) -> bool:
        """Check if an action result corresponds to a test execution."""
        if action_result.data and isinstance(action_result.data, dict):
            # Check if this was a test action by looking at the result data structure
            result_data = action_result.data.get('result', {})
            return 'status' in result_data and 'details' in result_data
        return False