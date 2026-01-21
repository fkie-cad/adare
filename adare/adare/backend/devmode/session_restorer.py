"""
Session restoration logic for dev mode.

This module handles the complex task of restoring a DevModeSession from
database metadata when the session object is not in memory but the VM
is still running.
"""

import logging
from pathlib import Path
from typing import Optional
from datetime import datetime

from adare.backend.devmode.session import DevModeSession, DevModeSnapshot
from adare.backend.experiment.runctx import ExperimentRunCtx, ExperimentConfig
from adare.backend.experiment.vm_lifecycle_manager import VMLifecycleManager
from adare.backend.experiment.playbook_controller import PlaybookController
from adare.backend.experiment.directory import ExperimentDirectory, ExperimentRunDirectory
from adare.backend.project.directory import ProjectDirectory
from adare.database.models.devsession import DevSession
from adare.config.configdirectory import ADAREVM_DIR, ADARELIB_DIR
from adare.types.playbook import Playbook

log = logging.getLogger(__name__)


async def restore_context(
    session: DevModeSession,
    db_session: DevSession,
    console_ulid: Optional[str] = None
) -> bool:
    """
    Restore session context from database metadata and filesystem.

    This function recreates all the internal state needed for a DevModeSession
    to function without creating a new VM - it reconnects to the existing one.

    Args:
        session: DevModeSession object to populate
        db_session: Database record with session metadata
        console_ulid: Optional console ULID for flow integration

    Returns:
        True if restoration successful, False otherwise
    """
    try:
        log.info(f"Restoring dev session context for {session.session_id}")

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
        from adare.backend.experiment import database as experiment_database

        # Create context
        session.experiment_ctx = ExperimentRunCtx(config=config)
        session.experiment_ctx.test_mode = True
        session.experiment_ctx.debug_screenshots = session.debug_screenshots

        # Initialize with fake=True (no database entry creation)
        # But we need to manually set the experiment_run_ulid for proper functioning
        session.experiment_ctx.experiment_run_ulid = f"devmode_{session.session_id}"
        session.experiment_ctx.timestamp_start = datetime.now()
        session.experiment_ctx.timestamp_before_vm_start = datetime.now()
        session.experiment_ctx.adarevm = ADAREVM_DIR
        session.experiment_ctx.adarelib = ADARELIB_DIR

        log.debug(f"Recreated ExperimentRunCtx with ulid: {session.experiment_ctx.experiment_run_ulid}")

        # 3. Setup directories and load playbook from filesystem
        session.experiment_ctx.project_directory = ProjectDirectory(config.project_path)
        session.experiment_ctx.experiment_directory = ExperimentDirectory(
            config.project_path,
            config.experiment_name
        )

        # Load playbook from filesystem
        playbook_path = session.experiment_ctx.experiment_directory.playbookfile
        if not playbook_path.exists():
            log.error(f"Playbook file not found: {playbook_path}")
            return False

        from adare.types.playbook import parse_playbook
        session.experiment_ctx.playbook = parse_playbook(playbook_path)

        log.debug(f"Loaded playbook from {playbook_path}")

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
            session.experiment_ctx.vm_file = environment_database.get_environment_vm_file(environment_ulid)

            log.debug(
                f"Environment: platform={session.experiment_ctx.guest_platform}, "
                f"hypervisor={session.experiment_ctx.hypervisor_type}"
            )

        except EnvironmentDoesNotExistInDatabase as e:
            log.error(f"Environment not found: {e}")
            return False

        # 5. Reconnect to existing VM
        # Create VM object that attaches to existing VM (not create new one)
        hypervisor = session.experiment_ctx.hypervisor_type
        vm_name = db_session.vm_name

        if hypervisor == 'qemu':
            from adare.hypervisor.qemu.vm import QEMUVM
            from adare.hypervisor.qemu.manager import QEMUManager
            from adare.config import get_vm_credentials

            # Create QEMU manager
            qemu_manager = QEMUManager()

            # Get VM credentials
            username, password = get_vm_credentials(session.experiment_ctx.guest_platform)

            # Create VM object (config auto-loaded from ~/.adare/qemu/vms/{vm_name}.json)
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
                    log.debug(f"Restored websocket_port: {vm_instance.websocket_port}")
                else:
                    log.warning(f"Could not restore websocket_port for VM instance {vm_name}")
        except Exception as e:
            log.warning(f"Failed to restore websocket_port from database: {e}")

        # 6. Recreate VMLifecycleManager
        session.vm_manager = VMLifecycleManager(hypervisor_type=hypervisor)
        log.debug("Recreated VMLifecycleManager")

        # 7. Setup experiment run directory structure
        # Create run directory for file operations
        from adare.backend.experiment.directory import ExperimentRunDirectory

        # Create run directory using project directory and experiment name
        run_dir = ExperimentRunDirectory(
            session.experiment_ctx.project_directory,
            session.experiment_ctx.config.experiment_name
        )
        run_dir.create()
        session.experiment_ctx.experiment_run_directory = run_dir

        log.debug(f"Created run directory: {run_dir.path}")

        # 8. Initialize and start MCP server for target resolution (non-fatal)
        try:
            from adare.backend.experiment.run import step_start_mcp_server
            from adare.backend.experiment.execution.mcp_server_manager import MCPServerManager

            # Initialize MCP server object (required before calling step_start_mcp_server)
            session.experiment_ctx.mcp_server = MCPServerManager(
                log_file=run_dir.mcp_gui_log_file
            )

            # Start the server
            await step_start_mcp_server(session.experiment_ctx)
            log.debug("MCP server started successfully")

        except Exception as e:
            log.warning(
                f"Failed to start MCP server: {e}. "
                f"Target resolution will not be available, but session can still be used."
            )
            # MCP server failure is non-fatal - session can work without it
            session.experiment_ctx.mcp_server = None

        # 9. Recreate PlaybookController
        from adare.config import get_vm_credentials

        vm_os = session.experiment_ctx.guest_platform
        vm_user = None
        if vm_os:
            vm_user, _ = get_vm_credentials(vm_os)

        # Note: WebSocket client will be None initially - will try to reconnect separately
        session.playbook_controller = PlaybookController(
            websocket_client=None,  # Will be set after WebSocket reconnection
            experiment_dir=session.experiment_ctx.experiment_directory.path,
            project_dir=session.experiment_ctx.project_directory.path,
            debug_screenshots=True,
            screenshots_dir=session.experiment_ctx.experiment_run_directory.screenshots_directory,
            playbook=session.experiment_ctx.playbook,
            vm=session.experiment_ctx.vm,
            experiment_run_directory=session.experiment_ctx.experiment_run_directory.path,
            vm_os=vm_os,
            vm_user=vm_user,
            test_mode=True,
            config=session.experiment_ctx.config
        )

        log.debug("Recreated PlaybookController")

        # 10. Query and restore snapshots from hypervisor
        await _restore_snapshots(session)

        # 11. Restore initial variables
        if session.experiment_ctx.playbook and session.experiment_ctx.playbook.variables:
            session.initial_variables = session.playbook_controller.execution_context.copy()

        # 12. Mark session as running
        session.is_running = True
        session.started_at = db_session.created_at

        log.info(f"Successfully restored dev session {session.session_id}")
        return True

    except Exception as e:
        log.error(f"Failed to restore session context: {e}", exc_info=True)
        return False


async def _restore_snapshots(session: DevModeSession) -> None:
    """
    Load checkpoints from database and verify snapshot files exist.

    Args:
        session: DevModeSession to populate with snapshot metadata
    """
    try:
        from adare.database.api.devmode import DevModeApi
        import os

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

    except Exception as e:
        log.warning(f"Failed to restore checkpoints from database: {e}", exc_info=True)
        # Non-fatal - session can work without checkpoint metadata
