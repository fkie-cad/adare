import asyncio
import logging
import threading
from datetime import UTC, datetime
from pathlib import Path

import adare.backend.experiment.database as experiment_database
from adare.backend.experiment.event_listeners import (
    create_and_start_flow_console,
    start_event_listeners,
)
from adare.backend.experiment.run_setup import (  # noqa: F401
    _ensure_and_copy_adare_log_to_run_directory,
    _resolve_and_store_test_execution_mode,
    _setup_guest_to_host_test_executor,
    step_collect_system_info,
    step_connect_websocket,
    step_execute_experiment,
    step_execute_installations,
    step_execute_installations_via_qga,
    step_finalize,
    step_initialize,
    step_install_and_run_websocket_server,
    step_prepare_run_environment,
    step_remove_fake_experiment_run,
    step_setup_experiment_environment,
    step_shutdown_mcp_server,
    step_shutdown_ws,
    step_start_mcp_server,
    step_validate_integrity,
)
from adare.backend.experiment.runctx import ExperimentConfig, ExperimentRunCtx
from adare.backend.experiment.stagectxmanager import StageCtxManager
from adare.backend.experiment.step_runner import ExperimentStepRunner
from adare.backend.experiment.vm_lifecycle_manager import VMLifecycleManager
from adare.exceptions import LoggedException
from adare.types.stages import (
    CleanupShutdownStage,
    ExperimentExecutionStage,
    ExperimentPreparationStage,
    SoftwareInstallationStage,
    VirtualMachineSetupStage,
)
from adarelib.constants import StatusEnum

log = logging.getLogger(__name__)

# Disable verbose MCP client logging to prevent base64 image flooding the log
logging.getLogger('mcp.client.streamable_http').setLevel(logging.WARNING)
logging.getLogger('httpx').setLevel(logging.WARNING)
logging.getLogger('httpcore').setLevel(logging.WARNING)


def _resolve_experiment_verdict(experiment_run, test_mode: bool, execution_success: bool) -> tuple[bool, dict]:
    """Resolve the success verdict for an experiment run.

    A "smoke run" (verify-vm and similar) declares no abstract tests and is
    invoked with test=False. For these, the playbook completing without an
    unhandled error is the verdict — applying a test-suite verdict here can
    falsely report failure when there were never tests to satisfy.

    For full test runs (test=True or any experiment with abstract tests),
    keep the strict result_status == SUCCESS rule so missing or failed test
    coverage is never silently green-lit.

    Returns (success, diagnostics) where diagnostics carries the inputs to
    the decision so they can be logged at a single grep-friendly site.
    """
    abstract_tests_count = 0
    test_events_count = 0
    result_status = None
    experiment_loaded = False

    if experiment_run is not None:
        try:
            if experiment_run.experiment is not None:
                experiment_loaded = True
                abstract_tests_count = len(experiment_run.experiment.abstract_tests or [])
            test_events_count = len(experiment_run.tests or [])
            result_status = experiment_run.result_status
        except Exception:
            # Session-boundary or lazy-load failure on a relationship — leave
            # counts at zero and result_status as None so the smoke gate can
            # still trigger when test_mode is False.
            pass

    is_smoke_run = (not test_mode) and abstract_tests_count == 0

    if is_smoke_run:
        success = bool(execution_success)
    else:
        success = result_status == StatusEnum.SUCCESS

    diagnostics = {
        "verdict": "SUCCESS" if success else "FAILED",
        "smoke_mode": is_smoke_run,
        "test_mode": test_mode,
        "run_found": experiment_run is not None,
        "experiment_loaded": experiment_loaded,
        "abstract_tests": abstract_tests_count,
        "test_events": test_events_count,
        "result_status": str(result_status) if result_status is not None else None,
        "execution_success": bool(execution_success),
    }
    return success, diagnostics


async def experiment_run(project_path: Path, experiment_name: str, environment_name: str, disable_printing: bool = False, test: bool = True, debug_screenshots: bool = False, preserve_snapshot: bool = False, runlog: bool = True, vm_memory: int = None, vm_cpus: int = None, gui_mode: str = None, test_exec_mode: str = None, diff: bool = None, diff_mode: str = 'auto', file_log_level: int = logging.INFO, run_ulid: str | None = None):
    import signal

    log.info(f"Starting experiment run {experiment_name} in project {project_path}")

    # Create the experiment context and initialize it.
    config = ExperimentConfig(
        project_path=project_path,
        experiment_name=experiment_name,
        environment_name=environment_name,
        preserve_snapshot=preserve_snapshot,
        runlog=runlog,
        test_mode=test,
        file_log_level=file_log_level
    )

    # Determine guest platform early to set platform-specific defaults
    # We need to get the environment info to determine the platform
    try:
        environment_file = None
        if environment_name:
            from adare.backend.environment import database as environment_database
            environment_file = environment_database.get_environment_path_by_project_and_name(
                project_path, environment_name
            )

        if environment_file:
            from adare.types.environment import parse_environment_file
            environment_metadata = parse_environment_file(environment_file)
            guest_platform = environment_metadata.os.platform

            # Set platform-specific defaults if not overridden by CLI
            if vm_memory is None:
                if 'windows' in guest_platform.lower():
                    config.vm_memory = 8192  # 8GB for Windows
                    log.info("Using Windows default VM memory: 8192MB")
                else:
                    config.vm_memory = 4096  # 4GB for Linux
                    log.info("Using Linux default VM memory: 4096MB")
            else:
                config.vm_memory = vm_memory
                log.info(f"Using custom VM memory: {vm_memory}MB")
        else:
            # Fallback: apply CLI override or keep default
            if vm_memory is not None:
                config.vm_memory = vm_memory
                log.info(f"Using custom VM memory: {vm_memory}MB")
    except (FileNotFoundError, OSError) as e:
        # Only catch file system related errors, not environment validation errors
        log.warning(f"Could not determine guest platform for memory defaults: {e}")
        # Fallback: apply CLI override or keep default
        if vm_memory is not None:
            config.vm_memory = vm_memory
            log.info(f"Using custom VM memory: {vm_memory}MB")

    # Override VM CPU settings if provided via CLI
    if vm_cpus is not None:
        config.vm_cpus = vm_cpus
        log.info(f"Using custom VM CPUs: {vm_cpus}")

    # Override GUI mode if provided via CLI
    if gui_mode is not None:
        config.gui_mode_override = gui_mode
        log.info(f"Using custom GUI mode: {gui_mode}")

    # Override test execution mode if provided via CLI
    if test_exec_mode is not None:
        config.test_mode_override = test_exec_mode
        log.info(f"Using custom test execution mode: {test_exec_mode}")

    # Set filesystem diff parameters
    if diff is not None:
        config.enable_diff = diff
        log.info(f"Filesystem diff CLI override: {'enabled' if diff else 'disabled'}")
    if diff_mode is not None:
        config.diff_mode = diff_mode
        log.info(f"Filesystem diff mode: {diff_mode}")

    experiment_run_context = ExperimentRunCtx(config)
    # Respect the --debug-screenshots CLI flag (default: False unless flag is provided)
    experiment_run_context.debug_screenshots = debug_screenshots
    experiment_run_context.test_mode = test  # Store test mode flag (default: True for test mode)
    if test:
        step_initialize(experiment_run_context, fake=True, run_ulid=run_ulid)  # Test mode: creates fake run
    else:
        step_initialize(experiment_run_context, run_ulid=run_ulid)  # Production mode: creates real run

    # Create an asyncio Event to signal shutdown.
    stop_event = asyncio.Event()

    # Create a separate threading Event specifically for user interruption (Ctrl-C)
    user_interrupt_event = threading.Event()

    # Add the user interrupt event to the context so step functions can use it
    experiment_run_context.user_interrupt_event = user_interrupt_event

    def handle_sigint():
        log.info("Ctrl-C detected. Stopping experiment run...")
        user_interrupt_event.set()  # Signal user interruption
        experiment_run_context.stop_event.set()  # Signal the context's stop event.
        stop_event.set()  # Signal the asyncio stop event.
        log.info('hanlde: send stop events')

    # Register the signal handler for SIGINT.
    loop = asyncio.get_running_loop()
    loop.add_signal_handler(signal.SIGINT, handle_sigint)

    # Create and start the flow console.
    flow_console = create_and_start_flow_console(experiment_run_context.experiment_run_ulid, disable_printing, user_interrupt_event)

    # Start experiment timer header row
    if not disable_printing:
        flow_console.start_experiment_timer(experiment_name)

    # Add small delay to let Rich console settle before starting stages
    await asyncio.sleep(0.1)
    log.debug("Flow console started, proceeding with event listeners")

    # Start event listeners BEFORE any stages begin to ensure all events are captured
    start_event_listeners(experiment_run_context.experiment_run_ulid)

    # Create step runner to handle execution logic
    step_runner = ExperimentStepRunner(stop_event, user_interrupt_event)

    # --- Execution Flow ---
    vm_manager = None

    try:

        # Experiment Preparation Phase
        if not stop_event.is_set():
            with StageCtxManager(ExperimentPreparationStage(), experiment_run_context.experiment_run_ulid, event=user_interrupt_event):
                initial_steps = [
                    step_setup_experiment_environment,
                    step_validate_integrity,
                    step_prepare_run_environment,
                ]
                await step_runner.run_steps_sequence(initial_steps, experiment_run_context)

                # Start MCP server early (independent of VM)
                await step_runner.run_async_step(step_start_mcp_server, experiment_run_context)

        # Create VM lifecycle manager with hypervisor from environment
        # (Must be created after step_setup_experiment_environment sets hypervisor_type)
        hypervisor = experiment_run_context.hypervisor_type or 'virtualbox'
        vm_manager = VMLifecycleManager(hypervisor_type=hypervisor)
        log.debug(f'Using hypervisor: {hypervisor}')

        # Virtual Machine Setup Phase
        if not stop_event.is_set():
            with StageCtxManager(VirtualMachineSetupStage(), experiment_run_context.experiment_run_ulid, event=user_interrupt_event):
                await step_runner.run_async_step(vm_manager.create_and_prepare_vm, experiment_run_context)
                await step_runner.run_async_step(vm_manager.setup_file_transfer, experiment_run_context)
                await step_runner.run_async_step(vm_manager.setup_networking, experiment_run_context)
                await step_runner.run_async_step(vm_manager.start_vm, experiment_run_context)

        # Resolve test execution mode after VM is created
        if not stop_event.is_set():
            _resolve_and_store_test_execution_mode(experiment_run_context)

        # Software Installation Phase
        if not stop_event.is_set():
            is_host_test_mode = experiment_run_context.test_execution_mode == 'host'
            is_host_gui_mode = (experiment_run_context.config.gui_mode_override == 'host' or
                               (experiment_run_context.config.gui_mode_override is None and
                                experiment_run_context.hypervisor_type == 'qemu'))

            # In full host mode (both GUI and tests via host), skip agent entirely
            needs_agent = not (is_host_test_mode and is_host_gui_mode)

            with StageCtxManager(SoftwareInstallationStage(), experiment_run_context.experiment_run_ulid, event=user_interrupt_event):
                if needs_agent:
                    await step_runner.run_async_step(step_install_and_run_websocket_server, experiment_run_context)
                    await step_runner.run_async_step(step_connect_websocket, experiment_run_context)
                    await step_runner.run_async_step(step_execute_installations, experiment_run_context)
                else:
                    log.info("Host mode: skipping adarevm agent installation and WebSocket connection")
                    await step_runner.run_async_step(step_execute_installations_via_qga, experiment_run_context)

        # Experiment Execution Phase
        if not stop_event.is_set():
            with StageCtxManager(ExperimentExecutionStage(), experiment_run_context.experiment_run_ulid, event=user_interrupt_event):
                await step_runner.run_async_step(step_execute_experiment, experiment_run_context)

                # Collect system information after experiment execution (if enabled in playbook settings)
                await step_runner.run_async_step(step_collect_system_info, experiment_run_context)

        # Success: Mark experiment as finished if no exceptions occurred
        if not stop_event.is_set():
            log.info("Experiment completed successfully, marking as FINISHED")
            experiment_database.update_experiment_run_status(
                experiment_run_context.project_directory.path,
                experiment_run_context.experiment_run_ulid,
                StatusEnum.FINISHED,
            )
            # Update experiment timer to show completion
            if not disable_printing:
                flow_console.finish_experiment_timer(success=True)

    except LoggedException as e:
        # Handle structured exceptions - let them bubble up to exec_with_error_printing for consistent UX
        experiment_run_context.stop_event.set()
        log.info("LoggedException: send stop events")
        from adare.exceptions import LoggedErrorException
        status = StatusEnum.FAILED if isinstance(e, LoggedErrorException) else StatusEnum.INTERRUPTED
        experiment_database.update_experiment_run_status(
            experiment_run_context.project_directory.path,
            experiment_run_context.experiment_run_ulid,
            status,
        )
        # Update experiment timer to show failure
        if not disable_printing:
            flow_console.finish_experiment_timer(success=False)
        # Re-raise to be handled by exec_with_error_printing
        raise
    except Exception as e:
        # Intentionally broad: top-level experiment runner must catch any unexpected
        # exception to update DB status and trigger cleanup before re-raising.
        log.error(f"An unexpected error occurred: {e}", exc_info=True)
        experiment_run_context.stop_event.set()
        log.info("exception: send stop events")
        experiment_database.update_experiment_run_status(
            experiment_run_context.project_directory.path,
            experiment_run_context.experiment_run_ulid,
            StatusEnum.INTERRUPTED,
        )
        # Update experiment timer to show failure
        if not disable_printing:
            flow_console.finish_experiment_timer(success=False)
        # Re-raise unexpected exceptions too so they get proper exit codes
        raise
    finally:
        # Ensure shutdown procedures are executed.
        if not stop_event.is_set():
            experiment_run_context.stop_event.set()
            log.info("finally: send stop events")

        # Update database status if user interrupted
        if user_interrupt_event.is_set():
            log.info("User interrupt detected - updating experiment run status to INTERRUPTED")
            experiment_database.update_experiment_run_status(
                experiment_run_context.project_directory.path,
                experiment_run_context.experiment_run_ulid,
                StatusEnum.INTERRUPTED,
            )
            # Update experiment timer to show interruption
            if not disable_printing:
                flow_console.finish_experiment_timer(success=False)

        try:
            log.info("Starting cleanup and shutdown...")
            # Wrap cleanup in proper stage context (don't pass interrupt event - we want to show actual cleanup work)
            with StageCtxManager(CleanupShutdownStage(), experiment_run_context.experiment_run_ulid, event=None):
                await step_runner.run_cleanup_step(step_finalize, experiment_run_context, post_interrupt=True)
                await step_runner.run_cleanup_step(step_shutdown_mcp_server, experiment_run_context, post_interrupt=True)
                await step_runner.run_cleanup_step(step_shutdown_ws, experiment_run_context, post_interrupt=True)

                if vm_manager:
                    # Determine if force shutdown is needed (Windows on QEMU)
                    force_shutdown = False
                    if (experiment_run_context.hypervisor_type == 'qemu' and
                        experiment_run_context.guest_platform == 'windows'):
                        force_shutdown = True
                        log.info("Forcing shutdown for Windows VM on QEMU to prevent updates")

                    # Retrieve artifacts BEFORE stopping VM (critical for QGA/VirtioFS which need a running VM)
                    # The lifecycle strategy handles stop internally in the correct order per transfer mode
                    await step_runner.run_cleanup_step(vm_manager.retrieve_artifacts, experiment_run_context, post_interrupt=True, force_stop=force_shutdown)
                    # Safety net: stop VM if retrieve_artifacts didn't already (idempotent)
                    await step_runner.run_cleanup_step(vm_manager.stop_vm, experiment_run_context, post_interrupt=True, force=force_shutdown)
                    # Perform host-side diff AFTER VM stopped, BEFORE overlay cleanup
                    await step_runner.run_cleanup_step(vm_manager.perform_host_diff, experiment_run_context, post_interrupt=True)
                    await step_runner.run_cleanup_step(vm_manager.cleanup_vm, experiment_run_context, post_interrupt=True)
            # Give time for all events to be processed before stopping
            await asyncio.sleep(2)

            # Stop the stage event coordinator
            from adare.backend.events.coordinator import stop_stage_coordinator
            stop_stage_coordinator()
            log.info("Stage event coordinator stopped")

            # Log enhanced experiment summary before stopping console
            # Get execution results and calculate overall statistics
            execution_result = getattr(experiment_run_context, 'execution_result', None)

            # Calculate total duration (shared by both branches)
            total_duration = None
            if hasattr(experiment_run_context, 'timestamp_start'):
                total_duration = (datetime.now(UTC) - experiment_run_context.timestamp_start).total_seconds()

            if execution_result:
                flow_console.log_experiment_summary(
                    ulid=experiment_run_context.experiment_run_ulid,
                    success=execution_result.success,
                    total_actions=execution_result.total_actions,
                    successful_actions=execution_result.successful_actions,
                    failed_actions=execution_result.failed_actions,
                    total_tests=execution_result.total_tests,
                    successful_tests=execution_result.successful_tests,
                    failed_tests=execution_result.failed_tests,
                    duration=total_duration
                )
            else:
                flow_console.log_experiment_summary(
                    ulid=experiment_run_context.experiment_run_ulid,
                    success=False,
                    total_actions=0, successful_actions=0, failed_actions=0,
                    total_tests=0, successful_tests=0, failed_tests=0,
                    duration=total_duration,
                    was_interrupted=user_interrupt_event.is_set()
                )

            if test:
                # Test mode: fake runs are kept until manually cleaned with 'adare experiment clean <name>'
                log.info(f"Test mode run {experiment_run_context.experiment_run_ulid} completed and preserved for analysis")
            # Give the flow console time to display the summary before stopping
            await asyncio.sleep(3)

            # Print debug flow messages before stopping console
            # flow_console.print_debug_flow_messages()
            flow_console.stop()
            flow_console.print_final_output()  # Flush all messages to terminal for review
        except Exception as e:
            # Intentionally broad: shutdown must not crash — any failure here
            # is logged and swallowed so the experiment still exits cleanly.
            log.error(f"Error during shutdown: {e}", exc_info=True)
            # Ensure coordinator is stopped even if cleanup fails
            try:
                from adare.backend.events.coordinator import stop_stage_coordinator
                stop_stage_coordinator()
            except Exception as cleanup_error:
                # Intentionally broad: last-resort cleanup must not raise.
                log.error(f"Error stopping stage coordinator during error cleanup: {cleanup_error}", exc_info=True)

    # Resolve the success verdict. For smoke/verify runs (test=False AND no
    # abstract tests on the experiment) trust the playbook completion signal.
    # For full test runs keep the strict result_status == SUCCESS rule so
    # missing/failed test coverage is never silently green-lit.
    execution_result = getattr(experiment_run_context, 'execution_result', None)
    execution_success = bool(getattr(execution_result, 'success', False))

    experiment_success = False
    diagnostics: dict = {
        "verdict": "FAILED",
        "smoke_mode": not test,
        "test_mode": test,
        "run_found": False,
        "experiment_loaded": False,
        "abstract_tests": 0,
        "test_events": 0,
        "result_status": None,
        "execution_success": execution_success,
        "lookup_error": None,
    }
    try:
        from adare.database.api.experiment import ExperimentApi
        from adare.database.models.project_models import ExperimentRun
        with ExperimentApi(experiment_run_context.project_directory.path) as api:
            experiment_run_row = api._session.query(ExperimentRun).filter(ExperimentRun.id == experiment_run_context.experiment_run_ulid).first()
            experiment_success, diagnostics = _resolve_experiment_verdict(
                experiment_run_row, test_mode=test, execution_success=execution_success
            )
    except (ValueError, KeyError, OSError) as e:
        log.error(f"Error checking experiment run status: {e}")
        diagnostics["lookup_error"] = repr(e)
        # Fallback: smoke runs can still pass on the playbook completion signal alone.
        if not test:
            experiment_success = execution_success
            diagnostics["verdict"] = "SUCCESS" if experiment_success else "FAILED"
            diagnostics["smoke_mode"] = True

    log.info(
        "experiment verdict resolved: "
        f"verdict={diagnostics['verdict']} smoke_mode={diagnostics['smoke_mode']} "
        f"test_mode={diagnostics['test_mode']} run_found={diagnostics['run_found']} "
        f"experiment_loaded={diagnostics['experiment_loaded']} "
        f"abstract_tests={diagnostics['abstract_tests']} test_events={diagnostics['test_events']} "
        f"result_status={diagnostics['result_status']} "
        f"execution_success={diagnostics['execution_success']} "
        f"lookup_error={diagnostics.get('lookup_error')} "
        f"run_ulid={experiment_run_context.experiment_run_ulid}"
    )

    # Generate forensic report after experiment completion
    try:
        # Check if forensic logging is enabled (default: True)
        forensic_enabled = True
        if (hasattr(experiment_run_context, 'playbook') and
            experiment_run_context.playbook and
            hasattr(experiment_run_context.playbook, 'settings') and
            experiment_run_context.playbook.settings):
            forensic_enabled = experiment_run_context.playbook.settings.forensic_logging

        if forensic_enabled and hasattr(experiment_run_context, 'experiment_run_directory'):
            from adare.backend.experiment.forensic_reporter import generate_forensic_report_for_run
            forensic_log_path = experiment_run_context.experiment_run_directory.forensic_log_file

            log.info(f"Generating forensic report for run {experiment_run_context.experiment_run_ulid}")
            forensic_success = generate_forensic_report_for_run(
                experiment_run_context.experiment_run_ulid,
                forensic_log_path,
                experiment_run_context.project_directory.path
            )

            if forensic_success:
                log.info(f"Forensic report generated: {forensic_log_path}")
            else:
                log.warning(f"Failed to generate forensic report for run {experiment_run_context.experiment_run_ulid}")
    except (OSError, ValueError, KeyError) as e:
        log.error(f"Error generating forensic report: {e}", exc_info=True)

    # Return both interruption status and actual success status
    return user_interrupt_event.is_set(), experiment_success

def experiment_test(project_path: Path, experiment_name: str, environment_name: str):
    """Test an experiment in development mode - creates fake run that gets cleaned up.

    This function provides a development-friendly way to test experiments without
    creating persistent runs or requiring integrity checks. Perfect for iterative
    development and testing of experiment playbooks.

    Args:
        project_path: Path to the project directory
        experiment_name: Name of the experiment to test
        environment_name: Name of the environment to use
    """

    log.info(f'Starting experiment test: {experiment_name} in environment {environment_name}')

    # Run experiment in test mode (creates fake run that gets cleaned up)
    asyncio.run(experiment_run(
        project_path=project_path,
        experiment_name=experiment_name,
        environment_name=environment_name,
        disable_printing=False,  # Show output for development feedback
        test=True,  # This creates fake runs that are cleaned up automatically
        debug_screenshots=True,  # Enable debug screenshots for development
        preserve_snapshot=False,  # Don't preserve snapshots in test mode
        runlog=True   # Save logs for test runs to aid debugging
    ))
