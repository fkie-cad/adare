# external imports
from pathlib import Path
from datetime import datetime, timezone
import threading
import asyncio

# internal imports
from adare.backend.experiment.directory import ExperimentDirectory, ExperimentRunDirectory
import adare.backend.experiment.database as experiment_database
import adare.backend.environment.database as environment_database
from adare.exceptions import LoggedException
from adare.backend.project.directory import ProjectDirectory
from adare.backend.experiment.print import flowconsolemanager
from adare.backend.experiment.step_runner import ExperimentStepRunner
from adare.backend.experiment.vm_lifecycle_manager import VMLifecycleManager
from adare.types.stages import (
    # Top-level parent stages
    ExperimentPreparationStage, VirtualMachineSetupStage, SoftwareInstallationStage,
    ExperimentExecutionStage, CleanupShutdownStage,
    # Sub-stages
    SetupExperimentEnvironmentStage, ValidateIntegrityStage, PrepareRunEnvironmentStage, StartComputerVisionServerStage,
    InstallAdareVMStage, ConnectToVMStage, InstallationsStage,
    ExperimentRunStage, SystemInfoCollectionStage,
    FinalizeStage, ShutdownComputerVisionServerStage, ShutdownWebSocketStage,
)
from adare.backend.experiment.stagectxmanager import StageCtxManager
from adarelib.constants import StatusEnum
from adare.config.configdirectory import ADAREVM_DIR, ADARELIB_DIR
from adare.backend.experiment.runctx import ExperimentRunCtx, ExperimentConfig

# Extracted modules
from adare.backend.experiment.integrity_validator import IntegrityValidator
from adare.backend.experiment.agent_lifecycle import install_and_run_adare_vm
from adare.backend.experiment.event_listeners import (
    start_event_listeners,
    create_and_start_flow_console,
)

# configure logging
import logging
log = logging.getLogger(__name__)

# Disable verbose MCP client logging to prevent base64 image flooding the log
logging.getLogger('mcp.client.streamable_http').setLevel(logging.WARNING)
logging.getLogger('httpx').setLevel(logging.WARNING)
logging.getLogger('httpcore').setLevel(logging.WARNING)

def _ensure_and_copy_adare_log_to_run_directory(run_directory: ExperimentRunDirectory, copy_existing: bool = True):
    """Ensure a log file exists and copy it to the experiment run directory.

    If no log file is currently active (e.g., when --logfile is not specified),
    this function will create a temporary log file in the run directory and
    configure logging to use it, ensuring the experiment run has log output.

    Args:
        run_directory: The experiment run directory where the log should be copied
        copy_existing: Whether to copy the existing log file (default: True).
                      Set to False for dev mode/long-running processes to avoid copying history.
    """
    import shutil
    import logging
    from adare.logger.logger import get_current_logfile, FileHandlerFormatter

    current_logfile = get_current_logfile()
    target_path = run_directory.log_directory / 'adare.log'

    if current_logfile and copy_existing:
        # Copy existing log file
        try:
            shutil.copy2(current_logfile, target_path)
            log.info(f'Copied adare log to {target_path}')
        except Exception as e:
            log.warning(f'Failed to copy adare log to run directory: {e}')
    elif not copy_existing:
        log.info('Skipping copy of existing log file (requested)')
    else:
        log.info('No active log file found, creating new log file for experiment run')

    # Always configure logging to the run directory file to capture all future logs
    try:
        # Create the log file handler (append mode to preserve copied content)
        file_handler = logging.FileHandler(target_path, mode='a', encoding='utf-8')
        file_handler.setFormatter(FileHandlerFormatter())
        file_handler.setLevel(logging.DEBUG)

        # Add handler to root logger to capture all log messages
        root_logger = logging.getLogger()
        root_logger.addHandler(file_handler)

        # Ensure root logger level allows DEBUG messages to be captured
        if root_logger.level > logging.DEBUG:
            root_logger.setLevel(logging.DEBUG)

        log.info(f'Configured logging to {target_path}')
    except Exception as e:
        log.warning(f'Failed to configure logging to run directory: {e}')

def __cleanup_experiment_run(experiment_run_directory: ExperimentRunDirectory):
    if experiment_run_directory is not None:
        experiment_run_directory.clean()

def step_initialize(context: ExperimentRunCtx, fake: bool = False, run_ulid: str = None):
    # Initialize experiment run in database (using optional specific ULID if provided)
    context.experiment_run_ulid = experiment_database.initialize_experiment_run(
        context.config.project_path,
        fake,
        id=run_ulid
    )
    context.timestamp_start = datetime.now(timezone.utc)
    context.timestamp_before_vm_start = datetime.now(timezone.utc)
    context.adarevm = ADAREVM_DIR
    context.adarelib = ADARELIB_DIR
    log.info(f'initialized experiment run {context.experiment_run_ulid}')

def step_setup_experiment_environment(context: ExperimentRunCtx):
    """Consolidated step: Setup directories, validate playbook, and resolve environment."""
    with StageCtxManager(SetupExperimentEnvironmentStage(), context.experiment_run_ulid, event=context.user_interrupt_event):
        # Setup directories
        context.project_directory = ProjectDirectory(context.config.project_path)
        context.experiment_directory = ExperimentDirectory(context.config.project_path, context.config.experiment_name)
        context.experiment_directory.check_for_missing_files()
        log.info(f'checked experiment directory {context.experiment_directory.path}')

        # Set experiment and environment info early to prevent orphaned runs on interruption
        experiment_database.set_experiment_run_base_info(
            context.experiment_run_ulid,
            context.config.experiment_name,
            context.config.environment_name,
            context.config.project_path
        )
        log.info(f'set base experiment info for run {context.experiment_run_ulid}')

        # Set experiment start timestamp early to ensure it's persisted even if interrupted
        experiment_database.update_experiment_run_start(context.project_directory.path, context.experiment_run_ulid, context.timestamp_start)
        log.info(f'set experiment start timestamp for run {context.experiment_run_ulid}')

        # Validate playbook
        try:
            experiment_id = experiment_database.get_experiment_by_project_and_name(
                context.config.project_path,
                context.config.experiment_name
            )
            if not experiment_id:
                # Fallback to file-based parsing for new/untracked experiments
                log.info("Experiment not found in database, falling back to file-based parsing")
                from adare.types.playbook import parse_playbook
                playbook_path = context.experiment_directory.path / "playbook.yml"
                if not playbook_path.exists():
                    log.warning("No playbook.yml found - experiment cannot run GUI actions (experiment may be incomplete)")
                    return
                # Get VM OS and user for automatic variables
                context.playbook = parse_playbook(playbook_path)
                log.info(f"Playbook validation successful - {len(context.playbook.actions)} actions found")
                return

            # Load from database (pre-validated)
            from adare.database.api.playbook import PlaybookApi
            with PlaybookApi(context.project_directory.path) as playbook_api:
                try:
                    log.info(f"Loading pre-validated playbook from database for experiment {experiment_id}")
                    context.playbook = playbook_api.load_playbook_from_database(experiment_id)
                    log.info(f"Playbook loaded from database - {len(context.playbook.actions)} actions found")
                except ValueError as e:
                    # Fallback to file parsing if database doesn't have the content
                    log.warning(f"Database playbook load failed: {e}, falling back to file parsing")
                    from adare.types.playbook import parse_playbook
                    from adare.config import get_vm_credentials
                    playbook_path = context.experiment_directory.path / "playbook.yml"
                    if not playbook_path.exists():
                        log.warning("No playbook.yml found - experiment cannot run GUI actions (experiment may be incomplete)")
                        return
                    context.playbook = parse_playbook(playbook_path)
                    log.info(f"Playbook validation successful - {len(context.playbook.actions)} actions found")

        except Exception as e:
            raise LoggedException(log, f"Playbook loading failed: {str(e)}")

        # Verify integrity of testfunctions used in playbook
        # TODO: Re-enable this for production use - currently disabled for testing
        # Temporarily commented out to allow testfunction modifications during testing
        # if hasattr(context, 'playbook') and context.playbook:
        #     validator = IntegrityValidator(context.config.project_path)
        #     validator.verify_playbook_testfunctions(context.playbook)

        # Resolve environment
        if context.config.environment_name:
            context.environment_file = environment_database.get_environment_path_by_project_and_name(
                context.config.project_path, context.config.environment_name
            )
        else:
            context.environment_file = experiment_database.get_experiment_environment(
                context.config.project_path, context.config.environment_name, context.config.experiment_name
            )
            # update environment_name based on file stem
            context.config.environment_name = context.environment_file.stem
        context.environment_ulid = experiment_database.get_environment_ulid(context.config.project_path, context.config.environment_name)

        # For lazy loading, VM file might not be available yet - will be resolved during VM creation
        context.vm_file = environment_database.get_environment_vm_file(context.environment_ulid)
        context.guest_platform = environment_database.get_environment_os(context.environment_ulid)
        context.hypervisor_type = environment_database.get_environment_hypervisor(context.environment_ulid)

        # Fetch guest architecture from database (via VM osinfo)
        env_arch_data = environment_database.get_environment_by_ulid(
            context.environment_ulid, fields=['vm_architecture']
        )
        if env_arch_data and env_arch_data.get('vm_architecture'):
            context.guest_architecture = env_arch_data['vm_architecture']

        # If VM file is not available, get from environment metadata directly
        if not context.vm_file or not context.guest_platform or not context.guest_architecture:
            from adare.types.environment import parse_environment_file
            environment_metadata = parse_environment_file(context.environment_file)
            if not context.vm_file:
                context.vm_file = Path(environment_metadata.vm)
            if not context.guest_platform:
                context.guest_platform = environment_metadata.os.platform
            if not context.guest_architecture and hasattr(environment_metadata.os, 'architecture'):
                context.guest_architecture = environment_metadata.os.architecture

        log.info(f'found environment {context.config.environment_name} (hypervisor: {context.hypervisor_type})')

def step_validate_integrity(context: ExperimentRunCtx):
    """Consolidated step: Check experiment and project integrity."""
    with StageCtxManager(ValidateIntegrityStage(), context.experiment_run_ulid, event=context.user_interrupt_event) as stage_ctx:
        # Skip integrity checks in test mode to allow development
        if context.test_mode:
            stage_ctx.stage.sub_msg = "SKIPPED - Development/Test Mode"
            stage_ctx.set_status(stage_ctx.stage.status)
            log.info('Skipping integrity checks - running in test/development mode')
            return

        validator = IntegrityValidator(
            project_path=context.config.project_path,
            project_directory=context.project_directory,
        )

        # Check experiment integrity
        stage_ctx.stage.sub_msg = "Checking experiment integrity..."
        stage_ctx.set_status(stage_ctx.stage.status)
        validator.check_experiment(
            context.config.experiment_name,
            context.config.environment_name,
            context.experiment_directory,
        )

        # Check project integrity
        stage_ctx.stage.sub_msg = "Checking project integrity..."
        stage_ctx.set_status(stage_ctx.stage.status)
        testfunction_files = experiment_database.get_experiment_testfunction_files(
            context.config.project_path, context.config.environment_name, context.config.experiment_name
        )
        testfunction_files_names = ",".join([file.name for file in testfunction_files])
        log.info(f'experiment {context.config.experiment_name} uses the following testfunction files: {testfunction_files_names}')
        validator.check_project(
            environments=[context.environment_file],
            testfunctions=testfunction_files,
        )

        # Clear sub message when done
        stage_ctx.stage.sub_msg = ""
        stage_ctx.set_status(stage_ctx.stage.status)

def step_prepare_run_environment(context: ExperimentRunCtx, skip_adare_log: bool = False):
    """Consolidated step: Check application data and create run directory.

    Args:
        context: Experiment run context
        skip_adare_log: If True, skip adare.log creation (for dev mode)

    Note:
        - The logs directory is ALWAYS created regardless of runlog flag
        - The runlog flag only controls whether adare.log is copied/configured
        - The adarevm agent writes to logs/adarevm.log automatically
    """
    with StageCtxManager(PrepareRunEnvironmentStage(), context.experiment_run_ulid, event=context.user_interrupt_event):
        # Check application data
        adarevm_uv_lock = ADAREVM_DIR / 'uv.lock'
        adarelib_uv_lock = ADARELIB_DIR / 'uv.lock'
        if adarevm_uv_lock.exists():
            log.info(f'removing {adarevm_uv_lock} to ensure that adarevm is installed correctly')
            adarevm_uv_lock.unlink()
        if adarelib_uv_lock.exists():
            log.info(f'removing {adarelib_uv_lock} to ensure that adarelib is installed correctly')
            adarelib_uv_lock.unlink()

        # Create run directory
        run_dir = ExperimentRunDirectory(context.project_directory, context.config.experiment_name)
        run_dir.create()

        # VALIDATE: Ensure logs directory was created
        if not run_dir.log_directory.exists():
            from adare.exceptions import LoggedException
            raise LoggedException(log, message=f"Failed to create logs directory: {run_dir.log_directory}")

        log.info(f"Run directory created: {run_dir.path}")
        log.info(f"Logs directory verified: {run_dir.log_directory}")

        context.experiment_run_directory = run_dir

        # Copy adare log to run directory if runlog is enabled (skip in dev mode)
        if context.config.runlog and not skip_adare_log:
            _ensure_and_copy_adare_log_to_run_directory(run_dir)

        # Initialize MCP server with log file
        from adare.backend.experiment.mcp_server_manager import MCPServerManager

        # Determine debug output directory
        debug_output_dir = None
        if context.debug_screenshots:
            debug_output_dir = run_dir.screenshots_directory / 'cv_debug'
            # Ensure parent screenshot directory exists (cv_debug will be created by server)
            run_dir.screenshots_directory.mkdir(parents=True, exist_ok=True)
            log.info(f"Enabled CV debug output to: {debug_output_dir}")

        context.mcp_server = MCPServerManager(
            log_file=run_dir.mcp_gui_log_file,
            debug=context.config.dev_mode,
            debug_output_dir=debug_output_dir
        )

def _resolve_and_store_test_execution_mode(context: ExperimentRunCtx):
    """Resolve the test execution mode and store it in context."""
    from adare.backend.experiment.execution.test_executor_factory import resolve_test_execution_mode

    if context.vm is None:
        log.warning("VM not available for test execution mode resolution, defaulting to agent")
        context.test_execution_mode = 'agent'
        return

    try:
        playbook_settings = getattr(context.playbook, 'settings', None) if context.playbook else None
        mode = resolve_test_execution_mode(
            vm=context.vm,
            playbook_settings=playbook_settings,
            cli_override=context.config.test_mode_override
        )
        context.test_execution_mode = mode.value
        log.info(f"Test execution mode resolved to: {mode.value}")
    except ValueError as e:
        log.warning(f"Failed to resolve test execution mode: {e}, defaulting to agent")
        context.test_execution_mode = 'agent'

async def step_execute_installations_via_qga(context: ExperimentRunCtx):
    """Execute environment installations via QGA guest-exec (no WebSocket needed)."""
    from adare.backend.experiment.agent_lifecycle import execute_installations_via_qga
    with StageCtxManager(InstallationsStage(), context.experiment_run_ulid, event=context.user_interrupt_event) as stage_ctx:
        await execute_installations_via_qga(context, stage_ctx)

async def step_install_and_run_websocket_server(context: ExperimentRunCtx):
    with StageCtxManager(InstallAdareVMStage(), context.experiment_run_ulid, event=context.user_interrupt_event):
        await install_and_run_adare_vm(context, stop_event=context.user_interrupt_event)

async def step_connect_websocket(context: ExperimentRunCtx):
    from adare.backend.experiment.agent_lifecycle import connect_websocket
    with StageCtxManager(ConnectToVMStage(), context.experiment_run_ulid, event=context.user_interrupt_event) as stage_ctx:
        await connect_websocket(context, stage_ctx)

async def step_execute_installations(context: ExperimentRunCtx):
    from adare.backend.experiment.agent_lifecycle import execute_installations_via_websocket
    with StageCtxManager(InstallationsStage(), context.experiment_run_ulid, event=context.user_interrupt_event) as stage_ctx:
        await execute_installations_via_websocket(context, stage_ctx)

async def step_start_mcp_server(context: ExperimentRunCtx):
    """Start the MCP GUI server for target detection."""
    with StageCtxManager(StartComputerVisionServerStage(), context.experiment_run_ulid, event=context.user_interrupt_event):
        log.info("Starting MCP GUI server for target detection...")

        success = await context.mcp_server.start()
        if success:
            log.info("MCP GUI server started successfully")
        else:
            from adare.exceptions import LoggedException
            raise LoggedException(log, "MCP GUI server failed to start - cannot proceed without target detection capabilities")

async def step_execute_experiment(context: ExperimentRunCtx):
    """Execute the experiment using the playbook controller."""

    is_host_test_mode = context.test_execution_mode == 'host'

    # First, install testfunction dependencies in a separate stage
    from adare.types.stages import TestfunctionDependenciesStage
    from adare.backend.experiment.test_loader import TestLoader

    stage_deps = TestfunctionDependenciesStage()
    with StageCtxManager(stage_deps, context.experiment_run_ulid, event=context.user_interrupt_event):
        test_loader = TestLoader(
            experiment_dir=context.experiment_directory.path,
            project_dir=context.project_directory.path,
            playbook=context.playbook,
            variable_resolver=None
        )
        if is_host_test_mode:
            log.info("Host test mode: skipping testfunction dependency installation in VM (dependencies run on host)")
        else:
            await test_loader._install_dependencies_only(context.client)

    # Then run the actual experiment
    with StageCtxManager(ExperimentRunStage(), context.experiment_run_ulid, event=context.user_interrupt_event) as stage:
        from adare.backend.experiment.playbook_controller import PlaybookController

        # In agent mode, WebSocket client is required
        if not is_host_test_mode and not context.client:
            log.error("WebSocket client not available for experiment execution")
            return

        # Get experiment ID for execution tracking
        experiment_id = None
        try:
            experiment_id = experiment_database.get_experiment_by_project_and_name(
                context.config.project_path,
                context.config.experiment_name
            )
            if experiment_id:
                log.debug(f"Found experiment {experiment_id} for execution tracking")
            else:
                log.warning("No experiment ID found - execution tracking will be disabled")
        except Exception as e:
            log.warning(f"Failed to get experiment ID for execution tracking: {e}")

        # Get VM credentials for automatic variables
        from adare.config import get_vm_credentials
        vm_os = context.guest_platform if context.guest_platform else None
        vm_user = None
        if vm_os:
            vm_user, _ = get_vm_credentials(vm_os)

        # Get flow console for interactive actions like pause
        flow_console = flowconsolemanager.get_handler(context.experiment_run_ulid)

        # Create playbook controller
        controller = PlaybookController(
            websocket_client=context.client,  # May be None in host mode
            experiment_dir=context.experiment_directory.path,
            project_dir=context.project_directory.path,
            debug_screenshots=context.debug_screenshots,
            screenshots_dir=context.experiment_run_directory.screenshots_directory,
            playbook=context.playbook,
            experiment_id=experiment_id,
            experiment_run_id=context.experiment_run_ulid,
            vm=context.vm,
            experiment_run_directory=context.experiment_run_directory.path,
            vm_os=vm_os,
            vm_user=vm_user,
            flow_console=flow_console,
            test_mode=context.test_mode,
            config=context.config
        )

        # Set up host-mode test executor if in HOST test mode
        if is_host_test_mode:
            _setup_host_mode_test_executor(controller, context, vm_os)

        # Execute complete experiment (playbook + tests)
        log.info(f"Starting experiment execution for {context.config.experiment_name}")
        result = await controller.execute_experiment(context.experiment_directory.path)

        # Store execution result in context for final message generation
        context.execution_result = result

        # Cleanup host-mode executor temp files
        if is_host_test_mode and hasattr(controller, '_host_mode_test_executor'):
            controller._host_mode_test_executor.cleanup()

        if result.success:
            log.info(f"Experiment completed successfully: {result.successful_actions}/{result.total_actions} actions succeeded")
        else:
            log.error(f"Experiment failed: {result.error_message}")
            log.error(f"Action results: {result.successful_actions}/{result.total_actions} succeeded")

def _setup_host_mode_test_executor(controller, context: ExperimentRunCtx, vm_os: str):
    """Set up host-mode test execution on the PlaybookController."""
    from adare.backend.experiment.execution.base import TestExecutionMode
    from adare.backend.experiment.host_mode_test_executor import HostModeTestExecutor
    from adare.backend.experiment.host_services.guest_file_proxy import GuestFileProxy
    from adare.backend.experiment.host_services.guest_command_proxy import GuestCommandProxy
    from adarelib.testset.testfunction import import_basictest_subclasses
    from adare.config.configdirectory import STATE_DIR

    guest_os = vm_os or 'linux'

    # Create QGA proxies
    guest_file = GuestFileProxy(vm=context.vm, guest_os=guest_os)
    guest_command = GuestCommandProxy(vm=context.vm, guest_os=guest_os)

    # Load testfunctions locally on host
    global_testfunctions_path = STATE_DIR / 'testfunctions'
    if global_testfunctions_path.exists():
        testfunction_collection = import_basictest_subclasses(directory=global_testfunctions_path)
        log.info(f"Host mode: loaded {sum(len(v) for v in testfunction_collection.values())} testfunctions locally")
    else:
        testfunction_collection = {}
        log.warning("Host mode: no testfunctions directory found")

    # Pre-flight validation: check all playbook tests are host-mode compatible
    playbook_tests = getattr(context.playbook, 'tests', [])
    if playbook_tests:
        ok, issues = HostModeTestExecutor.validate_playbook_tests(playbook_tests, testfunction_collection)
        if not ok:
            from adare.exceptions import LoggedException
            issue_list = '\n  - '.join(issues)
            raise LoggedException(
                log,
                f"Host-mode test validation failed. The following tests cannot run in host mode:\n  - {issue_list}\n"
                f"Use --test-mode agent to run these tests via the in-guest agent instead."
            )
        log.info(f"Host mode: pre-flight validation passed for {len(playbook_tests)} tests")

    # Create host-mode test executor
    host_mode_executor = HostModeTestExecutor(
        guest_file=guest_file,
        guest_command=guest_command,
        testfunction_collection=testfunction_collection,
    )

    # Store for cleanup and wire into the action executor
    controller._host_mode_test_executor = host_mode_executor
    controller.action_executor.test_actions.set_test_execution_mode(TestExecutionMode.HOST)
    controller.action_executor.test_actions.set_host_mode_test_executor(host_mode_executor)
    log.info("Host mode: HostModeTestExecutor configured")

async def step_collect_system_info(context: ExperimentRunCtx):
    """Collect system information from the guest VM and save to YAML file."""
    with StageCtxManager(SystemInfoCollectionStage(), context.experiment_run_ulid, event=context.user_interrupt_event):
        # Check if system info collection is enabled in playbook settings
        collect_enabled = getattr(context.playbook.settings, 'collect_system_info', True)
        if not collect_enabled:
            log.info("System info collection disabled in playbook settings")
            return

        if not context.guest_platform:
            log.warning("Guest platform not detected - skipping system info collection")
            return

        if not hasattr(context, 'experiment_run_directory') or not context.experiment_run_directory:
            log.warning("Experiment run directory not available - skipping system info collection")
            return

        output_file = context.experiment_run_directory.system_info_file

        # Use QGA-based collection in host test mode, WebSocket otherwise
        is_host_test_mode = context.test_execution_mode == 'host'

        if is_host_test_mode and context.vm:
            from adare.backend.experiment.system_info_collector import collect_system_info_via_qga
            success = await collect_system_info_via_qga(
                vm=context.vm,
                guest_platform=context.guest_platform,
                output_file=output_file
            )
        elif context.client:
            from adare.backend.experiment.system_info_collector import collect_system_info
            success = await collect_system_info(
                websocket_client=context.client,
                guest_platform=context.guest_platform,
                output_file=output_file
            )
        else:
            log.warning("Neither WebSocket client nor VM available - skipping system info collection")
            return

        if success:
            log.info(f"System information collected and saved to {output_file}")
        else:
            log.warning("System information collection failed (experiment continues)")

def step_finalize(context: ExperimentRunCtx, post_interrupt: bool = False):
    event = None if post_interrupt else context.user_interrupt_event
    with StageCtxManager(FinalizeStage(), context.experiment_run_ulid, event=event):
        timestamp_end = datetime.now(timezone.utc)
        experiment_database.update_experiment_run_end(context.project_directory.path, context.experiment_run_ulid, timestamp_end)
        duration_total = timestamp_end - context.timestamp_start
        duration_vm = timestamp_end - context.timestamp_before_vm_start
        log.info(f"Experiment run {context.experiment_run_ulid} finished after {duration_total} seconds (vm run time: {duration_vm})")
        __cleanup_experiment_run(context.experiment_run_directory)

async def step_shutdown_mcp_server(context: ExperimentRunCtx, post_interrupt: bool = False, force: bool = False):
    """Stop the MCP GUI server."""
    event = None if post_interrupt else context.user_interrupt_event
    with StageCtxManager(ShutdownComputerVisionServerStage(), context.experiment_run_ulid, event=event):
        log.info('stopping MCP GUI server')
        if context.mcp_server is not None:
            await context.mcp_server.stop(force_external=force)

async def step_shutdown_ws(context: ExperimentRunCtx, post_interrupt: bool = False):
    event = None if post_interrupt else context.user_interrupt_event
    with StageCtxManager(ShutdownWebSocketStage(), context.experiment_run_ulid, event=event):
        log.info('stopping websocket client')
        if context.client:
            await context.client.disconnect()

def step_remove_fake_experiment_run(context: ExperimentRunCtx):
    # todo remove associated stuff as well (e.g. stages/files/...)
    experiment_database.remove_fake_experiment_run(context.project_directory.path, context.experiment_run_ulid)
    log.info(f'fake experiment run {context.experiment_run_ulid} removed')

async def experiment_run(project_path: Path, experiment_name: str, environment_name: str, disable_printing: bool = False, test: bool = True, debug_screenshots: bool = False, preserve_snapshot: bool = False, runlog: bool = True, vm_memory: int = None, vm_cpus: int = None, gui_mode: str = None, test_exec_mode: str = None, diff: bool = None, diff_mode: str = 'auto'):
    import signal
    import asyncio

    log.info(f"Starting experiment run {experiment_name} in project {project_path}")

    # Create the experiment context and initialize it.
    config = ExperimentConfig(
        project_path=project_path,
        experiment_name=experiment_name,
        environment_name=environment_name,
        preserve_snapshot=preserve_snapshot,
        runlog=runlog,
        test_mode=test
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
                    log.info(f"Using Windows default VM memory: 8192MB")
                else:
                    config.vm_memory = 4096  # 4GB for Linux
                    log.info(f"Using Linux default VM memory: 4096MB")
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
        step_initialize(experiment_run_context, fake=True)  # Test mode: creates fake run
    else:
        step_initialize(experiment_run_context)  # Production mode: creates real run

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
                total_duration = (datetime.now(timezone.utc) - experiment_run_context.timestamp_start).total_seconds()

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
            log.error(f"Error during shutdown: {e}", exc_info=True)
            # Ensure coordinator is stopped even if cleanup fails
            try:
                from adare.backend.events.coordinator import stop_stage_coordinator
                stop_stage_coordinator()
            except Exception as cleanup_error:
                log.error(f"Error stopping stage coordinator during error cleanup: {cleanup_error}", exc_info=True)

    # Query the database to get the actual experiment success status
    experiment_success = False
    try:
        from adare.database.api.experiment import ExperimentApi
        from adare.database.models.project_models import ExperimentRun
        with ExperimentApi(experiment_run_context.project_directory.path) as api:
            experiment_run = api._session.query(ExperimentRun).filter(ExperimentRun.id == experiment_run_context.experiment_run_ulid).first()
            if experiment_run:
                # Use the result_status property to determine actual success
                experiment_success = experiment_run.result_status == StatusEnum.SUCCESS
    except Exception as e:
        log.error(f"Error checking experiment run status: {e}")
        experiment_success = False

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
    except Exception as e:
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
    import asyncio

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
