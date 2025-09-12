"""
Action Executor for Playbook Controller

This module contains all individual action execution methods, providing clean
separation of action handling logic from the main controller orchestration.
"""

import logging
import time
import base64
from typing import Dict, List, Tuple, Optional, Any
from dataclasses import dataclass
from pathlib import Path

from adare.types.playbook import (
    ActionType, ClickAction, DragAction,
    KeyboardAction, IdleAction, ScrollAction, GotoAction, 
    CommandAction, ScreenshotAction, BlockAction, ActionTestAction,
    SaveTimestampAction, PullAction
)
from adare.backend.experiment.websocket_client import AdareVMClient
from adare.backend.experiment.target_resolver import MCPTargetResolver, MCPConditionChecker
from adare.types.step_actions import FindAction, ExecuteAction

# Import for event emission
from adare.backend.events.emitters import emit_action

log = logging.getLogger(__name__)


@dataclass
class ActionResult:
    """Result of a playbook action execution."""
    success: bool
    message: str = ""
    coordinates: Optional[Tuple[int, int]] = None
    data: Optional[Dict] = None
    execution_time: Optional[float] = None


class ActionExecutor:
    """
    Handles execution of individual playbook actions.
    
    This class contains all the _execute_* methods that were previously in
    PlaybookController, providing clean separation of concerns.
    """
    
    def __init__(self, websocket_client: AdareVMClient, target_resolver: MCPTargetResolver, 
                 condition_checker: MCPConditionChecker, experiment_run_id: Optional[str] = None,
                 playbook = None, execution_context: Dict[str, Any] = None,
                 debug_screenshots: bool = False, screenshots_dir: Optional[Path] = None,
                 vm: Optional['VirtualBoxVM'] = None, experiment_run_directory: Optional[Path] = None):
        """
        Initialize the action executor.
        
        Args:
            websocket_client: Connected WebSocket client to adarevm
            target_resolver: Target resolver for image/text targets
            condition_checker: Condition checker for block actions
            experiment_run_id: Experiment run ID for event emission
            playbook: Playbook reference for variable access
            execution_context: Execution context for variable resolution
            debug_screenshots: Whether to save screenshots for debugging
            screenshots_dir: Directory to save debug screenshots
        """
        self.client = websocket_client
        self.target_resolver = target_resolver
        self.condition_checker = condition_checker
        self.experiment_run_id = experiment_run_id
        self.playbook = playbook
        self.execution_context = execution_context or {}
        self.debug_screenshots = debug_screenshots
        self.screenshots_dir = screenshots_dir
        self.screenshot_counter = 0
        self.vm = vm  # VirtualBox VM instance for file operations
        self.experiment_run_directory = experiment_run_directory  # Run directory for artifacts
        
        # Initialize action handlers mapping - now handled by _get_click_handler
        self._action_handlers = {}
    
    def _get_click_handler(self, click_type: str):
        """Get the appropriate click handler based on click type."""
        if click_type == 'right':
            return lambda x, y: self.client.right_click(x, y)
        elif click_type == 'double':
            return lambda x, y: self.client.double_click(x, y)
        else:  # 'left' or default
            return lambda x, y: self.client.click(x, y)
    
    async def execute_action(self, action: ActionType, parent_event_id: str = None, 
                           event_emitter = None, variable_resolver = None) -> ActionResult:
        """
        Execute a single playbook action by translating to WebSocket calls.
        
        Args:
            action: Playbook action to execute
            parent_event_id: Parent event ID for nested actions
            event_emitter: Event emitter instance for creating events
            variable_resolver: Variable resolver for template processing
            
        Returns:
            ActionResult with execution details
        """
        try:
            # Resolve variables in action fields first
            if variable_resolver:
                resolved_action = variable_resolver.resolve_action_variables(action, self.execution_context)
            else:
                resolved_action = action
            
            action_type = type(resolved_action).__name__
            description = getattr(resolved_action, 'description', '')
            log.debug(f"Executing {action_type}: {description}")
            
            # Dispatch to appropriate handler using resolved action
            if isinstance(resolved_action, ClickAction):
                return await self._execute_click(resolved_action, parent_event_id, event_emitter)
            elif isinstance(resolved_action, DragAction):
                return await self._execute_drag(resolved_action, parent_event_id, event_emitter)
            elif isinstance(resolved_action, KeyboardAction):
                return await self._execute_keyboard(resolved_action, parent_event_id, event_emitter)
            elif isinstance(resolved_action, IdleAction):
                return await self._execute_idle(resolved_action, parent_event_id, event_emitter)
            elif isinstance(resolved_action, ScrollAction):
                return await self._execute_scroll(resolved_action, parent_event_id, event_emitter)
            elif isinstance(resolved_action, GotoAction):
                return await self._execute_goto(resolved_action, parent_event_id, event_emitter)
            elif isinstance(resolved_action, ScreenshotAction):
                return await self._execute_screenshot(resolved_action, parent_event_id, event_emitter)
            elif isinstance(resolved_action, CommandAction):
                return await self._execute_command(resolved_action, parent_event_id, event_emitter)
            elif isinstance(resolved_action, ActionTestAction):
                return await self._execute_test(resolved_action, parent_event_id, event_emitter)
            elif isinstance(resolved_action, BlockAction):
                return await self._execute_block(resolved_action, parent_event_id, event_emitter, variable_resolver)
            elif isinstance(resolved_action, SaveTimestampAction):
                return await self._execute_save_timestamp(resolved_action, parent_event_id, event_emitter)
            elif isinstance(resolved_action, PullAction):
                return await self._execute_pull(resolved_action, parent_event_id, event_emitter)
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
    
    async def _execute_action_with_steps(self, action, execute_func, parent_action_id: str = None, event_emitter = None) -> ActionResult:
        """Execute an action with steps for target resolution and execution."""
        try:
            # Resolve target with find step (emitted as action event)
            coords = await self._resolve_target_with_steps(action.target, parent_action_id, event_emitter)
            if not coords:
                return ActionResult(
                    success=False,
                    message=f"Could not resolve target: {action.target}"
                )
            
            x, y = int(coords[0]), int(coords[1])
            
            # Create and emit execution step events
            execute_action_id = f"execute_step_{int(time.time()*1000)}"
            
            if self.experiment_run_id and event_emitter:
                # Create execution step action
                execute_step = ExecuteAction(
                    description=f"executing at ({x}, {y})",
                    coordinates=(x, y)
                )
                
                # Emit execution start event using existing unified pattern
                start_event = event_emitter.create_action_start_event(execute_step, -1, execute_action_id, parent_action_id)
                emit_action(self.experiment_run_id, start_event, execute_action_id)
            
            # Execute the action
            start_time = time.time()
            result = await execute_func(x, y)
            execution_time = time.time() - start_time
            execution_success = result.get('status') == 'success'
            
            # Emit execution complete event
            if self.experiment_run_id and event_emitter:
                execute_result = ActionResult(
                    success=execution_success,
                    message=result.get('message', ''),
                    execution_time=execution_time,
                    coordinates=(x, y)
                )
                complete_event = event_emitter.create_action_complete_event(execute_step, -1, execute_action_id, execute_result, parent_action_id)
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
    
    async def _resolve_target_with_steps(self, target, parent_action_id: str = None, event_emitter = None) -> Optional[Tuple[int, int]]:
        """Resolve target with find step emitted as action event."""
        # Apply smart defaults if no strategy specified
        if target.strategy is None:
            from adare.types.playbook import BestConfidenceStrategy, TopLeftStrategy
            if target.image:
                target.strategy = BestConfidenceStrategy()
                log.debug("Applied default BestConfidence strategy for image target")
            elif target.text:
                target.strategy = TopLeftStrategy()
                log.debug("Applied default TopLeft strategy for text target")
            else:
                target.strategy = TopLeftStrategy()
                log.debug("Applied fallback TopLeft strategy for position target")
        
        # Create and emit find step events
        find_action_id = f"find_step_{int(time.time()*1000)}"
        
        if self.experiment_run_id and event_emitter:
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
            start_event = event_emitter.create_action_start_event(find_step, -1, find_action_id, parent_action_id)
            emit_action(self.experiment_run_id, start_event, find_action_id)
        
        try:
            # Get screenshot for target resolution
            start_time = time.time()
            screenshot_base64 = await self._get_current_screenshot()
            if not screenshot_base64:
                log.error("Failed to get screenshot for target resolution")
                
                # Emit find failure event
                if self.experiment_run_id and event_emitter:
                    execution_time = time.time() - start_time
                    find_result = ActionResult(success=False, message="Failed to get screenshot", execution_time=execution_time)
                    complete_event = event_emitter.create_action_complete_event(find_step, -1, find_action_id, find_result, parent_action_id)
                    emit_action(self.experiment_run_id, complete_event, find_action_id)
                
                return None
            
            # Resolve using MCP target resolver
            match = await self.target_resolver.resolve_target(target, screenshot_base64)
            execution_time = time.time() - start_time
            
            # Emit find complete event
            if self.experiment_run_id and event_emitter:
                success = match is not None
                coords = match.coordinates if match else None
                find_result = ActionResult(
                    success=success,
                    message="Target found" if success else "Target not found",
                    execution_time=execution_time,
                    coordinates=coords
                )
                complete_event = event_emitter.create_action_complete_event(find_step, -1, find_action_id, find_result, parent_action_id)
                emit_action(self.experiment_run_id, complete_event, find_action_id)
            
            return match.coordinates if match else None
                
        except Exception as e:
            execution_time = time.time() - start_time if 'start_time' in locals() else 0
            log.error(f"Error resolving target: {e}")
            
            # Emit find failure event  
            if self.experiment_run_id and event_emitter:
                find_result = ActionResult(success=False, message=str(e), execution_time=execution_time)
                complete_event = event_emitter.create_action_complete_event(find_step, -1, find_action_id, find_result, parent_action_id)
                emit_action(self.experiment_run_id, complete_event, find_action_id)
            
            return None
    
    async def _execute_action_with_target(self, action, parent_event_id: str = None, event_emitter = None) -> ActionResult:
        """Execute any action that requires target resolution with steps."""
        if isinstance(action, ClickAction):
            # Use the click type to get the appropriate handler
            handler = self._get_click_handler(action.type)
            return await self._execute_action_with_steps(
                action,
                handler,
                parent_event_id,
                event_emitter
            )
        else:
            return ActionResult(
                success=False,
                message=f"No handler found for action type: {type(action).__name__}"
            )
    
    # Individual action execution methods
    
    async def _execute_click(self, action: ClickAction, parent_event_id: str = None, event_emitter = None) -> ActionResult:
        """Execute click action with steps."""
        return await self._execute_action_with_target(action, parent_event_id, event_emitter)
    
    async def _execute_drag(self, action: DragAction, parent_event_id: str = None, event_emitter = None) -> ActionResult:
        """Execute drag action - special handling for two targets."""
        try:
            # Resolve both targets (each will emit their own find steps with proper parent)
            src_coords = await self._resolve_target_with_steps(action.source, parent_event_id, event_emitter)
            dst_coords = await self._resolve_target_with_steps(action.destination, parent_event_id, event_emitter)
            
            if not src_coords or not dst_coords:
                return ActionResult(success=False, message="Could not resolve targets")
            
            # Create and emit execution step
            execute_action_id = f"execute_step_{int(time.time()*1000)}"
            
            if self.experiment_run_id and event_emitter:
                # Create execution step action
                execute_step = ExecuteAction(
                    description=f"dragging from ({src_coords[0]}, {src_coords[1]}) to ({dst_coords[0]}, {dst_coords[1]})",
                    coordinates=src_coords  # Use source coordinates
                )
                
                # Emit execution start event
                start_event = event_emitter.create_action_start_event(execute_step, -1, execute_action_id, parent_event_id)
                emit_action(self.experiment_run_id, start_event, execute_action_id)
            
            # Execute the drag
            start_time = time.time()
            result = await self.client.drag(src_coords[0], src_coords[1], dst_coords[0], dst_coords[1])
            execution_time = time.time() - start_time
            success = result.get('status') == 'success'
            
            # Emit execution complete event
            if self.experiment_run_id and event_emitter:
                execute_result = ActionResult(
                    success=success,
                    message=result.get('message', ''),
                    execution_time=execution_time,
                    coordinates=dst_coords,  # Use destination coordinates as final result
                    data={'source_coordinates': src_coords, 'dest_coordinates': dst_coords}
                )
                complete_event = event_emitter.create_action_complete_event(execute_step, -1, execute_action_id, execute_result, parent_event_id)
                emit_action(self.experiment_run_id, complete_event, execute_action_id)
            
            return ActionResult(
                success=success,
                message=result.get('message', ''),
                coordinates=src_coords,
                data={'source': action.source, 'destination': action.destination, 'source_coordinates': src_coords, 'dest_coordinates': dst_coords}
            )
            
        except Exception as e:
            return ActionResult(success=False, message=str(e))
    
    async def _execute_keyboard(self, action: KeyboardAction, parent_event_id: str = None, event_emitter = None) -> ActionResult:
        """Execute keyboard action."""
        try:
            if action.key:
                # Single key press -> pyautogui.press()
                result = await self.client.keyboard("press", action.key)
            elif action.text:
                # Text typing -> pyautogui.typewrite()
                result = await self.client.keyboard("type", action.text)
            elif action.combination:
                # Key combinations -> pyautogui.hotkey()
                combo = "+".join(action.combination)
                result = await self.client.keyboard("hotkey", combo)
            else:
                return ActionResult(
                    success=False,
                    message="No key, text, or combination specified"
                )
            
            return ActionResult(
                success=result.get('status') == 'success',
                message=result.get('message', '')
            )
        except Exception as e:
            return ActionResult(success=False, message=str(e))
    
    async def _execute_idle(self, action: IdleAction, parent_event_id: str = None, event_emitter = None) -> ActionResult:
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
    
    async def _execute_screenshot(self, action: ScreenshotAction, parent_event_id: str = None, event_emitter = None) -> ActionResult:
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
    
    async def _execute_scroll(self, action: ScrollAction, parent_event_id: str = None, event_emitter = None) -> ActionResult:
        """Execute scroll action."""
        result = await self.client.scroll(action.direction, action.amount or 3)
        return ActionResult(success=result.get('status') == 'success')
    
    async def _execute_goto(self, action: GotoAction, parent_event_id: str = None, event_emitter = None) -> ActionResult:
        """Execute goto action with steps."""
        return await self._execute_action_with_target(action, parent_event_id, event_emitter)
    
    async def _execute_command(self, action: CommandAction, parent_event_id: str = None, event_emitter = None) -> ActionResult:
        """Execute command action."""
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
    
    async def _execute_test(self, action: ActionTestAction, parent_event_id: str = None, event_emitter = None) -> ActionResult:
        """Execute individual test action with local variable substitution."""
        try:
            # This requires test loading functionality - will be handled by test_loader
            # For now, delegate to the provided test_loader if available
            if hasattr(self, 'test_loader') and self.test_loader:
                resolved_test = await self.test_loader.resolve_test_locally(action.name)
                if not resolved_test:
                    return ActionResult(
                        success=False,
                        message=f"Test '{action.name}' not found in playbook tests"
                    )
                
                # Send resolved test to VM for execution
                result = await self.client.run_test(action.name, resolved_test)
                
                # Extract expect_to_fail flag from resolved test
                expect_to_fail = resolved_test.get('expect_to_fail', False)
                
                # Use TestResultProcessor to handle result processing
                from adare.backend.experiment.test_result_processor import TestResultProcessor
                return TestResultProcessor.process_test_result(action.name, result, expect_to_fail)
            else:
                return ActionResult(
                    success=False,
                    message="Test loader not available"
                )
        except Exception as e:
            error_msg = str(e)
            if "No testset loaded" in error_msg or "testset" in error_msg.lower():
                return ActionResult(
                    success=False, 
                    message=f"No tests loaded - ensure playbook.yml contains tests section and loads successfully before test actions"
                )
            return ActionResult(success=False, message=error_msg)
    
    async def _execute_block(self, action: BlockAction, parent_event_id: str = None, event_emitter = None, variable_resolver = None) -> ActionResult:
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
        block_parent_event_id = parent_event_id
        
        # Execute all actions in block
        results = []
        for i, block_action in enumerate(action.actions):
            # Create sub-action ID
            sub_action_id = f"block_sub_{i}_{int(time.time()*1000)}"
            
            # Emit sub-action start event
            if self.experiment_run_id and event_emitter:
                try:
                    sub_start_event = event_emitter.create_action_start_event(block_action, i, sub_action_id, parent_event_id=block_parent_event_id)
                    emit_action(self.experiment_run_id, sub_start_event, sub_action_id)
                except Exception as e:
                    log.error(f"Failed to emit sub-action start event: {e}")
            
            # Execute the sub-action with variable resolution
            start_time = time.time()
            result = await self.execute_action(block_action, parent_event_id=block_parent_event_id, event_emitter=event_emitter, variable_resolver=variable_resolver)
            execution_time = time.time() - start_time
            result.execution_time = execution_time
            
            # Emit sub-action complete event
            if self.experiment_run_id and event_emitter:
                try:
                    sub_complete_event = event_emitter.create_action_complete_event(block_action, i, sub_action_id, result, parent_event_id=block_parent_event_id)
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
    
    async def _execute_save_timestamp(self, action: SaveTimestampAction, parent_event_id: str = None, event_emitter = None) -> ActionResult:
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

    async def _execute_pull(self, action: PullAction, parent_event_id: str = None, event_emitter = None) -> ActionResult:
        """Pull files/directories from VM to host artifacts directory."""
        try:
            if not self.vm:
                return ActionResult(
                    success=False,
                    message="VM instance not available for pull operation"
                )
            
            if not self.experiment_run_directory:
                return ActionResult(
                    success=False,
                    message="Experiment run directory not available for pull operation"
                )
            
            # Create artifacts directory if it doesn't exist
            artifacts_dir = Path(self.experiment_run_directory) / "artifacts"
            artifacts_dir.mkdir(exist_ok=True)
            
            # Determine destination path
            if action.destination:
                # Use custom destination relative to artifacts directory
                dest_path = artifacts_dir / action.destination
            else:
                # Preserve full guest path structure relative to artifacts directory
                # Remove leading slash to make it relative, then append to artifacts
                guest_path = Path(action.source)
                relative_guest_path = guest_path.relative_to('/') if guest_path.is_absolute() else guest_path
                dest_path = artifacts_dir / relative_guest_path
            
            # Create parent directories if they don't exist
            dest_path.parent.mkdir(parents=True, exist_ok=True)
            
            # Use VirtualBox guest control to copy files (always recursive)
            success = await self.vm.copy_from_guest(
                guest_path=action.source,
                host_path=str(dest_path),
                recursive=True
            )
            
            if success:
                log.info(f"Successfully pulled {action.source} to {dest_path}")
                return ActionResult(
                    success=True,
                    message=f"Pulled {action.source} to artifacts/{dest_path.name}",
                    data={
                        "source": action.source,
                        "destination": str(dest_path),
                        "artifacts_path": f"artifacts/{dest_path.name}"
                    }
                )
            else:
                return ActionResult(
                    success=False,
                    message=f"Failed to pull {action.source}"
                )
            
        except Exception as e:
            log.error(f"Error in pull operation: {e}")
            return ActionResult(
                success=False,
                message=f"Pull operation failed: {str(e)}"
            )
    
    # Utility methods
    
    async def _save_debug_screenshot(self, screenshot_base64: str):
        """
        Save screenshot to disk for debugging purposes.
        
        Args:
            screenshot_base64: Base64 encoded screenshot data
        """
        if not self.debug_screenshots or not self.screenshots_dir:
            return
            
        try:
            # Create screenshots directory if it doesn't exist
            self.screenshots_dir.mkdir(parents=True, exist_ok=True)
            
            # Generate filename with counter
            filename = f"screenshot_{self.screenshot_counter}.png"
            filepath = self.screenshots_dir / filename
            
            # Increment counter for next screenshot
            self.screenshot_counter += 1
            
            # Decode and save the image
            image_data = base64.b64decode(screenshot_base64)
            with open(filepath, 'wb') as f:
                f.write(image_data)
                
            log.debug(f"Debug screenshot saved: {filepath}")
            
        except Exception as e:
            log.error(f"Failed to save debug screenshot: {e}")
    
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
                await self._save_debug_screenshot(screenshot_base64)
                
                log.debug("Screenshot captured")
                return screenshot_base64
            else:
                log.error("Screenshot result missing image data")
                return None
                
        except Exception as e:
            log.error(f"Failed to capture screenshot: {e}")
            return None
    
    def _serialize_target(self, target) -> Optional[Dict[str, Any]]:
        """Serialize Target object for JSON storage."""
        if not target:
            return None
        from adare.types.actions import converter
        return converter.unstructure(target)
    
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