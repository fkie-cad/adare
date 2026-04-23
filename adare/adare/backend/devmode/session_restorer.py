"""
Session restoration logic for dev mode.

This module handles the complex task of restoring a DevModeSession from
database metadata when the session object is not in memory but the VM
is still running.
"""

import logging
from datetime import datetime
from pathlib import Path

from adare.backend.devmode.session import DevModeSession, DevModeSnapshot
from adare.backend.experiment.directory import ExperimentDirectory, ExperimentRunDirectory
from adare.backend.experiment.playbook_controller import PlaybookController
from adare.backend.experiment.runctx import ExperimentConfig, ExperimentRunCtx
from adare.backend.experiment.vm_lifecycle_manager import VMLifecycleManager
from adare.backend.project.directory import ProjectDirectory
from adare.config.configdirectory import ADARELIB_DIR, ADAREVM_DIR
from adare.database.exceptions import DatabaseError
from adare.database.models.devsession import DevSession

log = logging.getLogger(__name__)


async def restore_infrastructure_context(
    session: DevModeSession,
    db_session: DevSession
) -> bool:
    """
    Restore underlying infrastructure context (VM, directories, config).

    This loads enough context to manage the VM lifecycle (stop/destroy)
    and clean up files, but does NOT load application logic (playbooks,
    websockets, etc).

    Args:
        session: DevModeSession object to populate
        db_session: Database record with session metadata

    Returns:
        True if infrastructure restored successfully, False otherwise
    """
    try:
        log.info(f"Restoring infrastructure context for session {session.session_id}")

        # 1. Recreate ExperimentConfig from database metadata
        config = ExperimentConfig(
            project_path=Path(db_session.project_path),
            experiment_name=db_session.experiment_name,
            environment_name=db_session.environment_name,
            test_mode=True,
            preserve_snapshot=True,
            runlog=True,
            disable_printing=True,
            gui_mode_override=session.gui_mode,
            vm_memory=session.vm_memory or 4096,
            vm_cpus=session.vm_cpus or 4
        )

        # 2. Initialize ExperimentRunCtx (fake mode - no new VM creation)

        # Create context
        session.experiment_ctx = ExperimentRunCtx(config=config)
        session.experiment_ctx.test_mode = True
        session.experiment_ctx.debug_screenshots = session.debug_screenshots

        # Initialize with fake=True (no database entry creation)
        # But we need to manually set the experiment_run_ulid for proper functioning
        # We use session_id directly as the experiment run ID (aligned with session.py)
        session.experiment_ctx.experiment_run_ulid = session.session_id
        session.experiment_ctx.timestamp_start = datetime.now()
        session.experiment_ctx.timestamp_before_vm_start = datetime.now()
        session.experiment_ctx.adarevm = ADAREVM_DIR
        session.experiment_ctx.adarelib = ADARELIB_DIR

        log.debug(f"Recreated ExperimentRunCtx with ulid: {session.experiment_ctx.experiment_run_ulid}")

        # 3. Setup directories
        session.experiment_ctx.project_directory = ProjectDirectory(config.project_path)
        session.experiment_ctx.experiment_directory = ExperimentDirectory(
            config.project_path,
            config.experiment_name
        )

        # 4. Get environment metadata
        from adare.backend.environment import database as environment_database
        from adare.backend.environment.exceptions import EnvironmentDoesNotExistInDatabase

        try:
            environment_ulid = environment_database.resolve_environment_identifier(
                config.environment_name
            )

            session.experiment_ctx.environment_ulid = environment_ulid
            session.experiment_ctx.guest_platform = environment_database.get_environment_os(environment_ulid)
            session.experiment_ctx.hypervisor_type = environment_database.get_environment_hypervisor(environment_ulid)
            session.experiment_ctx.environment_file = environment_database.get_environment_path_by_project_and_name(
                config.project_path,
                config.environment_name
            )

            # CRITICAL: Restore overlay path from database, not base disk path
            # This prevents accidental base disk deletion during cleanup
            if db_session.overlay_disk_path:
                session.experiment_ctx.vm_file = Path(db_session.overlay_disk_path)
                log.debug(f"Restored overlay disk path: {db_session.overlay_disk_path}")
            else:
                # Fallback for old sessions without overlay_disk_path (unsafe!)
                log.warning(
                    f"Session {session.session_id} missing overlay_disk_path field. "
                    f"Using base disk as fallback (UNSAFE - base disk may be deleted!)"
                )
                session.experiment_ctx.vm_file = environment_database.get_environment_vm_file(environment_ulid)

        except EnvironmentDoesNotExistInDatabase as e:
            log.error(f"Environment not found: {e}")
            return False

        # 5. Reconnect to existing VM
        # Create VM object that attaches to existing VM (not create new one)
        hypervisor = session.experiment_ctx.hypervisor_type
        vm_name = db_session.vm_name

        if hypervisor == 'qemu':
            from adare.config import get_vm_credentials
            from adare.hypervisor.qemu.manager import QEMUManager
            from adare.hypervisor.qemu.vm import QEMUVM

            # Create QEMU manager
            qemu_manager = QEMUManager()

            # Get VM credentials
            username, password = get_vm_credentials(session.experiment_ctx.guest_platform)

            # Create VM object (config auto-loaded from ~/.adare/qemu/vms/{vm_name}.json)
            # disk_path points to the OVERLAY disk (not base disk) thanks to restoration above
            session.experiment_ctx.vm = QEMUVM(
                vm_name=vm_name,
                guest_os=session.experiment_ctx.guest_platform,
                manager=qemu_manager,
                username=username,
                password=password,
                executables=qemu_manager.executables,
                disk_path=str(session.experiment_ctx.vm_file) if session.experiment_ctx.vm_file else None
            )

            log.debug(f"Attached to existing QEMU VM: {vm_name}")

        elif hypervisor == 'virtualbox':
            from adare.hypervisor.virtualbox.vm import VirtualBoxVM

            # Create VM object with existing name
            session.experiment_ctx.vm = VirtualBoxVM(
                name=vm_name,
                disk_path=session.experiment_ctx.vm_file,
                base_snapshot_name=None  # Will query from VM
            )

            log.debug(f"Attached to existing VirtualBox VM: {vm_name}")

        else:
            log.error(f"Unknown hypervisor type: {hypervisor}")
            return False

        session.experiment_ctx.vm_name = vm_name

        # Restore websocket_port from VM instance database
        from adare.database.api.vm import VmApi
        try:
            with VmApi() as vm_api:
                vm_instance = vm_api.get_vm_instance_by_name(vm_name)
                if vm_instance and vm_instance.websocket_port:
                    session.experiment_ctx.config.websocket_port = vm_instance.websocket_port
                else:
                    log.warning(f"Could not restore websocket_port for VM instance {vm_name}")
        except (ImportError, DatabaseError, OSError, AttributeError) as e:
            log.warning(f"Failed to restore websocket_port from database: {e}")

        # 6. Recreate VMLifecycleManager
        session.vm_manager = VMLifecycleManager(hypervisor_type=hypervisor)

        # 7. Setup experiment run directory structure (for file ops)
        # Try to restore from stored path first (prevents "None" directories)
        if db_session.run_directory_path:
            stored_path = Path(db_session.run_directory_path)

            # Verify the directory still exists
            if stored_path.exists():
                log.info(f"Restoring run directory from stored path: {stored_path}")

                # Reconstruct ExperimentRunDirectory using the stored path
                # We need to create an instance that points to the existing directory
                run_dir = ExperimentRunDirectory.__new__(ExperimentRunDirectory)
                run_dir.path = stored_path
                run_dir.log_directory = stored_path / 'logs'
                run_dir.screenshots_directory = stored_path / 'reporting' / 'screenshots'
                run_dir.mcp_gui_log_file = stored_path / 'logs' / 'mcp_gui.log'

                session.experiment_ctx.experiment_run_directory = run_dir
                session.run_directory_path = stored_path

                log.info(f"Successfully restored run directory: {stored_path}")
            else:
                log.warning(f"Stored run directory does not exist: {stored_path}, falling back to recreation")
                # Fall through to recreation logic below

        # Fallback: Recreate run directory if no stored path or path doesn't exist
        if not hasattr(session.experiment_ctx, 'experiment_run_directory') or session.experiment_ctx.experiment_run_directory is None:
            log.info("Creating new run directory (fallback)")

            # Ensure experiment_name is never None
            experiment_name = session.experiment_ctx.config.experiment_name or "_dev_session"

            run_dir = ExperimentRunDirectory(
                session.experiment_ctx.project_directory,
                experiment_name
            )
            run_dir.create()
            session.experiment_ctx.experiment_run_directory = run_dir
            session.run_directory_path = run_dir.path

        log.debug("Infrastructure context restored (VM, directories, config)")

        # 8. Query and restore snapshots from hypervisor (needed for file cleanup)
        await _restore_snapshots(session)

        return True

    except Exception as e:  # Intentionally broad: infrastructure restoration must not crash caller
        log.error(f"Failed to restore infrastructure context: {e}", exc_info=True)
        return False


async def restore_application_context(
    session: DevModeSession,
    console_ulid: str | None = None,
    should_start_vm: bool = False
) -> bool:
    """
    Restore application-layer context (playbooks, controllers, WebSocket).

    This loads the "logic" part of the session. It requires infrastructure
    context to be loaded first.

    Args:
        session: DevModeSession object (already has infrastructure loaded)
        console_ulid: Optional console ULID for flow integration
        should_start_vm: If True, start the VM and reconnect WebSocket.

    Returns:
        True if application context restored successfully, False otherwise
    """
    if not session.experiment_ctx:
        log.error("Infrastructure context not loaded - cannot restore application context")
        return False

    try:
        log.info(f"Restoring application context for session {session.session_id}")

        # 1. Load playbook from filesystem
        playbook_path = session.experiment_ctx.experiment_directory.playbookfile
        if playbook_path.exists():
            from adare.types.playbook import parse_playbook
            session.experiment_ctx.playbook = parse_playbook(playbook_path)
            log.debug(f"Loaded playbook from {playbook_path}")
        else:
            log.debug(f"No playbook found at {playbook_path}, continuing without loaded playbook")
            session.experiment_ctx.playbook = None

        # 2. Initialize and start MCP server for target resolution (non-fatal)
        try:
            from adare.backend.experiment.mcp_server_manager import MCPServerManager
            from adare.backend.experiment.run import step_start_mcp_server

            # Initialize MCP server object
            session.experiment_ctx.mcp_server = MCPServerManager(
                log_file=session.experiment_ctx.experiment_run_directory.mcp_gui_log_file
            )

            # Start the server
            await step_start_mcp_server(session.experiment_ctx)
            log.debug("MCP server started successfully")

        except (ImportError, OSError, RuntimeError, ConnectionError) as e:
            log.warning(
                f"Failed to start MCP server: {e}. "
                f"Target resolution will not be available, but session can still be used."
            )
            session.experiment_ctx.mcp_server = None

        # 3. Recreate PlaybookController
        from adare.config import get_vm_credentials

        vm_os = session.experiment_ctx.guest_platform
        vm_user = None
        if vm_os:
            vm_user, _ = get_vm_credentials(vm_os)

        # WebSocket client will be None initially
        session.playbook_controller = PlaybookController(
            websocket_client=None,
            experiment_dir=session.experiment_ctx.experiment_directory.path,
            project_dir=session.experiment_ctx.project_directory.path,
            debug_screenshots=True,
            screenshots_dir=session.experiment_ctx.experiment_run_directory.screenshots_directory,
            playbook=session.experiment_ctx.playbook,
            experiment_run_id=console_ulid or session.console_ulid or session.experiment_ctx.experiment_run_ulid,
            vm=session.experiment_ctx.vm,
            experiment_run_directory=session.experiment_ctx.experiment_run_directory.path,
            vm_os=vm_os,
            vm_user=vm_user,
            test_mode=True,
            config=session.experiment_ctx.config
        )

        log.debug("Recreated PlaybookController")

        # 4. Restore initial variables
        if session.experiment_ctx.playbook and session.experiment_ctx.playbook.variables:
            session.initial_variables = session.playbook_controller.execution_context.copy()

        # 5. Start VM and reconnect WebSocket if requested
        if should_start_vm:
            log.info("Starting VM for stopped session resumption...")

            # Force QEMU_LIBGUESTFS=true for dev mode
            import os
            os.environ['QEMU_LIBGUESTFS'] = 'true'

            # Import required step functions
            from adare.backend.events.emitters import StageCtxManager
            from adare.backend.events.stages import (
                SoftwareInstallationStage,
                VirtualMachineSetupStage,
            )
            from adare.backend.experiment.run import (
                step_connect_websocket,
                step_install_and_run_websocket_server,
            )

            stage_ulid = console_ulid or session.experiment_ctx.experiment_run_ulid

            try:
                # Start VM
                with StageCtxManager(
                    VirtualMachineSetupStage(),
                    stage_ulid,
                    event=session.experiment_ctx.user_interrupt_event
                ):
                    await session.vm_manager.start_vm(session.experiment_ctx)
                    log.info("VM started successfully")

                # Install WebSocket server and connect
                with StageCtxManager(
                    SoftwareInstallationStage(),
                    stage_ulid,
                    event=session.experiment_ctx.user_interrupt_event
                ):
                    await step_install_and_run_websocket_server(session.experiment_ctx)
                    log.info("AdareVM WebSocket server installed")

                    await step_connect_websocket(session.experiment_ctx)
                    log.info("Connected to WebSocket")

                # Update playbook controller with WebSocket client
                session.playbook_controller.update_websocket_client(session.experiment_ctx.client)

            except Exception as e:
                log.error(f"Failed to start VM and reconnect WebSocket: {e}", exc_info=True)
                return False

        # 6. Mark session as running
        session.is_running = True

        # Restore original start time from DB if possible (need to pass db_session probably,
        # or just set current time if re-running)
        # Assuming caller tracks this, or we just set it to now if not available
        if not session.started_at:
             session.started_at = datetime.now()

        log.info(f"Successfully restored dev session application context {session.session_id}")
        return True

    except Exception as e:  # Intentionally broad: application restoration must not crash caller
        log.error(f"Failed to restore application context: {e}", exc_info=True)
        return False


async def restore_context(
    session: DevModeSession,
    db_session: DevSession,
    console_ulid: str | None = None,
    should_start_vm: bool = False
) -> bool:
    """
    Restore complete session context (infrastructure + application).

    This function recreates all the internal state needed for a DevModeSession
    to function efficiently.

    Args:
        session: DevModeSession object to populate
        db_session: Database record with session metadata
        console_ulid: Optional console ULID for flow integration
        should_start_vm: If True, start the VM and reconnect WebSocket after restoration.

    Returns:
        True if restoration successful, False otherwise
    """
    # 1. Restore infrastructure (VM, files, config)
    if not await restore_infrastructure_context(session, db_session):
        return False

    # 2. Restore application (playbook, websocket, logic)
    return await restore_application_context(session, console_ulid, should_start_vm)


async def _restore_snapshots(session: DevModeSession) -> None:
    """
    Load checkpoints from database and verify snapshot files exist.

    Args:
        session: DevModeSession to populate with snapshot metadata
    """
    try:
        import os

        from adare.database.api.devmode import DevModeApi

        log.debug(f"Loading checkpoints from database for session {session.session_id}")

        # Load checkpoints from database
        with DevModeApi() as api:
            checkpoints = api.list_checkpoints(session.session_id)

        if not checkpoints:
            log.debug("No checkpoints found in database")
            return

        # Convert database checkpoints to DevModeSnapshot objects
        for checkpoint in checkpoints:
            # Verify snapshot files exist (for QEMU external snapshots)
            files_exist = True
            if session.experiment_ctx.hypervisor_type == 'qemu':
                if checkpoint.memory_file_path and not os.path.exists(checkpoint.memory_file_path):
                    log.warning(f"Memory file missing for checkpoint '{checkpoint.name}': {checkpoint.memory_file_path}")
                    files_exist = False
                if checkpoint.disk_file_path and not os.path.exists(checkpoint.disk_file_path):
                    log.warning(f"Disk file missing for checkpoint '{checkpoint.name}': {checkpoint.disk_file_path}")
                    files_exist = False

            if not files_exist:
                log.warning(f"Skipping checkpoint '{checkpoint.name}' due to missing files")
                continue

            # Create DevModeSnapshot from database checkpoint
            snapshot = DevModeSnapshot(
                snapshot_name=checkpoint.snapshot_name,
                created_at=checkpoint.created_at,
                variable_state=checkpoint.variable_state or {},
                description=checkpoint.description or "",
                memory_file_path=checkpoint.memory_file_path,
                disk_file_path=checkpoint.disk_file_path,
                checkpoint_id=checkpoint.checkpoint_id
            )
            session.snapshots.append(snapshot)

        log.info(f"Restored {len(session.snapshots)} checkpoints from database")

    except (OSError, DatabaseError, KeyError, AttributeError) as e:
        log.warning(f"Failed to restore checkpoints from database: {e}", exc_info=True)
        # Non-fatal - session can work without checkpoint metadata
