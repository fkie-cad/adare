"""
Action Executor for Playbook Controller

This module orchestrates playbook action execution by delegating to specialized executors.
"""

import logging
from typing import Dict, Optional, Any
from pathlib import Path

from adare.types.playbook import (
    ActionType, ClickAction, DragAction, KeyboardAction, IdleAction,
    ScrollAction, GotoAction, CommandAction, ScreenshotAction, BlockAction,
    ActionTestAction, SaveTimestampAction, PullAction, PauseAction,
    WaitUntilAction, LoopAction, StopAction, ContinueAction, SnapshotFilesystemAction
)
from adare.backend.experiment.websocket_client import AdareVMClient
from adare.backend.experiment.target_resolver import MCPTargetResolver, MCPConditionChecker

# Import modular executors
from .execution.base import ActionResult
from .execution.target_resolution import TargetResolutionExecutor
from .execution.simple_actions import SimpleActionsExecutor
from .execution.flow_control import FlowControlExecutor
from .execution.test_actions import TestActionsExecutor

log = logging.getLogger(__name__)

# Re-export ActionResult for backward compatibility
__all__ = ['ActionExecutor', 'ActionResult']


class ActionExecutor:
    """
    Orchestrates execution of playbook actions by delegating to specialized executors.

    This class serves as the main entry point for action execution, routing actions
    to appropriate specialized executors based on action type.
    """

    def __init__(self, websocket_client: AdareVMClient, target_resolver: MCPTargetResolver,
                 condition_checker: MCPConditionChecker, experiment_run_id: Optional[str] = None,
                 playbook = None, execution_context: Dict[str, Any] = None,
                 debug_screenshots: bool = False, screenshots_dir: Optional[Path] = None,
                 vm: Optional['VirtualBoxVM'] = None, experiment_run_directory: Optional[Path] = None,
                 flow_console = None):
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
            vm: VirtualBox VM instance for file operations
            experiment_run_directory: Run directory for artifacts
            flow_console: Flow console for interactive display and input
        """
        self.client = websocket_client
        self.target_resolver = target_resolver
        self.condition_checker = condition_checker
        self.experiment_run_id = experiment_run_id
        self.playbook = playbook
        self.execution_context = execution_context if execution_context is not None else {}
        self.debug_screenshots = debug_screenshots
        self.screenshots_dir = screenshots_dir
        self.vm = vm
        self.experiment_run_directory = experiment_run_directory
        self.flow_console = flow_console

        # Initialize specialized executors
        self.target_resolution = TargetResolutionExecutor(
            websocket_client=websocket_client,
            target_resolver=target_resolver,
            experiment_run_id=experiment_run_id,
            debug_screenshots=debug_screenshots,
            screenshots_dir=screenshots_dir
        )

        # CRITICAL: Pass the SAME execution_context reference to both executors
        # This ensures captured variables from commands are visible to stop/continue conditions
        self.simple_actions = SimpleActionsExecutor(
            websocket_client=websocket_client,
            target_resolution_executor=self.target_resolution,
            experiment_run_id=experiment_run_id,
            playbook=playbook,
            execution_context=execution_context,  # Pass reference, not self.execution_context
            vm=vm,
            experiment_run_directory=experiment_run_directory
        )

        self.flow_control = FlowControlExecutor(
            websocket_client=websocket_client,
            target_resolution_executor=self.target_resolution,
            condition_checker=condition_checker,
            experiment_run_id=experiment_run_id,
            execution_context=execution_context,  # Pass reference, not self.execution_context
            flow_console=flow_console
        )

        self.test_actions = TestActionsExecutor(
            experiment_run_directory=experiment_run_directory,
            playbook=playbook
        )

    def set_test_loader(self, test_loader):
        """Set the test loader after initialization."""
        self.test_actions.set_test_loader(test_loader)
        self.test_loader = test_loader  # Keep reference for backward compatibility

    async def execute_action(self, action: ActionType, parent_event_id: str = None,
                           event_emitter = None, variable_resolver = None) -> ActionResult:
        """
        Execute a single playbook action by delegating to appropriate executor.

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

            # Dispatch to appropriate executor and capture result
            result = None
            if isinstance(resolved_action, ClickAction):
                result = await self.simple_actions.execute_click(resolved_action, parent_event_id, event_emitter)

            elif isinstance(resolved_action, DragAction):
                result = await self.simple_actions.execute_drag(resolved_action, parent_event_id, event_emitter)

            elif isinstance(resolved_action, KeyboardAction):
                result = await self.simple_actions.execute_keyboard(resolved_action, parent_event_id, event_emitter)

            elif isinstance(resolved_action, IdleAction):
                result = await self.simple_actions.execute_idle(resolved_action, parent_event_id, event_emitter)

            elif isinstance(resolved_action, ScrollAction):
                result = await self.simple_actions.execute_scroll(resolved_action, parent_event_id, event_emitter)

            elif isinstance(resolved_action, GotoAction):
                result = await self.simple_actions.execute_goto(resolved_action, parent_event_id, event_emitter)

            elif isinstance(resolved_action, ScreenshotAction):
                result = await self.simple_actions.execute_screenshot(resolved_action, parent_event_id, event_emitter)

            elif isinstance(resolved_action, CommandAction):
                result = await self.simple_actions.execute_command(resolved_action, parent_event_id, event_emitter)

            elif isinstance(resolved_action, SaveTimestampAction):
                result = await self.simple_actions.execute_save_timestamp(resolved_action, parent_event_id, event_emitter)

            elif isinstance(resolved_action, PullAction):
                result = await self.simple_actions.execute_pull(resolved_action, parent_event_id, event_emitter)

            elif isinstance(resolved_action, ActionTestAction):
                result = await self.test_actions.execute_test(
                    resolved_action,
                    websocket_client=self.client,
                    target_resolver=self.target_resolver,
                    parent_event_id=parent_event_id,
                    event_emitter=event_emitter,
                    execution_context=self.execution_context,
                    action_executor=self  # Pass self for nested action execution
                )

            elif isinstance(resolved_action, BlockAction):
                result = await self.flow_control.execute_block(
                    resolved_action,
                    parent_event_id=parent_event_id,
                    event_emitter=event_emitter,
                    variable_resolver=variable_resolver,
                    action_executor=self  # Pass self for nested action execution
                )

            elif isinstance(resolved_action, LoopAction):
                result = await self.flow_control.execute_loop(
                    resolved_action,
                    parent_event_id=parent_event_id,
                    event_emitter=event_emitter,
                    variable_resolver=variable_resolver,
                    action_executor=self  # Pass self for nested action execution
                )

            elif isinstance(resolved_action, WaitUntilAction):
                result = await self.flow_control.execute_wait_until(resolved_action, parent_event_id, event_emitter)

            elif isinstance(resolved_action, PauseAction):
                result = await self.flow_control.execute_pause(resolved_action, parent_event_id, event_emitter)

            elif isinstance(resolved_action, StopAction):
                result = await self.flow_control.execute_stop(resolved_action, parent_event_id, event_emitter)

            elif isinstance(resolved_action, ContinueAction):
                result = await self.flow_control.execute_continue(resolved_action, parent_event_id, event_emitter)

            elif isinstance(resolved_action, SnapshotFilesystemAction):
                result = await self.simple_actions.execute_snapshot_filesystem(resolved_action, parent_event_id, event_emitter)

            else:
                result = ActionResult(
                    success=False,
                    message=f"Unknown action type: {action_type}"
                )

            # Post-execution debug screenshot (if enabled and action was successful)
            if self.debug_screenshots and result and result.success:
                # Only capture for GUI-modifying actions (exclude non-GUI actions)
                non_gui_actions = (IdleAction, SaveTimestampAction, PullAction,
                                   BlockAction, LoopAction, ActionTestAction,
                                   WaitUntilAction, PauseAction, StopAction, ContinueAction,
                                   SnapshotFilesystemAction)
                if not isinstance(resolved_action, non_gui_actions):
                    try:
                        # Capture and save post-execution screenshot
                        # This reuses the existing screenshot infrastructure in target_resolution
                        await self.target_resolution.get_current_screenshot_with_path()
                    except Exception as screenshot_error:
                        # Don't fail the action if screenshot capture fails
                        log.warning(f"Failed to capture post-execution debug screenshot: {screenshot_error}")

            return result

        except Exception as e:
            log.error(f"Error executing action: {e}", exc_info=True)
            return ActionResult(
                success=False,
                message=f"Exception: {str(e)}"
            )

    async def execute_programmatic_pull(self, src_path: str, description: str = "Programmatic pull") -> ActionResult:
        """
        Execute a pull operation programmatically without a formal PullAction.

        This method is used for auto-pulls triggered by test failures or other
        programmatic scenarios where we need to pull files without explicit
        playbook pull actions.

        Args:
            src_path: Source path on VM to pull from
            description: Description for logging

        Returns:
            ActionResult with pull operation details
        """
        return await self.simple_actions.execute_programmatic_pull(src_path, description)
