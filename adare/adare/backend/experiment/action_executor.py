"""
Action Executor for Playbook Controller

This module orchestrates playbook action execution by delegating to specialized executors.
"""

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any, Optional

from adare.backend.experiment.target_resolver import MCPConditionChecker, MCPTargetResolver
from adare.backend.experiment.websocket_client import AdareVMClient
from adare.types.playbook import (
    ActionTestAction,
    ActionType,
    BlockAction,
    ClickAction,
    CommandAction,
    ContinueAction,
    DragAction,
    GotoAction,
    IdleAction,
    KeyboardAction,
    LoopAction,
    PauseAction,
    PullAction,
    PullChangedFilesAction,
    SaveTimestampAction,
    SaveVariableAction,
    ScreenshotAction,
    ScrollAction,
    SnapshotFilesystemAction,
    StopAction,
    WaitUntilAction,
)

# Import modular executors
from .execution.base import ActionResult
from .execution.flow_control import FlowControlExecutor
from .execution.simple_actions import SimpleActionsExecutor
from .execution.target_resolution import TargetResolutionExecutor
from .execution.test_actions import TestActionsExecutor

if TYPE_CHECKING:
    from adare.hypervisor.virtualbox.vm import VirtualBoxVM

log = logging.getLogger(__name__)

# Re-export ActionResult for backward compatibility
__all__ = ['ActionExecutor', 'ActionResult', 'MachineHandles']


@dataclass
class MachineHandles:
    """One machine's action-dispatch handles within a (possibly multi-machine) playbook run.

    Single-VM playbooks (no `machines:` key) get exactly one of these, under the
    implicit `None` key. Multi-machine playbooks get one per declared machine,
    each with its own VM, websocket client and CV/OCR resolver.
    """

    vm: Optional['VirtualBoxVM'] = None
    client: AdareVMClient | None = None
    vm_os: str | None = None
    vm_user: str | None = None
    mcp_gui_url: str = "http://localhost:13109/mcp"
    target_resolver: MCPTargetResolver | None = None
    condition_checker: MCPConditionChecker | None = None


class ActionExecutor:
    """
    Orchestrates execution of playbook actions by delegating to specialized executors.

    This class serves as the main entry point for action execution, routing actions
    to appropriate specialized executors based on action type.
    """

    def __init__(
        self,
        websocket_client: AdareVMClient = None,
        target_resolver: MCPTargetResolver = None,
        condition_checker: MCPConditionChecker = None,
        experiment_run_id: str | None = None,
        playbook=None,
        execution_context: dict[str, Any] = None,
        debug_screenshots: bool = False,
        screenshots_dir: Path | None = None,
        vm: Optional['VirtualBoxVM'] = None,
        experiment_run_directory: Path | None = None,
        flow_console=None,
        machines: dict[str | None, MachineHandles] | None = None,
    ):
        """
        Initialize the action executor.

        Args:
            websocket_client: (legacy, single-machine) Connected WebSocket client to adarevm
            target_resolver: (legacy, single-machine) Target resolver for image/text targets
            condition_checker: (legacy, single-machine) Condition checker for block actions
            experiment_run_id: Experiment run ID for event emission
            playbook: Playbook reference for variable access
            execution_context: Execution context for variable resolution
            debug_screenshots: Whether to save screenshots for debugging
            screenshots_dir: Directory to save debug screenshots
            vm: (legacy, single-machine) VirtualBox VM instance for file operations
            experiment_run_directory: Run directory for artifacts
            flow_console: Flow console for interactive display and input
            machines: Per-machine dispatch handles for a multi-machine playbook. When
                omitted, a single-entry dict is built from the legacy singular
                kwargs above (the None key) -- unchanged behavior for single-VM
                playbooks and for direct callers that predate multi-machine support.
        """
        if machines is not None:
            self.machines = machines
        else:
            self.machines = {
                None: MachineHandles(
                    vm=vm,
                    client=websocket_client,
                    target_resolver=target_resolver,
                    condition_checker=condition_checker,
                )
            }
        self._primary_machine_key = next(iter(self.machines))
        primary = self.machines[self._primary_machine_key]

        self.client = primary.client
        self.target_resolver = primary.target_resolver
        self.condition_checker = primary.condition_checker
        self.vm = primary.vm
        self.experiment_run_id = experiment_run_id
        self.playbook = playbook
        self.execution_context = execution_context if execution_context is not None else {}
        self.debug_screenshots = debug_screenshots
        self.screenshots_dir = screenshots_dir
        self.experiment_run_directory = experiment_run_directory
        self.flow_console = flow_console

        # Initialize specialized executors, seeded from the primary machine. Every
        # existing single-VM playbook has exactly one machine (the None key), so
        # this is byte-for-byte what construction did before machines existed.
        self.target_resolution = TargetResolutionExecutor(
            websocket_client=self.client,
            target_resolver=self.target_resolver,
            experiment_run_id=experiment_run_id,
            debug_screenshots=debug_screenshots,
            screenshots_dir=screenshots_dir,
        )

        # CRITICAL: Pass the SAME execution_context reference to both executors
        # This ensures captured variables from commands are visible to stop/continue conditions
        self.simple_actions = SimpleActionsExecutor(
            websocket_client=self.client,
            target_resolution_executor=self.target_resolution,
            experiment_run_id=experiment_run_id,
            playbook=playbook,
            execution_context=execution_context,  # Pass reference, not self.execution_context
            vm=self.vm,
            experiment_run_directory=experiment_run_directory,
        )

        # Wire GUI executor to target resolution for mode-aware screenshots
        self.target_resolution.gui_executor = self.simple_actions.gui_executor

        self.flow_control = FlowControlExecutor(
            websocket_client=self.client,
            target_resolution_executor=self.target_resolution,
            condition_checker=self.condition_checker,
            experiment_run_id=experiment_run_id,
            execution_context=execution_context,  # Pass reference, not self.execution_context
            flow_console=flow_console,
        )

        self.test_actions = TestActionsExecutor(experiment_run_directory=experiment_run_directory, playbook=playbook)

    def _rebind_to_machine(self, handles: MachineHandles) -> None:
        """Point this executor and its sub-executors at one machine's handles.

        Touches the same attribute set ``PlaybookController.update_websocket_client``
        touches for session-restore reconnects (``client`` on each sub-executor),
        plus ``vm``/``target_resolver``/``condition_checker`` -- a different
        ``machine:`` means a genuinely different VM/resolver, not just a refreshed
        socket on the same one. ``TestActionsExecutor`` needs no rebind: it already
        takes the client/resolver as per-call parameters (see ``execute_action``).
        """
        self.client = handles.client
        self.vm = handles.vm
        self.target_resolver = handles.target_resolver
        self.condition_checker = handles.condition_checker

        self.target_resolution.client = handles.client
        self.target_resolution.target_resolver = handles.target_resolver

        self.simple_actions.client = handles.client
        self.simple_actions.vm = handles.vm

        gui_executor = getattr(self.simple_actions, 'gui_executor', None)
        if gui_executor is not None:
            if hasattr(gui_executor, 'client'):
                gui_executor.client = handles.client
            if hasattr(gui_executor, 'vm'):
                gui_executor.vm = handles.vm

        self.flow_control.client = handles.client
        self.flow_control.condition_checker = handles.condition_checker

    def set_test_loader(self, test_loader):
        """Set the test loader after initialization."""
        self.test_actions.set_test_loader(test_loader)
        self.test_loader = test_loader  # Keep reference for backward compatibility

    async def execute_action(
        self,
        action: ActionType,
        parent_event_id: str = None,
        event_emitter=None,
        variable_resolver=None,
        action_context: str = None,
    ) -> ActionResult:
        """
        Execute a single playbook action by delegating to appropriate executor.

        Args:
            action: Playbook action to execute
            parent_event_id: Parent event ID for nested actions
            event_emitter: Event emitter instance for creating events
            variable_resolver: Variable resolver for template processing
            action_context: Debug context string for screenshot filenames (e.g. 'a03_click_L_img_button')

        Returns:
            ActionResult with execution details
        """
        try:
            # Set action prefix for find-step screenshots
            self.target_resolution.current_action_prefix = action_context

            # Resolve variables in action fields first
            if variable_resolver:
                resolved_action = variable_resolver.resolve_action_variables(action, self.execution_context)
            else:
                resolved_action = action

            # Multi-machine routing: rebind to the action's target machine (or stay
            # on the primary machine) before dispatch. Single-machine playbooks
            # always resolve to the same (None) machine, so this is a no-op
            # reassignment for them -- see _rebind_to_machine.
            target_key = getattr(resolved_action, 'machine', None)
            if target_key is None:
                target_key = self._primary_machine_key
            self._rebind_to_machine(self.machines.get(target_key, self.machines[self._primary_machine_key]))

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
                result = await self.simple_actions.execute_save_timestamp(
                    resolved_action, parent_event_id, event_emitter
                )

            elif isinstance(resolved_action, SaveVariableAction):
                result = await self.simple_actions.execute_save_variable(
                    resolved_action, parent_event_id, event_emitter
                )

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
                    action_executor=self,  # Pass self for nested action execution
                )

            elif isinstance(resolved_action, BlockAction):
                result = await self.flow_control.execute_block(
                    resolved_action,
                    parent_event_id=parent_event_id,
                    event_emitter=event_emitter,
                    variable_resolver=variable_resolver,
                    action_executor=self,  # Pass self for nested action execution
                )

            elif isinstance(resolved_action, LoopAction):
                result = await self.flow_control.execute_loop(
                    resolved_action,
                    parent_event_id=parent_event_id,
                    event_emitter=event_emitter,
                    variable_resolver=variable_resolver,
                    action_executor=self,  # Pass self for nested action execution
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
                result = await self.simple_actions.execute_snapshot_filesystem(
                    resolved_action, parent_event_id, event_emitter
                )

            elif isinstance(resolved_action, PullChangedFilesAction):
                result = await self.simple_actions.execute_pull_changed_files(
                    resolved_action, parent_event_id, event_emitter
                )

            else:
                result = ActionResult(success=False, message=f"Unknown action type: {action_type}")

            # Post-execution debug screenshot (if enabled and action was successful)
            if self.debug_screenshots and result and result.success:
                # Only capture for GUI-modifying actions (exclude non-GUI actions)
                non_gui_actions = (
                    IdleAction,
                    SaveTimestampAction,
                    SaveVariableAction,
                    PullAction,
                    BlockAction,
                    LoopAction,
                    ActionTestAction,
                    WaitUntilAction,
                    PauseAction,
                    StopAction,
                    ContinueAction,
                    SnapshotFilesystemAction,
                    PullChangedFilesAction,
                )
                if not isinstance(resolved_action, non_gui_actions):
                    try:
                        # Capture and save post-execution screenshot
                        # This reuses the existing screenshot infrastructure in target_resolution
                        await self.target_resolution.get_current_screenshot_with_path(action_context=action_context)
                    except (OSError, ConnectionError, TimeoutError, RuntimeError) as screenshot_error:
                        # Don't fail the action if screenshot capture fails
                        log.warning(f"Failed to capture post-execution debug screenshot: {screenshot_error}")

            return result

        except Exception as e:  # noqa: BLE001 -- top-level action handler; must convert any failure to ActionResult
            log.error(f"Error executing action: {e}", exc_info=True)
            return ActionResult(success=False, message=f"Exception: {str(e)}")

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
