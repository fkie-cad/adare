"""
Diff Mode Execution

Lightweight execution path for running experiments in QEMU GUI mode without agent.
Designed for visual comparison between different OS/software versions.

Features:
- QEMU only (no VirtualBox support)
- No agent installation or WebSocket communication
- Executes only visual/GUI actions (click, keyboard, screenshot, etc.)
- Skips all forensic actions (save_timestamp, snapshot_filesystem, pull, tests)
- No database records (ephemeral mode)
- Uses HOST GUI mode for execution
"""

import logging
import asyncio
import threading
import time
import signal
import ulid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional

from adare.types.playbook import (
    Playbook, ActionType, ClickAction, KeyboardAction, DragAction, ScrollAction,
    GotoAction, ScreenshotAction, IdleAction, PauseAction, BlockAction, LoopAction,
    parse_playbook
)
from adare.types.environment import parse_environment_file
from adare.backend.project.directory import ProjectDirectory
from adare.backend.experiment.directory import ExperimentDirectory, DiffRunDirectory
from adare.backend.experiment.runctx import ExperimentRunCtx, ExperimentConfig
from adare.backend.experiment.vm_lifecycle_manager import VMLifecycleManager
from adare.backend.experiment.execution.base import GUIExecutionMode, ActionResult
from adare.backend.experiment.variable_resolver import VariableResolver
from adarelib.common.variables import VariableRegistry, Variable, VariableType
from adarelib.common.automatic_variables import AutomaticVariables
from adare.backend.experiment.target_resolver import MCPTargetResolver, MCPConditionChecker
from adare.backend.experiment.mcp_server_manager import MCPServerManager
from adare.backend.experiment.action_executor import ActionExecutor
from adare.exceptions import LoggedException
from adare.config.configdirectory import ADAREVM_DIR, ADARELIB_DIR
import adare.backend.environment.database as environment_database
import adare.backend.experiment.database as experiment_database
from adare.backend.experiment.print import flowconsolemanager, ExperimentFlowConsole
from adare.backend.experiment.event_manager import EventManager
from adare.backend.events.emitters import emit_action
import ulid as ulid_module

log = logging.getLogger(__name__)

# Visual actions that can be executed without agent
VISUAL_ACTION_TYPES = {
    ClickAction, KeyboardAction, DragAction, ScrollAction,
    GotoAction, ScreenshotAction, IdleAction, PauseAction
}


@dataclass
class DiffModeResult:
    """Result of diff mode execution."""
    success: bool
    actions_executed: int = 0
    successful_actions: int = 0
    failed_actions: int = 0
    actions_skipped: int = 0
    execution_time: float = 0.0
    error: Optional[str] = None
    diff_run_directory: Optional[Path] = None


def is_visual_action(action: ActionType) -> bool:
    """Check if action can be executed in diff mode (no agent required)."""
    return type(action) in VISUAL_ACTION_TYPES


def filter_nested_actions(actions: List[ActionType]) -> List[ActionType]:
    """Recursively filter nested actions in blocks/loops."""
    filtered = []
    for action in actions:
        if isinstance(action, (BlockAction, LoopAction)):
            # Recursively filter nested actions
            nested_filtered = filter_nested_actions(action.actions)
            if nested_filtered:  # Keep block if any visual actions remain
                # Create a copy with filtered actions
                if isinstance(action, BlockAction):
                    filtered_action = BlockAction(
                        when=action.when,
                        actions=nested_filtered
                    )
                else:  # LoopAction
                    filtered_action = LoopAction(
                        items=action.items,
                        loop_var=action.loop_var,
                        actions=nested_filtered
                    )
                filtered.append(filtered_action)
        elif is_visual_action(action):
            filtered.append(action)
        else:
            log.debug(f"Skipping non-visual action in diff mode: {type(action).__name__}")
    return filtered


def filter_playbook_actions(playbook: Playbook) -> Playbook:
    """Return playbook with only visual actions, recursively filtering blocks."""
    filtered_actions = filter_nested_actions(playbook.actions)

    # Create a new playbook with filtered actions
    playbook.actions = filtered_actions
    return playbook


def __create_and_start_flow_console(experiment_run_ulid: str, disable_printing: bool, external_stop_event: threading.Event = None):
    """
    Create a flow console and start it.

    Args:
        experiment_run_ulid: Used to reference the console if multiple runs at the same time (can be fake)
        disable_printing: If true, the console will not print anything
        external_stop_event: Event to monitor for external interruption (Ctrl-C)

    Returns:
        The flow_console instance
    """
    flow_console = ExperimentFlowConsole(disable_printing, external_stop_event)
    flowconsolemanager.add_handler(experiment_run_ulid, flow_console)
    flow_console.start()
    return flow_console


def __start_event_listeners(experiment_run_ulid: str):
    """
    Start stage event coordinator and event listeners.

    Args:
        experiment_run_ulid: The experiment run ULID

    Returns:
        Tuple of (cli_thread, db_thread)
    """
    from adare.backend.events.listener import event_listener_cli
    from adare.backend.events.coordinator import start_stage_coordinator

    # Start the stage event coordinator first
    start_stage_coordinator()
    log.info("Stage event coordinator started")

    # Note: In diff mode, we skip DB listener since there's no database persistence
    # Only start CLI listener for console output
    cli_ready_event = threading.Event()

    def cli_wrapper():
        cli_ready_event.set()
        event_listener_cli(experiment_run_ulid)

    cli_thread = threading.Thread(target=cli_wrapper, daemon=True)
    cli_thread.start()

    # Wait for listener to be ready (with timeout to prevent hangs)
    if not cli_ready_event.wait(timeout=10.0):
        raise RuntimeError("CLI event listener failed to start within 10 seconds")
    log.info("Event listener ready")

    return cli_thread


async def experiment_diff_run(
    project_path: Path,
    experiment_name: str,
    environment_name: str
) -> DiffModeResult:
    """
    Execute experiment in diff mode (visual-only, no database, QEMU host mode).

    Args:
        project_path: Path to project directory
        experiment_name: Name of experiment
        environment_name: Name of environment (must be QEMU-based)

    Returns:
        DiffModeResult with execution summary
    """
    start_time = time.time()
    action_results = []  # Track all action results
    skipped_count = 0
    action_failed = False  # Track if any action failed
    flow_console = None  # Initialize to None for cleanup
    diff_run_dir = None  # Initialize to None for result

    try:
        log.info(f"Starting diff mode: {experiment_name} on {environment_name}")

        # 1. Get environment file and validate QEMU
        environment_file = environment_database.get_environment_path_by_project_and_name(
            project_path, environment_name
        )

        if not environment_file:
            raise LoggedException(
                log,
                f"Environment not found: {environment_name}",
                ValueError
            )

        environment_metadata = parse_environment_file(environment_file)

        if environment_metadata.hypervisor.lower() != 'qemu':
            raise LoggedException(
                log,
                f"Diff mode requires QEMU hypervisor. "
                f"Environment '{environment_name}' uses {environment_metadata.hypervisor}. "
                f"Please use a QEMU-based environment.",
                ValueError
            )

        log.info(f"Environment validated: QEMU, platform={environment_metadata.os.platform}")

        # 2. Load playbook from YAML
        project_directory = ProjectDirectory(project_path)
        experiment_directory = ExperimentDirectory(project_directory.path, experiment_name)
        playbook_path = experiment_directory.path / "playbook.yml"

        if not playbook_path.exists():
            raise LoggedException(
                log,
                f"Playbook not found: {playbook_path}",
                ValueError
            )

        playbook = parse_playbook(playbook_path)
        log.info(f"Loaded playbook with {len(playbook.actions)} actions")

        # 3. Filter to visual actions only
        original_action_count = len(playbook.actions)
        playbook = filter_playbook_actions(playbook)
        filtered_action_count = len(playbook.actions)
        skipped_count = original_action_count - filtered_action_count

        if filtered_action_count == 0:
            raise LoggedException(
                log,
                f"No visual actions found in playbook. "
                f"Diff mode requires at least one visual action.",
                ValueError
            )

        log.info(f"Filtered to {filtered_action_count} visual actions ({skipped_count} skipped)")

        # 4. Create minimal ExperimentRunCtx for diff mode
        config = ExperimentConfig(
            project_path=project_path,
            experiment_name=experiment_name,
            environment_name=environment_name,
            test_mode=True,  # Treat diff mode like test mode
            gui_mode_override='host',  # Force HOST mode
            enable_diff=True  # Enable host-side filesystem diff
        )

        ctx = ExperimentRunCtx(config)

        # Initialize context fields manually (skip database)
        ctx.experiment_run_ulid = str(ulid.ULID())  # Fake ULID for diff mode
        ctx.timestamp_start = datetime.now(timezone.utc)
        ctx.adarevm = ADAREVM_DIR
        ctx.adarelib = ADARELIB_DIR
        ctx.project_directory = project_directory
        ctx.experiment_directory = experiment_directory
        ctx.environment_file = environment_file
        ctx.environment_ulid = experiment_database.get_environment_ulid(project_path, environment_name)
        ctx.guest_platform = environment_metadata.os.platform
        ctx.hypervisor_type = 'qemu'
        ctx.playbook = playbook
        ctx.test_mode = True

        # Create diff run directory
        log.info("Creating diff run directory structure")
        diff_run_dir = DiffRunDirectory(project_directory, experiment_name)
        diff_run_dir.create()
        ctx.experiment_run_directory = diff_run_dir
        log.info(f"Diff run directory created at: {diff_run_dir.path}")

        # Set up logging to diff directory
        from adare.backend.experiment.run import _ensure_and_copy_adare_log_to_run_directory
        _ensure_and_copy_adare_log_to_run_directory(diff_run_dir)

        # Set up signal handlers for Ctrl-C
        def handle_interrupt():
            log.info("Interrupt detected, stopping diff mode...")
            ctx.user_interrupt_event.set()
            ctx.stop_event.set()

        loop = asyncio.get_running_loop()
        loop.add_signal_handler(signal.SIGINT, handle_interrupt)

        # Create and start flow console BEFORE event listeners
        flow_console = __create_and_start_flow_console(
            ctx.experiment_run_ulid,
            disable_printing=False,
            external_stop_event=ctx.user_interrupt_event
        )
        # Start event listeners AFTER flow console
        cli_thread = __start_event_listeners(ctx.experiment_run_ulid)

        try:
            # 5. Start MCP server for target resolution
            log.info("Starting MCP server")
            ctx.mcp_server = MCPServerManager(log_file=diff_run_dir.mcp_gui_log_file)
            await ctx.mcp_server.start()

            # 6. VM lifecycle (no agent)
            log.info("Preparing VM")
            vm_manager = VMLifecycleManager(hypervisor_type='qemu')
            await vm_manager.create_and_prepare_vm(ctx)

            log.info("Starting VM in GUI mode")
            await vm_manager.start_vm(ctx)

            try:
                # 7. Execute visual actions (HOST mode)
                log.info(f"Executing {filtered_action_count} visual actions")

                # Create target resolver and condition checker
                target_resolver = MCPTargetResolver(
                    experiment_dir=ctx.experiment_directory.path,
                    mcp_gui_url=ctx.mcp_server.server_url,
                    experiment_run_ulid=ctx.experiment_run_ulid
                )
                condition_checker = MCPConditionChecker(
                    target_resolver=target_resolver
                )

                # Create variable registry using automatic variables system (same as normal run)
                vm_user = environment_metadata.credentials.user if (
                    hasattr(environment_metadata, 'credentials') and environment_metadata.credentials
                ) else 'guest'

                # Get automatic variables (vm.*, adare_*, etc.)
                automatic_vars = AutomaticVariables.get_automatic_variables(
                    ctx.guest_platform,
                    vm_user
                )

                # Merge with playbook variables if they exist (user variables take precedence)
                user_vars = playbook.variables if hasattr(playbook, 'variables') else None
                variable_registry = AutomaticVariables.merge_with_user_variables(
                    automatic_vars,
                    user_vars
                )

                # Create execution context with playbook and variables
                execution_context = {'playbook': playbook}
                if variable_registry:
                    # Convert VariableRegistry to execution context format
                    var_dict = variable_registry.to_execution_context(for_tests=False)
                    execution_context.update(var_dict)
                    log.info(f"Added {len(var_dict)} variables to execution context")

                # Create variable resolver
                variable_resolver = VariableResolver(variable_registry)

                # Create event manager for action event emission (no database persistence)
                event_manager = EventManager(
                    experiment_run_id=ctx.experiment_run_ulid,
                    playbook_items_map={}  # Empty - no database IDs in diff mode
                )

                # Create action executor
                executor = ActionExecutor(
                    websocket_client=None,  # No agent in diff mode
                    target_resolver=target_resolver,
                    condition_checker=condition_checker,
                    experiment_run_id=None,
                    playbook=playbook,
                    execution_context=execution_context,
                    debug_screenshots=True,  # Enable screenshots in diff mode
                    screenshots_dir=diff_run_dir.screenshots_directory,
                    vm=ctx.vm
                )

                # Execute actions with event emission for visual display
                for action_index, action in enumerate(playbook.actions):
                    if ctx.stop_event.is_set():
                        log.info("Stop event detected")
                        break

                    # Generate unique action ID for event tracking
                    action_id = str(ulid_module.ULID())

                    # Resolve variables in action
                    resolved_action = variable_resolver.resolve_action_variables(action, execution_context)

                    # Create and emit start event
                    start_event = event_manager.create_action_start_event(
                        action=resolved_action,
                        action_index=action_index,
                        action_id=action_id,
                        parent_event_id=None
                    )
                    emit_action(ctx.experiment_run_ulid, start_event, action_id)

                    # Execute action
                    log.info(f"Executing: {type(resolved_action).__name__}")
                    result = await executor.execute_action(resolved_action)

                    # Create and emit complete event
                    complete_event = event_manager.create_action_complete_event(
                        action=resolved_action,
                        action_index=action_index,
                        action_id=action_id,
                        result=result,
                        parent_event_id=None
                    )
                    emit_action(ctx.experiment_run_ulid, complete_event, action_id)

                    # Track all results
                    action_results.append(result)

                    if result.success:
                        log.info(f"Success: {result.message}")
                    else:
                        log.error(f"Action {action_index+1} failed: {result.message}")
                        log.info("Stopping execution due to action failure")
                        action_failed = True
                        break  # Stop immediately - avoid unnecessary diff computation

            finally:
                # 8. Cleanup
                log.info("Stopping VM")
                await vm_manager.stop_vm(ctx)

                # Perform host-side filesystem diff analysis
                if not ctx.user_interrupt_event.is_set() and not action_failed:
                    log.info("Analyzing filesystem changes using virt-diff")
                    await vm_manager.perform_host_diff(ctx, post_interrupt=False)
                    # Diff results are displayed via stage sub_msg (set in perform_host_diff)
                    # No need for separate flow console logging here
                else:
                    if ctx.user_interrupt_event.is_set():
                        log.info("Skipping filesystem diff due to user interrupt")
                    elif action_failed:
                        log.info("Skipping filesystem diff due to action failure")

                log.info("Cleaning up resources")
                await vm_manager.cleanup_vm(ctx)

        finally:
            try:
                if ctx.mcp_server:
                    await ctx.mcp_server.stop()

                loop.remove_signal_handler(signal.SIGINT)

                # Give time for all events to be processed before stopping
                await asyncio.sleep(2)

                # Stop the stage event coordinator
                from adare.backend.events.coordinator import stop_stage_coordinator
                stop_stage_coordinator()
                log.info("Stage event coordinator stopped")

                # Log experiment summary before stopping console (if console was started)
                if flow_console:
                    total_duration = None
                    if ctx.timestamp_start:
                        total_duration = (datetime.now(timezone.utc) - ctx.timestamp_start).total_seconds()

                    # Check if this was an interruption
                    was_interrupted = ctx.user_interrupt_event.is_set()

                    # Calculate statistics from action results
                    successful_actions = sum(1 for r in action_results if r.success)
                    failed_actions = len(action_results) - successful_actions
                    total_actions = len(action_results)

                    # Show summary
                    flow_console.log_experiment_summary(
                        ulid=ctx.experiment_run_ulid,
                        success=not was_interrupted and failed_actions == 0 and total_actions > 0,
                        total_actions=total_actions,
                        successful_actions=successful_actions,
                        failed_actions=failed_actions,
                        total_tests=0,
                        successful_tests=0,
                        failed_tests=0,
                        duration=total_duration,
                        was_interrupted=was_interrupted
                    )

                    # Display diff results location
                    flow_console.log_success(
                        identifier='DIFF_RESULTS_LOCATION',
                        message=f"📊 Diff results available in: {diff_run_dir.diff_directory}",
                        level=0
                    )

                    # Give the flow console time to display the summary before stopping
                    await asyncio.sleep(3)

                    flow_console.stop()
            except NameError:
                # Handle case where variables are not yet defined (early exception)
                pass
            except Exception as cleanup_error:
                log.error(f"Error during cleanup: {cleanup_error}", exc_info=True)
                # Ensure coordinator and console are stopped even if cleanup fails
                try:
                    from adare.backend.events.coordinator import stop_stage_coordinator
                    stop_stage_coordinator()
                except:
                    pass
                # Ensure flow console is stopped
                if flow_console:
                    try:
                        flow_console.stop()
                    except:
                        pass

        execution_time = time.time() - start_time

        # Calculate final statistics
        successful_actions = sum(1 for r in action_results if r.success)
        failed_actions = len(action_results) - successful_actions

        return DiffModeResult(
            success=failed_actions == 0,
            actions_executed=len(action_results),
            successful_actions=successful_actions,
            failed_actions=failed_actions,
            actions_skipped=skipped_count,
            execution_time=execution_time,
            diff_run_directory=diff_run_dir.path if diff_run_dir else None
        )

    except Exception as e:
        execution_time = time.time() - start_time
        log.error(f"Diff mode failed: {e}", exc_info=True)

        # Calculate statistics even on exception
        successful_actions = sum(1 for r in action_results if r.success)
        failed_actions = len(action_results) - successful_actions

        return DiffModeResult(
            success=False,
            actions_executed=len(action_results),
            successful_actions=successful_actions,
            failed_actions=failed_actions,
            actions_skipped=skipped_count,
            execution_time=execution_time,
            error=str(e),
            diff_run_directory=diff_run_dir.path if diff_run_dir else None
        )
