"""
Playbook Controller for WebSocket-based Experiment Execution.

This module provides the PlaybookController class that translates YAML playbook
actions and tests into WebSocket commands for execution on the VM. It handles
local CV/OCR for target resolution and maintains proper execution order.
"""

import asyncio
import logging
import base64
from pathlib import Path
from typing import Dict, List, Tuple, Optional, Any
from dataclasses import dataclass
import time
import jinja2

# Playbook and test imports
from adare.types.playbook import (
    parse_playbook, Config, ActionType, Target, SaveTimestampAction,
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


class PlaybookController:
    """
    Controller for executing YAML playbooks via WebSocket.
    
    This controller translates playbook actions into WebSocket tool calls,
    performs local CV/OCR for target resolution, and maintains proper
    execution order with timing and conditional logic.
    """
    
    def __init__(self, websocket_client: AdareVMClient, experiment_dir: Path, project_dir: Path, mcp_gui_url: str = "http://localhost:13109/mcp", debug_screenshots: bool = False, screenshots_dir: Path = None):
        """
        Initialize the playbook controller.
        
        Args:
            websocket_client: Connected WebSocket client to adarevm
            experiment_dir: Path to experiment directory (for images/)
            project_dir: Path to project directory (for testfunctions/)
            mcp_gui_url: URL of the MCP GUI server for CV/OCR
            debug_screenshots: Whether to save screenshots for debugging
            screenshots_dir: Directory to save debug screenshots
        """
        self.client = websocket_client
        self.experiment_dir = experiment_dir
        self.project_dir = project_dir
        self.execution_context = {}
        self.action_results: List[ActionResult] = []
        self.debug_screenshots = debug_screenshots
        self.screenshots_dir = screenshots_dir
        self.screenshot_counter = 0
        
        # Target resolution using MCP GUI server
        self.target_resolver = MCPTargetResolver(experiment_dir, mcp_gui_url)
        self.condition_checker = MCPConditionChecker(self.target_resolver)
        
        # Performance tracking
        self.start_time: Optional[float] = None
        self.action_timings: Dict[str, float] = {}
        
        
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
        
        try:
            # 1. Load testfunctions and testset FIRST (required for playbook test actions)
            await self.load_tests(experiment_dir)
            
            # 2. Execute playbook actions (can now use loaded tests)
            playbook_path = experiment_dir / "playbook.yaml"
            if playbook_path.exists():
                log.info("Executing playbook actions...")
                playbook_result = await self.execute_playbook(playbook_path)
                if not playbook_result.success:
                    return playbook_result
            else:
                log.warning("No playbook.yaml found, skipping GUI actions")
            
            # 3. Run any additional tests
            await self.run_final_tests(experiment_dir)
            
            execution_time = time.time() - self.start_time
            log.info(f"Experiment completed successfully in {execution_time:.2f}s")
            
            return PlaybookExecutionResult(
                success=True,
                total_actions=len(self.action_results),
                successful_actions=sum(1 for r in self.action_results if r.success),
                failed_actions=sum(1 for r in self.action_results if not r.success),
                execution_time=execution_time,
                action_results=self.action_results
            )
            
        except Exception as e:
            execution_time = time.time() - (self.start_time or time.time())
            log.error(f"Experiment execution failed: {e}")
            
            return PlaybookExecutionResult(
                success=False,
                total_actions=len(self.action_results),
                successful_actions=sum(1 for r in self.action_results if r.success),
                failed_actions=sum(1 for r in self.action_results if not r.success),
                execution_time=execution_time,
                action_results=self.action_results,
                error_message=str(e)
            )
    
    async def execute_playbook(self, playbook_path: Path) -> PlaybookExecutionResult:
        """
        Execute YAML playbook actions in order.
        
        Args:
            playbook_path: Path to playbook.yaml file
            
        Returns:
            PlaybookExecutionResult with execution details
        """
        log.info(f"Parsing playbook: {playbook_path}")
        config = parse_playbook(playbook_path)
        
        # Set up experiment variables and config access
        self.execution_context['config'] = config
        if hasattr(config, 'variables') and config.variables:
            log.info("Setting experiment variables...")
            await self.client.set_variables(config.variables)
            self.execution_context.update(config.variables)
        
        # Execute actions sequentially
        total_actions = len(config.actions)
        log.info(f"Executing {total_actions} playbook actions...")
        
        for i, action in enumerate(config.actions):
            action_name = type(action).__name__
            log.info(f"Executing action {i+1}/{total_actions}: {action_name}")
            
            # Execute the action
            start_time = time.time()
            result = await self.execute_action(action)
            execution_time = time.time() - start_time
            
            result.execution_time = execution_time
            self.action_results.append(result)
            self.action_timings[f"action_{i+1}_{action_name}"] = execution_time
            
            if not result.success:
                log.error(f"Action {i+1} failed: {result.message}")
                # Stop execution by default after failed action
                break
            
            # Apply global idle setting
            if hasattr(config, 'settings') and config.settings and config.settings.idle:
                await self.client.idle(config.settings.idle)
        
        successful = sum(1 for r in self.action_results if r.success)
        failed = len(self.action_results) - successful
        
        return PlaybookExecutionResult(
            success=failed == 0,
            total_actions=total_actions,
            successful_actions=successful,
            failed_actions=failed,
            execution_time=sum(self.action_timings.values()),
            action_results=self.action_results
        )
    
    async def execute_action(self, action: ActionType) -> ActionResult:
        """
        Execute a single playbook action by translating to WebSocket calls.
        
        Args:
            action: Playbook action to execute
            
        Returns:
            ActionResult with execution details
        """
        try:
            action_type = type(action).__name__
            description = getattr(action, 'description', '')
            log.debug(f"Executing {action_type}: {description}")
            
            # Dispatch to appropriate handler
            if isinstance(action, ClickAction):
                return await self._execute_click(action)
            elif isinstance(action, RightClickAction):
                return await self._execute_right_click(action)
            elif isinstance(action, DoubleClickAction):
                return await self._execute_double_click(action)
            elif isinstance(action, DragAction):
                return await self._execute_drag(action)
            elif isinstance(action, KeyboardAction):
                return await self._execute_keyboard(action)
            elif isinstance(action, IdleAction):
                return await self._execute_idle(action)
            elif isinstance(action, ScrollAction):
                return await self._execute_scroll(action)
            elif isinstance(action, GotoAction):
                return await self._execute_goto(action)
            elif isinstance(action, ScreenshotAction):
                return await self._execute_screenshot(action)
            elif isinstance(action, CommandAction):
                return await self._execute_command(action)
            elif isinstance(action, ActionTestAction):
                return await self._execute_test(action)
            elif isinstance(action, BlockAction):
                return await self._execute_block(action)
            elif isinstance(action, SaveTimestampAction):
                return await self._execute_save_timestamp(action)
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
        
        # Upload testset configuration (YAML)
        testset_path = experiment_dir / "testset.yml"
        if testset_path.exists():
            log.info("Uploading testset configuration...")
            try:
                testset_yaml = testset_path.read_text()
                await self.client.upload_testset(testset_yaml)
                log.info("Testset loaded successfully - tests are now available for playbook actions")
            except Exception as e:
                log.error(f"Failed to upload testset: {e}")
        else:
            log.warning("No testset.yml found - test actions in playbook will fail")
    
    async def run_final_tests(self, experiment_dir: Path):
        """
        Run final tests after playbook execution.
        
        Args:
            experiment_dir: Path to experiment directory
        """
        testset_path = experiment_dir / "testset.yml"
        if testset_path.exists():
            log.info("Running final test suite...")
            try:
                result = await self.client.run_all_tests()
                log.info(f"Final test execution completed: {result}")
            except Exception as e:
                log.error(f"Failed to run final tests: {e}")
        else:
            log.info("No testset.yml found, skipping final tests")
    
    # Action execution methods will be implemented in the next part...
    
    async def _execute_click(self, action: ClickAction) -> ActionResult:
        """Execute click action."""
        coords = await self._resolve_target(action.target)
        if not coords:
            return ActionResult(
                success=False,
                message=f"Could not resolve target: {action.target}"
            )
        
        x, y = int(coords[0]), int(coords[1])
        try:
            result = await self.client.click(x, y)
            return ActionResult(
                success=result.get('status') == 'success',
                message=result.get('message', ''),
                coordinates=(x, y)
            )
        except Exception as e:
            return ActionResult(
                success=False,
                message=str(e),
                coordinates=(x, y)
            )
    
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
    
    async def _resolve_target(self, target: Target) -> Optional[Tuple[int, int]]:
        """
        Resolve target to screen coordinates using MCP GUI server.
        
        Args:
            target: Target to resolve
            
        Returns:
            Coordinates if found, None otherwise
        """
        try:
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
    
    async def _execute_keyboard(self, action: KeyboardAction) -> ActionResult:
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
    
    async def _execute_idle(self, action: IdleAction) -> ActionResult:
        """Execute idle action."""
        try:
            result = await self.client.idle(action.duration)
            return ActionResult(
                success=result.get('status') == 'success',
                message=result.get('message', '')
            )
        except Exception as e:
            return ActionResult(success=False, message=str(e))
    
    async def _execute_screenshot(self, action: ScreenshotAction) -> ActionResult:
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
    
    async def _execute_test(self, action: ActionTestAction) -> ActionResult:
        """Execute individual test action."""
        try:
            result = await self.client.run_test(action.name)
            return ActionResult(
                success=result.get('status') == 'success',
                message=result.get('message', ''),
                data=result
            )
        except Exception as e:
            error_msg = str(e)
            if "No testset loaded" in error_msg or "testset" in error_msg.lower():
                return ActionResult(
                    success=False, 
                    message=f"No testset loaded - ensure testset.yml exists and loads successfully before test actions"
                )
            return ActionResult(success=False, message=error_msg)
    
    async def _execute_block(self, action: BlockAction) -> ActionResult:
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
        
        # Execute all actions in block
        results = []
        for block_action in action.actions:
            result = await self.execute_action(block_action)
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
            message=f"Block executed successfully ({len(results)} actions)"
        )
    
    # Placeholder implementations for other actions
    async def _execute_right_click(self, action: RightClickAction) -> ActionResult:
        coords = await self._resolve_target(action.target)
        if coords:
            result = await self.client.right_click(coords[0], coords[1])
            return ActionResult(success=result.get('status') == 'success')
        return ActionResult(success=False, message="Could not resolve target")
    
    async def _execute_double_click(self, action: DoubleClickAction) -> ActionResult:
        coords = await self._resolve_target(action.target)
        if coords:
            result = await self.client.double_click(coords[0], coords[1])
            return ActionResult(success=result.get('status') == 'success')
        return ActionResult(success=False, message="Could not resolve target")
    
    async def _execute_drag(self, action: DragAction) -> ActionResult:
        src_coords = await self._resolve_target(action.source)
        dst_coords = await self._resolve_target(action.destination)
        if src_coords and dst_coords:
            result = await self.client.drag(src_coords[0], src_coords[1], dst_coords[0], dst_coords[1])
            return ActionResult(success=result.get('status') == 'success')
        return ActionResult(success=False, message="Could not resolve targets")
    
    async def _execute_scroll(self, action: ScrollAction) -> ActionResult:
        result = await self.client.scroll(action.direction, action.amount or 3)
        return ActionResult(success=result.get('status') == 'success')
    
    async def _execute_goto(self, action: GotoAction) -> ActionResult:
        coords = await self._resolve_target(action.target)
        if coords:
            result = await self.client.goto(coords[0], coords[1])
            return ActionResult(success=result.get('status') == 'success')
        return ActionResult(success=False, message="Could not resolve target")
    
    def _replace_variables(self, text: str) -> str:
        """Replace Jinja2 template variables in text with values from execution context.
        
        Performs recursive replacement to handle nested variables like:
        username: "vagrant"
        filepath: "C:/Users/{{ username }}/Documents/file.txt"
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
                
                # Perform template replacement
                log.debug(f"Processing template: '{result}' with context keys: {list(self.execution_context.keys())}")
                template = jinja2.Template(result)
                new_result = template.render(self.execution_context)
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
    
    async def _execute_command(self, action: CommandAction) -> ActionResult:
        try:
            # Handle both old and new command formats
            command = action.cmd or action.command
            
            # Replace variables in the command
            command = self._replace_variables(command)
            
            # Replace variables in other options as well
            cwd = self._replace_variables(action.cwd) if action.cwd else None
            env = {k: self._replace_variables(str(v)) for k, v in action.env.items()} if action.env else None
            
            # Execute raw shell command directly with options
            result = await self.client.execute_shell(
                shell_command=command,
                cwd=cwd,
                env=env,
                timeout=action.timeout,
                shell=action.shell
            )
            return ActionResult(
                success=result.get('status') == 'success',
                message=result.get('message', ''),
                data=result
            )
        except Exception as e:
            return ActionResult(success=False, message=str(e))
    
    async def _execute_save_timestamp(self, action: SaveTimestampAction) -> ActionResult:
        """Save current timestamp to execution context for later use in tests."""
        try:
            current_timestamp = time.time()
            self.execution_context[action.variable] = current_timestamp
            log.info(f"Saved timestamp {current_timestamp} to variable {action.variable}")
            return ActionResult(
                success=True,
                message=f"Timestamp saved to {action.variable}",
                data={action.variable: current_timestamp}
            )
        except Exception as e:
            return ActionResult(success=False, message=str(e))