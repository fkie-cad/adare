"""Experiment run setup steps and helpers.

This module contains all the individual step functions used during experiment
setup, execution, and teardown. These are extracted from run.py to keep each
module under 1000 lines.

The main orchestration (experiment_run, experiment_test) remains in run.py.
"""

import logging
from datetime import UTC, datetime
from pathlib import Path

import adare.backend.environment.database as environment_database
import adare.backend.experiment.database as experiment_database
from adare.backend.experiment.agent_lifecycle import install_and_run_adare_vm
from adare.backend.experiment.directory import ExperimentDirectory, ExperimentRunDirectory
from adare.backend.experiment.integrity_validator import IntegrityValidator
from adare.backend.experiment.print import flowconsolemanager
from adare.backend.experiment.runctx import ExperimentRunCtx, MachineRunCtx
from adare.backend.experiment.stagectxmanager import StageCtxManager
from adare.backend.project.directory import ProjectDirectory
from adare.config.configdirectory import ADARELIB_DIR, ADAREVM_DIR
from adare.exceptions import LoggedException
from adare.types.stages import (
    ConnectToVMStage,
    ExperimentRunStage,
    FinalizeStage,
    InstallAdareVMStage,
    InstallationsStage,
    PrepareRunEnvironmentStage,
    SetupExperimentEnvironmentStage,
    ShutdownComputerVisionServerStage,
    ShutdownWebSocketStage,
    StartComputerVisionServerStage,
    SystemInfoCollectionStage,
    TestfunctionDependenciesStage,
    ValidateIntegrityStage,
)

log = logging.getLogger(__name__)


def _ensure_and_copy_adare_log_to_run_directory(
    run_directory: ExperimentRunDirectory, copy_existing: bool = True, file_log_level: int = logging.INFO
):
    """Ensure a log file exists and copy it to the experiment run directory.

    If no log file is currently active (e.g., when --logfile is not specified),
    this function will create a temporary log file in the run directory and
    configure logging to use it, ensuring the experiment run has log output.

    Args:
        run_directory: The experiment run directory where the log should be copied
        copy_existing: Whether to copy the existing log file (default: True).
                      Set to False for dev mode/long-running processes to avoid copying history.
        file_log_level: Logging level for the file handler (default: logging.INFO).
    """
    import logging
    import shutil

    from adare.logger.logger import FileHandlerFormatter, get_current_logfile

    current_logfile = get_current_logfile()
    target_path = run_directory.log_directory / 'adare.log'

    if current_logfile and copy_existing:
        # Copy existing log file
        try:
            shutil.copy2(current_logfile, target_path)
            log.info(f'Copied adare log to {target_path}')
        except OSError as e:
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
        file_handler.setLevel(file_log_level)

        # Add handler to root logger to capture all log messages
        root_logger = logging.getLogger()
        root_logger.addHandler(file_handler)

        # Unconditionally ensure root logger level is low enough for the file handler.
        # Without this, the root logger may stay at WARNING (the console default),
        # silently dropping INFO messages before they ever reach the file handler.
        previous_level = root_logger.level
        root_logger.setLevel(min(root_logger.level, file_log_level) if root_logger.level > 0 else file_log_level)

        log.info(
            f'Configured logging to {target_path} '
            f'(root level: {logging.getLevelName(previous_level)} -> {logging.getLevelName(root_logger.level)}, '
            f'handlers: {len(root_logger.handlers)})'
        )
    except (OSError, ValueError) as e:
        log.warning(f'Failed to configure logging to run directory: {e}')


def __cleanup_experiment_run(experiment_run_directory: ExperimentRunDirectory):
    if experiment_run_directory is not None:
        experiment_run_directory.clean()


def step_initialize(context: ExperimentRunCtx, fake: bool = False, run_ulid: str = None):
    # Initialize experiment run in database (using optional specific ULID if provided)
    context.experiment_run_ulid = experiment_database.initialize_experiment_run(
        context.config.project_path, fake, id=run_ulid
    )
    context.timestamp_start = datetime.now(UTC)
    context.timestamp_before_vm_start = datetime.now(UTC)
    context.adarevm = ADAREVM_DIR
    context.adarelib = ADARELIB_DIR
    log.info(f'initialized experiment run {context.experiment_run_ulid}')


def _apply_playbook_resolution(context: ExperimentRunCtx):
    """Copy the playbook's optional `settings.resolution` onto the run config.

    Unset/None leaves ``vm_display_resolution`` at its default (None), so the VM
    builder advertises the host/env default and issues no guest-side mode-set.
    """
    settings = getattr(context.playbook, 'settings', None) if context.playbook else None
    resolution = getattr(settings, 'resolution', None) if settings else None
    if resolution:
        context.config.vm_display_resolution = resolution
        log.info(f"Playbook requests guest display resolution: {resolution}")


def step_setup_experiment_environment(context: ExperimentRunCtx):
    """Consolidated step: Setup directories, validate playbook, and resolve environment."""
    with StageCtxManager(
        SetupExperimentEnvironmentStage(), context.experiment_run_ulid, event=context.user_interrupt_event
    ):
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
            context.config.project_path,
        )
        log.info(f'set base experiment info for run {context.experiment_run_ulid}')

        # Set experiment start timestamp early to ensure it's persisted even if interrupted
        experiment_database.update_experiment_run_start(
            context.project_directory.path, context.experiment_run_ulid, context.timestamp_start
        )
        log.info(f'set experiment start timestamp for run {context.experiment_run_ulid}')

        # Validate playbook
        try:
            experiment_id = experiment_database.get_experiment_by_project_and_name(
                context.config.project_path, context.config.experiment_name
            )
            if not experiment_id:
                # Fallback to file-based parsing for new/untracked experiments
                log.info("Experiment not found in database, falling back to file-based parsing")
                from adare.types.playbook import parse_playbook

                playbook_path = context.experiment_directory.path / "playbook.yml"
                if not playbook_path.exists():
                    log.warning(
                        "No playbook.yml found - experiment cannot run GUI actions (experiment may be incomplete)"
                    )
                    return
                # Get VM OS and user for automatic variables
                context.playbook = parse_playbook(playbook_path)
                log.info(f"Playbook validation successful - {len(context.playbook.actions)} actions found")
                _apply_playbook_resolution(context)
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

                    playbook_path = context.experiment_directory.path / "playbook.yml"
                    if not playbook_path.exists():
                        log.warning(
                            "No playbook.yml found - experiment cannot run GUI actions (experiment may be incomplete)"
                        )
                        return
                    context.playbook = parse_playbook(playbook_path)
                    log.info(f"Playbook validation successful - {len(context.playbook.actions)} actions found")

        except (ValueError, KeyError, OSError, TypeError) as e:
            raise LoggedException(log, f"Playbook loading failed: {str(e)}") from e

        # Carry the playbook's optional display-resolution setting into the run
        # config so the QEMU VM builder can advertise it (mirrors iso_path plumbing).
        _apply_playbook_resolution(context)

        # Verify integrity of testfunctions used in playbook
        # TODO: Re-enable this for production use - currently disabled for testing
        # Temporarily commented out to allow testfunction modifications during testing
        # if hasattr(context, 'playbook') and context.playbook:
        #     validator = IntegrityValidator(context.config.project_path)
        #     validator.verify_playbook_testfunctions(context.playbook)

        # Resolve environment name(s). Multi-machine playbooks (`playbook.machines`)
        # resolve one MachineRunCtx per machine key from its MachineSpec.environment;
        # today's single-VM playbooks (no `machines:` key) resolve exactly one, under
        # the implicit `None` key -- net-zero behavior change for existing playbooks.
        machines_spec = getattr(context.playbook, 'machines', None) if context.playbook else None
        if machines_spec:
            for machine_key, spec in machines_spec.items():
                _resolve_machine_environment(context, machine_key, spec.environment)
        else:
            if context.config.environment_name:
                environment_name = context.config.environment_name
            else:
                environment_name = experiment_database.get_experiment_environment_name(
                    context.config.project_path, context.config.experiment_name
                )
                context.config.environment_name = environment_name
            _resolve_machine_environment(context, context.primary_machine, environment_name)


def _resolve_machine_environment(
    context: ExperimentRunCtx, machine_key: str | None, environment_name: str
) -> MachineRunCtx:
    """Resolve one machine's environment metadata (VM file, guest OS/arch, hypervisor).

    Populates and returns the ``MachineRunCtx`` for ``machine_key`` in
    ``context.machines``. Called once per ``MachineSpec`` for a multi-machine
    playbook, or once for the implicit ``None`` key otherwise.
    """
    machine_ctx = context.machines.setdefault(machine_key, MachineRunCtx())

    # One version, read once: everything below is keyed by its ULID.
    environment = environment_database.get_run_environment(environment_name)
    machine_ctx.environment_file = environment['file']
    machine_ctx.environment_ulid = environment['ulid']

    environment_database.verify_environment_vm(machine_ctx.environment_ulid)

    # For lazy loading, VM file might not be available yet - will be resolved during VM creation
    machine_ctx.vm_file = environment['vm_file']
    machine_ctx.guest_platform = environment['platform']
    machine_ctx.hypervisor_type = environment['hypervisor']
    if environment['architecture']:
        machine_ctx.guest_architecture = environment['architecture']

    # If VM file is not available, get from environment metadata directly
    if not machine_ctx.vm_file or not machine_ctx.guest_platform or not machine_ctx.guest_architecture:
        from adare.types.environment import parse_environment_file

        environment_metadata = parse_environment_file(machine_ctx.environment_file)
        if not machine_ctx.vm_file:
            machine_ctx.vm_file = Path(environment_metadata.vm)
        if not machine_ctx.guest_platform:
            machine_ctx.guest_platform = environment_metadata.os.platform
        if not machine_ctx.guest_architecture and hasattr(environment_metadata.os, 'architecture'):
            machine_ctx.guest_architecture = environment_metadata.os.architecture

    log.info(
        f'found environment {environment_name} for machine {machine_key!r} (hypervisor: {machine_ctx.hypervisor_type})'
    )
    return machine_ctx


def step_validate_integrity(context: ExperimentRunCtx):
    """Consolidated step: Check experiment and project integrity."""
    with StageCtxManager(
        ValidateIntegrityStage(), context.experiment_run_ulid, event=context.user_interrupt_event
    ) as stage_ctx:
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
        log.info(
            f'experiment {context.config.experiment_name} uses the following testfunction files: {testfunction_files_names}'
        )
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
            _ensure_and_copy_adare_log_to_run_directory(run_dir, file_log_level=context.config.file_log_level)

        # Initialize one MCP (CV/OCR) server per machine -- multi-machine playbooks
        # get one cv-server per machine (each needs its own port/log/debug dir);
        # today's single-VM playbooks (no `machines:` key) get exactly one, under
        # the implicit None key -- net-zero behavior change.
        from adare.backend.experiment.mcp_server_manager import MCPServerManager, find_free_cv_port

        for machine_key, view in _machine_views(context):
            # Determine debug output directory
            debug_output_dir = None
            if context.debug_screenshots:
                debug_output_dir = run_dir.screenshots_directory / 'cv_debug'
                if machine_key is not None:
                    debug_output_dir = debug_output_dir.with_name(f'cv_debug_{machine_key}')
                # Ensure parent screenshot directory exists (cv_debug will be created by server)
                run_dir.screenshots_directory.mkdir(parents=True, exist_ok=True)
                log.info(f"Enabled CV debug output to: {debug_output_dir}")

            log_file = run_dir.mcp_gui_log_file
            if machine_key is not None:
                log_file = log_file.with_name(f"{log_file.stem}-{machine_key}{log_file.suffix}")

            # Pick a free port rather than taking the fixed default: two concurrent
            # `adare experiment run` invocations (or, here, two machines of the same
            # run) would otherwise share one cv-server, and the loser's CV debug
            # images and mcp_gui.log would be written into the winner's run
            # directory (both are fixed in the spawned process's argv). The chosen
            # URL is handed to the PlaybookController in step_execute_experiment so
            # each machine's resolver talks to ITS run's server.
            cv_port = find_free_cv_port()

            view.mcp_server = MCPServerManager(
                server_port=cv_port, log_file=log_file, debug=context.config.dev_mode, debug_output_dir=debug_output_dir
            )
            log.info(f"CV/OCR server for machine {machine_key!r} will use port {cv_port}")


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
            vm=context.vm, playbook_settings=playbook_settings, cli_override=context.config.test_mode_override
        )
        context.test_execution_mode = mode.value
        log.info(f"Test execution mode resolved to: {mode.value}")
    except ValueError as e:
        log.warning(f"Failed to resolve test execution mode: {e}, defaulting to agent")
        context.test_execution_mode = 'agent'


def _machine_views(context: ExperimentRunCtx):
    """Yield a ``(machine_key, view)`` pair for each machine to drive.

    Multi-machine playbooks (``playbook.machines`` with >=2 entries) yield one
    ``_MachineContextView`` per declared machine, so agent-lifecycle helpers
    written for a single-VM ``ExperimentRunCtx`` run once per machine unmodified.
    Today's single-VM playbooks (no ``machines:`` key) yield the context itself
    once -- net-zero behavior change.
    """
    from adare.backend.experiment.vm_orchestrator import _MachineContextView

    machines_spec = getattr(context.playbook, 'machines', None) if context.playbook else None
    if machines_spec and len(machines_spec) > 1:
        for machine_key in machines_spec:
            yield machine_key, _MachineContextView(context, machine_key)
    else:
        yield context.primary_machine, context


async def _run_per_machine_installations(context: ExperimentRunCtx, install_fn):
    """Run an installation-execution function once per machine.

    Skips the stage entirely when there is nothing to install on any machine, so
    the "Installing environment software" row never appears for empty environments.
    """
    pending = [
        (key, view)
        for key, view in _machine_views(context)
        if environment_database.get_environment_installations(context.machines[key].environment_ulid)
    ]
    if not pending:
        log.info("No environment installations to execute; skipping stage")
        return
    with StageCtxManager(
        InstallationsStage(), context.experiment_run_ulid, event=context.user_interrupt_event
    ) as stage_ctx:
        for _key, view in pending:
            await install_fn(view, stage_ctx)


async def step_execute_installations_via_qga(context: ExperimentRunCtx):
    """Execute environment installations via QGA guest-exec (no WebSocket needed)."""
    from adare.backend.experiment.agent_lifecycle import execute_installations_via_qga

    await _run_per_machine_installations(context, execute_installations_via_qga)


async def step_install_and_run_websocket_server(context: ExperimentRunCtx):
    with StageCtxManager(InstallAdareVMStage(), context.experiment_run_ulid, event=context.user_interrupt_event):
        for _key, view in _machine_views(context):
            await install_and_run_adare_vm(view, stop_event=context.user_interrupt_event)


async def step_connect_websocket(context: ExperimentRunCtx):
    from adare.backend.experiment.agent_lifecycle import connect_websocket, stop_agent
    from adare.backend.experiment.exceptions import AgentAuthenticationError, AgentProtocolMismatchError
    from adare.backend.experiment.websocket_client import AgentAuthError, AgentProtocolError

    with StageCtxManager(
        ConnectToVMStage(), context.experiment_run_ulid, event=context.user_interrupt_event
    ) as stage_ctx:
        for _key, view in _machine_views(context):
            try:
                try:
                    await connect_websocket(view, stage_ctx)
                except AgentProtocolError as e:
                    # An agent from before the current protocol (e.g. a dev session
                    # restored from an older snapshot): replace it once, then retry.
                    log.warning(f"{e}; reinstalling the guest agent")
                    await stop_agent(view, context.user_interrupt_event)
                    await install_and_run_adare_vm(view, stop_event=context.user_interrupt_event, force_install=True)
                    await connect_websocket(view, stage_ctx)
            except AgentProtocolError as e:
                raise AgentProtocolMismatchError(
                    log,
                    f"The guest agent is still incompatible after reinstalling it: {e}",
                    [
                        'Restart the VM (or start a fresh dev session) so no old adarevm keeps the port',
                        'Rebuild the agent wheels with `adare runtime build` and run again',
                    ],
                ) from e
            except AgentAuthError as e:
                raise AgentAuthenticationError(
                    log,
                    str(e),
                    ["The run's config.json and the running agent disagree; restart the VM or the dev session"],
                ) from e


async def step_execute_installations(context: ExperimentRunCtx):
    from adare.backend.experiment.agent_lifecycle import execute_installations_via_websocket

    await _run_per_machine_installations(context, execute_installations_via_websocket)


async def step_start_mcp_server(context: ExperimentRunCtx):
    """Start the MCP GUI server(s) for target detection -- one per machine."""
    with StageCtxManager(
        StartComputerVisionServerStage(), context.experiment_run_ulid, event=context.user_interrupt_event
    ):
        for machine_key, view in _machine_views(context):
            log.info(f"Starting MCP GUI server for machine {machine_key!r}...")

            success = await view.mcp_server.start()
            if success:
                log.info(f"MCP GUI server started successfully for machine {machine_key!r}")
                # Record which port/PID this run or dev session owns, so a resumed dev
                # session reclaims its own server instead of allocating a second one and
                # leaking the first. Written here rather than at each construction site
                # so dev start, dev resume and production runs all record it identically.
                if context.experiment_run_directory is not None:
                    from adare.backend.experiment.mcp_server_manager import save_cv_state

                    save_cv_state(
                        context.experiment_run_directory.path,
                        view.mcp_server.server_port,
                        view.mcp_server.known_server_pid,
                        machine_key=machine_key,
                    )
            else:
                from adare.exceptions import LoggedException

                raise LoggedException(
                    log,
                    f"MCP GUI server failed to start for machine {machine_key!r} - cannot proceed without target detection capabilities",
                )


async def step_execute_experiment(context: ExperimentRunCtx):
    """Execute the experiment using the playbook controller."""

    is_host_test_mode = context.test_execution_mode == 'host'

    # First, install testfunction dependencies in a separate stage
    from adare.backend.experiment.test_loader import TestLoader

    stage_deps = TestfunctionDependenciesStage()
    with StageCtxManager(stage_deps, context.experiment_run_ulid, event=context.user_interrupt_event):
        test_loader = TestLoader(
            experiment_dir=context.experiment_directory.path,
            project_dir=context.project_directory.path,
            playbook=context.playbook,
            variable_resolver=None,
        )
        if is_host_test_mode:
            log.info("Host test mode: skipping testfunction dependency installation in VM (dependencies run on host)")
        else:
            for _key, view in _machine_views(context):
                await test_loader._install_dependencies_only(view.client)

    # Then run the actual experiment
    with StageCtxManager(ExperimentRunStage(), context.experiment_run_ulid, event=context.user_interrupt_event):
        from adare.backend.experiment.playbook_controller import PlaybookController

        # In agent mode, WebSocket client is required
        if not is_host_test_mode and not context.client:
            log.error("WebSocket client not available for experiment execution")
            return

        # Get experiment ID for execution tracking
        experiment_id = None
        try:
            experiment_id = experiment_database.get_experiment_by_project_and_name(
                context.config.project_path, context.config.experiment_name
            )
            if experiment_id:
                log.debug(f"Found experiment {experiment_id} for execution tracking")
            else:
                log.warning("No experiment ID found - execution tracking will be disabled")
        except (ValueError, KeyError, OSError) as e:
            log.warning(f"Failed to get experiment ID for execution tracking: {e}")

        # Get VM credentials for automatic variables
        from adare.config import get_vm_credentials

        vm_os = context.guest_platform if context.guest_platform else None
        vm_user = None
        if vm_os:
            vm_user, _ = get_vm_credentials(vm_os)

        # Get flow console for interactive actions like pause
        flow_console = flowconsolemanager.get_handler(context.experiment_run_ulid)

        # Point the target resolver at THIS run's cv-server. Without this the
        # controller falls back to its hardcoded http://localhost:13109/mcp default
        # (playbook_controller.py / target_resolver.py), which under concurrency is a
        # different run's server — or nothing at all. diff_run.py and the dev-session
        # path already pass this; the production run path did not.
        controller_kwargs = {}
        if context.mcp_server is not None:
            controller_kwargs['mcp_gui_url'] = context.mcp_server.server_url

        # Multi-machine playbooks: build one MachineHandles per machine so the
        # controller's ActionExecutor can route each action to its `machine:`.
        machines_spec = getattr(context.playbook, 'machines', None) if context.playbook else None
        if machines_spec and len(machines_spec) > 1:
            from adare.backend.experiment.action_executor import MachineHandles

            machine_handles = {}
            for machine_key in machines_spec:
                machine_ctx = context.machines[machine_key]
                machine_vm_os = machine_ctx.guest_platform or None
                machine_vm_user = None
                if machine_vm_os:
                    machine_vm_user, _ = get_vm_credentials(machine_vm_os)
                machine_handles[machine_key] = MachineHandles(
                    vm=machine_ctx.vm,
                    client=machine_ctx.client,
                    vm_os=machine_vm_os,
                    vm_user=machine_vm_user,
                    mcp_gui_url=machine_ctx.mcp_server.server_url
                    if machine_ctx.mcp_server
                    else "http://localhost:13109/mcp",
                )
            controller_kwargs['machines'] = machine_handles

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
            config=context.config,
            **controller_kwargs,
        )

        # Set up host-mode test executor if in HOST test mode
        if is_host_test_mode:
            _setup_guest_to_host_test_executor(controller, context.vm, context.playbook, vm_os)

        # Execute complete experiment (playbook + tests)
        log.info(f"Starting experiment execution for {context.config.experiment_name}")
        result = await controller.execute_experiment(context.experiment_directory.path)

        # Store execution result in context for final message generation
        context.execution_result = result

        # Cleanup host-mode executor temp files
        if is_host_test_mode and hasattr(controller, '_guest_to_host_test_executor'):
            controller._guest_to_host_test_executor.cleanup()

        if result.success:
            log.info(
                f"Experiment completed successfully: {result.successful_actions}/{result.total_actions} actions succeeded"
            )
        else:
            log.error(f"Experiment failed: {result.error_message}")
            log.error(f"Action results: {result.successful_actions}/{result.total_actions} succeeded")


def _setup_guest_to_host_test_executor(controller, vm, playbook, vm_os: str):
    """Set up host-mode test execution on the PlaybookController.

    Takes ``vm`` and ``playbook`` directly (rather than an ExperimentRunCtx) so
    the dev-mode playbook path can reuse it without building a full run context.
    """
    from adare.backend.experiment.execution.base import TestExecutionMode
    from adare.backend.experiment.guest_to_host_test_executor import GuestToHostTestExecutor
    from adare.backend.experiment.host_services.guest_command_proxy import GuestCommandProxy
    from adare.backend.experiment.host_services.guest_file_proxy import GuestFileProxy
    from adare.config.configdirectory import STATE_DIR
    from adarelib.testset.testfunction import import_basictest_subclasses

    guest_os = vm_os or 'linux'

    # Create QGA proxies
    guest_file = GuestFileProxy(vm=vm, guest_os=guest_os)
    guest_command = GuestCommandProxy(vm=vm, guest_os=guest_os)

    # Load testfunctions locally on host
    global_testfunctions_path = STATE_DIR / 'testfunctions'
    if global_testfunctions_path.exists():
        testfunction_collection = import_basictest_subclasses(directory=global_testfunctions_path)
        log.info(f"Host mode: loaded {sum(len(v) for v in testfunction_collection.values())} testfunctions locally")
    else:
        testfunction_collection = {}
        log.warning("Host mode: no testfunctions directory found")

    # Pre-flight validation: check all playbook tests are host-mode compatible
    playbook_tests = getattr(playbook, 'tests', [])
    if playbook_tests:
        ok, issues = GuestToHostTestExecutor.validate_playbook_tests(playbook_tests, testfunction_collection)
        if not ok:
            from adare.exceptions import LoggedException

            issue_list = '\n  - '.join(issues)
            raise LoggedException(
                log,
                f"Host-mode test validation failed. The following tests cannot run in host mode:\n  - {issue_list}\n"
                f"Use --test-mode agent to run these tests via the in-guest agent instead.",
            )
        log.info(f"Host mode: pre-flight validation passed for {len(playbook_tests)} tests")

    # Create host-mode test executor
    guest_to_host_executor = GuestToHostTestExecutor(
        guest_file=guest_file,
        guest_command=guest_command,
        testfunction_collection=testfunction_collection,
    )

    # Store for cleanup and wire into the action executor
    controller._guest_to_host_test_executor = guest_to_host_executor
    controller.action_executor.test_actions.set_test_execution_mode(TestExecutionMode.HOST)
    controller.action_executor.test_actions.set_guest_to_host_test_executor(guest_to_host_executor)
    log.info("Host mode: GuestToHostTestExecutor configured")


async def step_collect_system_info(context: ExperimentRunCtx):
    """Collect system information from the guest VM(s) and save to YAML file(s)."""
    with StageCtxManager(SystemInfoCollectionStage(), context.experiment_run_ulid, event=context.user_interrupt_event):
        # Check if system info collection is enabled in playbook settings
        collect_enabled = getattr(context.playbook.settings, 'collect_system_info', True)
        if not collect_enabled:
            log.info("System info collection disabled in playbook settings")
            return

        if not hasattr(context, 'experiment_run_directory') or not context.experiment_run_directory:
            log.warning("Experiment run directory not available - skipping system info collection")
            return

        machine_views = list(_machine_views(context))
        multi_machine = len(machine_views) > 1
        for machine_key, view in machine_views:
            await _collect_machine_system_info(context, machine_key, view, multi_machine)


async def _collect_machine_system_info(context: ExperimentRunCtx, machine_key, view, multi_machine: bool):
    """Collect system info for one machine. `view` may be the context itself (single-VM) or a per-machine view."""
    if not view.guest_platform:
        log.warning(f"Guest platform not detected for machine {machine_key!r} - skipping system info collection")
        return

    output_file = context.experiment_run_directory.system_info_file
    if multi_machine:
        # Distinct output files per machine -- the plain path would otherwise have
        # every machine overwrite the same system-info.yml.
        output_file = output_file.with_name(f"{output_file.stem}-{machine_key}{output_file.suffix}")

    # Use QGA-based collection in host test mode, WebSocket otherwise
    is_host_test_mode = context.test_execution_mode == 'host'

    if is_host_test_mode and view.vm:
        from adare.backend.experiment.system_info_collector import collect_system_info_via_qga

        success = await collect_system_info_via_qga(
            vm=view.vm, guest_platform=view.guest_platform, output_file=output_file
        )
    elif view.client:
        from adare.backend.experiment.system_info_collector import collect_system_info

        success = await collect_system_info(
            websocket_client=view.client, guest_platform=view.guest_platform, output_file=output_file
        )
    else:
        log.warning(
            f"Neither WebSocket client nor VM available for machine {machine_key!r} - skipping system info collection"
        )
        return

    if success:
        log.info(f"System information collected and saved to {output_file}")
    else:
        log.warning(f"System information collection failed for machine {machine_key!r} (experiment continues)")


def step_finalize(context: ExperimentRunCtx, post_interrupt: bool = False):
    event = None if post_interrupt else context.user_interrupt_event
    with StageCtxManager(FinalizeStage(), context.experiment_run_ulid, event=event):
        timestamp_end = datetime.now(UTC)
        experiment_database.update_experiment_run_end(
            context.project_directory.path, context.experiment_run_ulid, timestamp_end
        )

        # The run actually executed against this environment: register it as a
        # "can run here" indicator on the experiment (DB + metadata.yml). This is
        # best-effort and never breaks a completed run.
        experiment_database.register_experiment_environment(
            context.project_directory.path,
            context.config.experiment_name,
            context.config.environment_name,
        )

        duration_total = timestamp_end - context.timestamp_start
        duration_vm = timestamp_end - context.timestamp_before_vm_start
        log.info(
            f"Experiment run {context.experiment_run_ulid} finished after {duration_total} seconds (vm run time: {duration_vm})"
        )
        __cleanup_experiment_run(context.experiment_run_directory)


async def step_shutdown_mcp_server(context: ExperimentRunCtx, post_interrupt: bool = False, force: bool = False):
    """Stop the MCP GUI server(s) -- one per machine."""
    event = None if post_interrupt else context.user_interrupt_event
    with StageCtxManager(ShutdownComputerVisionServerStage(), context.experiment_run_ulid, event=event):
        for machine_ctx in context.machines.values():
            if machine_ctx.mcp_server is not None:
                log.info('stopping MCP GUI server')
                await machine_ctx.mcp_server.stop(force_external=force)


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
