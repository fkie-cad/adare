"""
Guest agent lifecycle management: readiness verification, installation, and startup.

Extracted from run.py to isolate VM agent interaction from the experiment orchestrator.
"""

import asyncio
import threading

# configure logging
import logging
log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Shared retry helper  (deduplicates 3 identical patterns from run.py)
# ---------------------------------------------------------------------------

async def _run_command_with_retry(
    vm,
    command: str,
    stop_event: threading.Event,
    *,
    admin: bool = False,
    max_retries: int = 3,
    initial_delay: float = 1.0,
    label: str = "command",
) -> "CommandResult":
    """Execute *command* on *vm* with exponential-backoff retry on transient failures.

    Retries only on guest-agent connectivity problems (returncode == -1) and
    ``asyncio.TimeoutError``.  Genuine command failures (non-zero, non -1
    return codes) are raised immediately.

    Returns the successful ``CommandResult`` on success.

    Raises:
        VMSetupError: after exhausting retries or on a real command failure.
    """
    from adare.backend.experiment.exceptions import VMSetupError

    retry_delay = initial_delay

    for attempt in range(max_retries):
        try:
            result = await vm.run_command(
                command,
                stop_event=stop_event,
                admin=admin,
            )

            if result.returncode == 0:
                return result

            if result.returncode == -1:
                # Guest agent not responding (transient)
                if attempt < max_retries - 1:
                    log.warning(
                        f"{label} attempt {attempt + 1}/{max_retries} failed "
                        f"(guest agent not responding), retrying in {retry_delay}s..."
                    )
                    await asyncio.sleep(retry_delay)
                    retry_delay *= 2
                else:
                    log.error(
                        f"Guest agent connectivity error (returncode -1): {result.stderr}"
                    )
                    raise VMSetupError(
                        log, vm.vm_name, command,
                        result.returncode, result.stdout, result.stderr,
                    )
            else:
                # Real command failure - fail fast
                log.error(
                    f"{label} failed with exit code {result.returncode}: {result.stderr}"
                )
                raise VMSetupError(
                    log, vm.vm_name, command,
                    result.returncode, result.stdout, result.stderr,
                )

        except asyncio.TimeoutError as e:
            if attempt < max_retries - 1:
                log.warning(
                    f"{label} attempt {attempt + 1}/{max_retries} timed out, "
                    f"retrying in {retry_delay}s..."
                )
                await asyncio.sleep(retry_delay)
                retry_delay *= 2
            else:
                raise VMSetupError(
                    log, vm.vm_name, command,
                    -1, "", f"Timeout after {max_retries} attempts: {e}",
                )

    # Should not be reachable, but satisfies the type checker
    raise VMSetupError(log, vm.vm_name, command, -1, "", "Unexpected retry loop exit")  # pragma: no cover


# ---------------------------------------------------------------------------
# Guest agent readiness verification
# ---------------------------------------------------------------------------

async def verify_guest_agent_readiness(
    vm,
    stop_event: threading.Event,
    max_retries: int = 5,
    initial_delay: float = 1.0,
) -> bool:
    """Verify guest agent is responsive before executing commands.

    Performs lightweight connectivity test with exponential backoff retry.
    This supplements the boot check by catching transient agent disconnections
    that occur shortly after boot completion.

    Returns True if agent is responsive, False if all retries exhausted or
    cancelled.
    """
    from adare.backend.experiment.exceptions import VMSetupError

    retry_delay = initial_delay

    for attempt in range(max_retries):
        if stop_event.is_set():
            log.warning("Guest agent readiness check cancelled by stop event")
            return False

        log.debug(f"Guest agent readiness check attempt {attempt + 1}/{max_retries}...")

        try:
            result = await vm.run_command(
                'echo ready',
                stop_event=stop_event,
                admin=False,
            )

            if result.returncode == 0:
                log.info(f"Guest agent readiness verified on attempt {attempt + 1}")
                return True

            if result.returncode == -1:
                if attempt < max_retries - 1:
                    log.warning(
                        f"Guest agent not responding (attempt {attempt + 1}/{max_retries}), "
                        f"retrying in {retry_delay}s..."
                    )
                    await asyncio.sleep(retry_delay)
                    retry_delay *= 2
                else:
                    log.error("Guest agent not responsive after all retry attempts")
                    return False
            else:
                error_msg = (
                    f"Unexpected error during readiness check "
                    f"(returncode {result.returncode}): {result.stderr}"
                )
                log.error(error_msg)
                raise VMSetupError(
                    log, vm.vm_name, "guest agent readiness check",
                    result.returncode, result.stdout, result.stderr,
                )

        except asyncio.TimeoutError:
            if attempt < max_retries - 1:
                log.warning(
                    f"Guest agent readiness check timed out (attempt {attempt + 1}/{max_retries}), "
                    f"retrying in {retry_delay}s..."
                )
                await asyncio.sleep(retry_delay)
                retry_delay *= 2
            else:
                log.error("Guest agent readiness check timed out after all retry attempts")
                return False

    return False


# ---------------------------------------------------------------------------
# Agent installation & startup
# ---------------------------------------------------------------------------

async def install_and_run_adare_vm(context, stop_event: threading.Event):
    """Install and run the adarevm agent in the VM.

    Uses the command builder pattern for platform-specific commands.
    The heavy lifting is delegated to ``_run_command_with_retry`` to avoid
    duplicated retry/backoff logic.
    """
    from .agent_command_builders import (
        detect_environment,
        WindowsAgentCommandBuilder,
        LinuxAgentCommandBuilder,
        CommandSet, EnvironmentInfo,
    )
    from adare.database.api.devmode import DevModeApi
    from adare.backend.experiment.exceptions import VMSetupError

    vm = context.vm
    wheels_dir = context.project_directory.vm_runtime / 'wheels'

    # Check for cached start command in database (dev mode restores)
    cached_command_str = None
    if context.experiment_run_ulid:
        try:
            with DevModeApi() as api:
                session = api.get_session(context.experiment_run_ulid)
                if session and session.cached_start_command:
                    cached_command_str = session.cached_start_command
                    log.info("Using cached adarevm start command from database (skipping detection/install)")
        except Exception as e:
            log.warning(f"Failed to check for cached start command: {e}")

    commands = None
    env_info = None

    if cached_command_str:
        # Use cached command - bypass detection logic
        platform = context.guest_platform or 'windows'

        commands = CommandSet(
            setup_commands=[],
            install_command="",
            run_command=cached_command_str,
            run_cwd=None,
            skip_installation=True,
        )

        env_info = EnvironmentInfo(
            use_conda=False, conda_env_exists=False, miniforge_path=None, platform=platform,
        )

        # Shared folder mounting (needed after restore)
        if context.guest_platform == 'windows':
            shared_folders = {
                name: paths['vm']
                for name, paths in context.config.shared_directories.items()
                if paths.get('vm')
            }
            if shared_folders:
                pass  # Agent readiness is verified below before any commands

    else:
        # Step 1: Detect Python environment
        env_info = await detect_environment(vm, context.guest_platform, stop_event)

        # Step 1.5: Determine GUI mode
        from .execution.gui_executor_factory import resolve_gui_execution_mode
        from .execution.base import GUIExecutionMode

        playbook_settings = (
            context.playbook.settings
            if hasattr(context, 'playbook') and context.playbook
            else None
        )
        cli_override = (
            context.config.gui_mode_override
            if hasattr(context.config, 'gui_mode_override')
            else None
        )

        gui_mode = resolve_gui_execution_mode(vm, playbook_settings, cli_override=cli_override)
        skip_xhost = gui_mode == GUIExecutionMode.HOST

        vm.adare_gui_mode = gui_mode

        if skip_xhost:
            log.info("Skipping xhost setup - using host-based GUI automation")

        # Step 2: Create platform-specific command builder
        builder_kwargs = dict(
            wheels_dir=wheels_dir,
            shared_folders=context.config.shared_directories,
            websocket_port=context.config.websocket_port,
            skip_xhost=skip_xhost,
            hypervisor_type=context.hypervisor_type or 'virtualbox',
            installation_mode=context.config.installation_mode,
        )

        if context.guest_platform == 'windows':
            builder = WindowsAgentCommandBuilder(**builder_kwargs)
        else:
            builder = LinuxAgentCommandBuilder(**builder_kwargs)

        # Step 3: Discover guest PATH
        await vm._discover_guest_path()

        # Step 4: Build all commands
        commands = await builder.build_commands(env_info, vm, stop_event)

    # ---- Common path: Verification & Execution ----

    log.info("Verifying guest agent readiness...")
    if not await verify_guest_agent_readiness(vm, stop_event, max_retries=8):
        raise VMSetupError(
            log, vm.vm_name, "pre-flight guest agent check",
            -1, "", "Guest agent not responsive after boot validation",
        )
    log.info("Guest agent verification successful")

    # Execute setup commands
    for idx, setup_cmd in enumerate(commands.setup_commands):
        await _run_command_with_retry(
            vm, setup_cmd.command, stop_event,
            admin=setup_cmd.requires_admin,
            label=f"Setup command [{idx + 1}/{len(commands.setup_commands)}]",
        )

    # Mount shared folders (Windows only)
    if context.guest_platform == 'windows':
        shared_folders = {
            name: paths['vm']
            for name, paths in context.config.shared_directories.items()
            if paths.get('vm')
        }
        if shared_folders:
            await vm.mount_multiple_shared_folders(
                folders=shared_folders,
                stop_event=stop_event,
            )

    # Install adarevm if needed
    if not commands.skip_installation:
        log.info("Installing adarevm")
        await _run_command_with_retry(
            vm, commands.install_command, stop_event,
            admin=False,
            label="Installation",
        )
    else:
        log.info("Installation skipped")

    # Run adarevm as background process
    if context.guest_platform == 'linux':
        result = await vm.run_command(
            commands.run_command,
            background=True,
            stop_event=stop_event,
            admin=True if env_info.use_conda else False,
            cwd=commands.run_cwd,
        )
    else:
        log_path = r'C:\adare\run\logs'
        result = await vm.run_command(
            commands.run_command,
            cwd=commands.run_cwd,
            admin=True,
            run_as_user=True,
            stop_event=stop_event,
            redirect_stdout=rf'{log_path}\adarevm_stdout.log',
            redirect_stderr=rf'{log_path}\adarevm_stderr.log',
        )

    if result.returncode != 0:
        log.error(f"Failed to start adarevm: {result.stderr}")
        raise VMSetupError(
            log, vm.vm_name, commands.run_command,
            result.returncode, result.stdout, result.stderr,
        )

    # Store PID for QEMU process monitoring
    if context.hypervisor_type == 'qemu' and result.returncode == 0:
        try:
            import re
            match = re.search(r'PID (\d+)', result.stdout)
            if match:
                context.adarevm_pid = int(match.group(1))
                log.debug(f"Stored adarevm process PID: {context.adarevm_pid}")
            else:
                if context.guest_platform == 'windows':
                    log.debug(
                        "Could not extract PID from background process start "
                        "(expected on Windows/schtasks)"
                    )
                else:
                    log.warning("Could not extract PID from background process start")
                context.adarevm_pid = None
        except (AttributeError, ValueError) as e:
            log.warning(f"Failed to parse adarevm PID: {e}")
            context.adarevm_pid = None

    # Cache the start command
    if not cached_command_str and context.experiment_run_ulid:
        command_to_cache = commands.run_command
        if commands.run_cwd:
            if "cd " not in command_to_cache:
                if context.guest_platform == 'windows':
                    command_to_cache = f"cd /d {commands.run_cwd} & {command_to_cache}"
                else:
                    command_to_cache = f"cd {commands.run_cwd} && {command_to_cache}"

        try:
            with DevModeApi() as api:
                api.update_session_cached_command(context.experiment_run_ulid, command_to_cache)
                log.info("Cached adarevm start command to database")
        except Exception as e:
            log.warning(f"Failed to cache command to DB: {e}")


# ---------------------------------------------------------------------------
# WebSocket connection
# ---------------------------------------------------------------------------

async def connect_websocket(context, stage_ctx):
    """Establish WebSocket connection to the adarevm agent with retries.

    Args:
        context: ExperimentRunCtx
        stage_ctx: StageCtxManager context for progress reporting
    """
    from adare.backend.experiment.websocket_client import AdareVMClient
    from adare.exceptions import LoggedException
    from websockets.exceptions import ConnectionClosed, WebSocketException

    # Validate websocket port is set
    if not context.config.websocket_port:
        error_msg = "WebSocket port not configured in context - cannot establish connection"
        log.error(error_msg)
        raise LoggedException(log, error_msg)

    # QEMU-specific: Check if adarevm process is still alive before attempting connection
    if context.hypervisor_type == 'qemu' and hasattr(context, 'adarevm_pid') and context.adarevm_pid:
        log.debug(f"Checking if adarevm process (PID {context.adarevm_pid}) is still running...")

        try:
            is_running, exit_code, error_msg = await context.vm._check_process_status_via_agent(
                context.adarevm_pid,
                timeout=5
            )

            if not is_running:
                if exit_code is not None:
                    error = f"adarevm process (PID {context.adarevm_pid}) has already exited with code {exit_code}. Check logs for startup errors."
                else:
                    error = f"adarevm process (PID {context.adarevm_pid}) is not running. {error_msg}"

                log.error(f"{error}")
                raise LoggedException(log, error)
            else:
                log.debug(f"adarevm process is alive, proceeding with connection attempts")
        except LoggedException:
            raise
        except Exception as e:
            log.warning(f"Could not verify adarevm process status: {e}")

    # Create websocket client with host port forwarding
    context.client = AdareVMClient(host='localhost', port=context.config.websocket_port)

    # Set up event handlers for logging
    def log_event_handler(event_type: str, data: dict):
        message = data.get('message', '')
        log.info(f"AdareVM Event [{event_type}]: {message}")

    def error_event_handler(event_type: str, data: dict):
        error = data.get('error', '')
        log.error(f"AdareVM Error: {error}")

    context.client.add_event_handler('log', log_event_handler)
    context.client.add_event_handler('error', error_event_handler)

    # Retry delays: 2, 3, 5, 7, 10 seconds (increased initial delay)
    retry_delays = [2, 3, 5, 7, 10]
    max_attempts = len(retry_delays) + 1  # +1 for the initial attempt

    last_error = None
    for attempt in range(1, max_attempts + 1):
        if context.stop_event.is_set():
            log.info("Connection cancelled by stop event")
            return

        # Update stage message to show retry attempt
        if attempt == 1:
            stage_ctx.stage.sub_msg = "Attempting connection..."
        else:
            stage_ctx.stage.sub_msg = f"Retrying connection (attempt {attempt}/{max_attempts})"
        stage_ctx.set_status(stage_ctx.stage.status)

        try:
            log.info(f"Attempting to connect to AdareVM server (attempt {attempt}/{max_attempts})")
            connected = await context.client.connect(timeout=60.0)

            if connected:
                stage_ctx.stage.sub_msg = ""
                stage_ctx.set_status(stage_ctx.stage.status)
                log.info("Successfully connected to AdareVM WebSocket server")

                # Test the connection with ping
                ping_success = await context.client.ping()
                if ping_success:
                    log.info("Ping test successful - WebSocket connection is working")
                else:
                    log.warning("Ping test failed but connection established")

                # Get server status
                try:
                    status = await context.client.get_status()
                    log.info(f"AdareVM server status: {status}")
                except (asyncio.TimeoutError, ConnectionClosed) as e:
                    log.warning(f"Could not get server status: {e}")

                return  # Success
            else:
                raise ConnectionRefusedError("Failed to establish websocket connection")

        except (asyncio.TimeoutError, ConnectionClosed, WebSocketException, ConnectionRefusedError, OSError) as e:
            last_error = e
            log.warning(f"Connection attempt {attempt}/{max_attempts} failed: {e}")

            if attempt < max_attempts:
                delay = retry_delays[attempt - 1]
                stage_ctx.stage.sub_msg = f"Attempt {attempt} failed, retrying in {delay}s..."
                stage_ctx.set_status(stage_ctx.stage.status)

                log.info(f"Retrying in {delay} seconds...")
                await asyncio.sleep(delay)

    # All attempts failed
    stage_ctx.stage.sub_msg = f"All {max_attempts} connection attempts failed"
    stage_ctx.set_status(stage_ctx.stage.status)
    log.error(last_error, exc_info=True)
    raise LoggedException(log, f"Failed to connect to AdareVM server after {max_attempts} attempts: {last_error}") from last_error


# ---------------------------------------------------------------------------
# Installation execution helpers
# ---------------------------------------------------------------------------

async def execute_installations_via_websocket(context, stage_ctx):
    """Execute environment installations via WebSocket client.

    Args:
        context: ExperimentRunCtx
        stage_ctx: StageCtxManager context for progress reporting
    """
    import adare.backend.environment.database as environment_database

    installations = environment_database.get_environment_installations(context.environment_ulid)

    if not installations:
        log.info("No installations to execute")
        return

    log.info(f"Executing {len(installations)} installation(s) from environment")

    for idx, installation in enumerate(installations, 1):
        installation_name = installation.name if hasattr(installation, 'name') else f"Installation {idx}"
        installation_cmd = installation.command if hasattr(installation, 'command') else str(installation)
        installation_desc = installation.description if hasattr(installation, 'description') else ""

        stage_ctx.stage.sub_msg = f"[{idx}/{len(installations)}] {installation_name}"
        stage_ctx.set_status(stage_ctx.stage.status)

        log.info(f"Executing installation [{idx}/{len(installations)}]: {installation_name}")
        if installation_desc:
            log.info(f"Description: {installation_desc}")
        log.info(f"Command: {installation_cmd}")

        try:
            result = await context.client.execute_shell(
                installation_cmd,
                shell=True,
                timeout=600  # 10 minute timeout for installations
            )

            if result.get('returncode') == 0:
                log.info(f"Installation '{installation_name}' completed successfully")
                if result.get('stdout'):
                    log.debug(f"Installation output: {result['stdout']}")
            else:
                log.error(f"Installation '{installation_name}' failed with return code {result.get('returncode')}")
                if result.get('stderr'):
                    log.error(f"Installation error: {result['stderr']}")
                if result.get('stdout'):
                    log.error(f"Installation output: {result['stdout']}")
                log.warning("Continuing with remaining installations despite failure")

        except Exception as e:
            log.error(f"Failed to execute installation '{installation_name}': {e}", exc_info=True)
            log.warning("Continuing with remaining installations despite error")

    log.info("All installations completed")


async def execute_installations_via_qga(context, stage_ctx):
    """Execute environment installations via QGA guest-exec (no WebSocket needed).

    Args:
        context: ExperimentRunCtx
        stage_ctx: StageCtxManager context for progress reporting
    """
    import adare.backend.environment.database as environment_database

    installations = environment_database.get_environment_installations(context.environment_ulid)

    if not installations:
        log.info("No installations to execute")
        return

    log.info(f"Executing {len(installations)} installation(s) via QGA guest-exec")

    for idx, installation in enumerate(installations, 1):
        installation_name = installation.name if hasattr(installation, 'name') else f"Installation {idx}"
        installation_cmd = installation.command if hasattr(installation, 'command') else str(installation)
        installation_desc = installation.description if hasattr(installation, 'description') else ""

        stage_ctx.stage.sub_msg = f"[{idx}/{len(installations)}] {installation_name}"
        stage_ctx.set_status(stage_ctx.stage.status)

        log.info(f"Executing installation [{idx}/{len(installations)}]: {installation_name}")
        if installation_desc:
            log.info(f"Description: {installation_desc}")
        log.info(f"Command: {installation_cmd}")

        try:
            result = await context.vm.run_command(installation_cmd, silent=False)

            if result.returncode == 0:
                log.info(f"Installation '{installation_name}' completed successfully")
                if result.stdout:
                    log.debug(f"Installation output: {result.stdout}")
            else:
                log.error(f"Installation '{installation_name}' failed with return code {result.returncode}")
                if result.stderr:
                    log.error(f"Installation error: {result.stderr}")
                if result.stdout:
                    log.error(f"Installation output: {result.stdout}")
                log.warning("Continuing with remaining installations despite failure")

        except Exception as e:
            log.error(f"Failed to execute installation '{installation_name}': {e}", exc_info=True)
            log.warning("Continuing with remaining installations despite error")

    log.info("All installations completed")
