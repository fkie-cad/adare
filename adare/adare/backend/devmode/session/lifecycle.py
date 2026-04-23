"""
Session lifecycle management: start, shutdown, stop, and cleanup.

This module contains the DevModeLifecycleMixin with methods for
starting the VM session, shutting down, and full removal/cleanup.
"""

import logging
from datetime import datetime
from pathlib import Path

from adare.backend.experiment.exceptions import ExperimentException
from adare.backend.experiment.runctx import ExperimentConfig, ExperimentRunCtx
from adare.backend.experiment.stagectxmanager import StageCtxManager
from adare.backend.experiment.vm_lifecycle_manager import VMLifecycleManager
from adare.backend.experiment.websocket_client import WebSocketTimeoutError
from adare.core.result import Result
from adare.database.exceptions import DatabaseError
from adare.exceptions import LoggedErrorException
from adare.hypervisor.exceptions import HypervisorException
from adare.types.stages import (
    CleanupShutdownStage,
    ExperimentPreparationStage,
    SoftwareInstallationStage,
    VirtualMachineSetupStage,
)

log = logging.getLogger(__name__)


class DevModeLifecycleMixin:
    """
    Mixin providing session lifecycle methods: start, shutdown, stop_and_remove, stop.

    Depends on attributes from DevModeSessionCore:
        session_id, project_path, environment_name, gui_mode, vm_memory, vm_cpus,
        debug_screenshots, console_ulid, experiment_name, shared_directories,
        experiment_ctx, playbook_controller, vm_manager, vm_instance_id,
        snapshots, actions_executed, started_at, is_running, run_directory_path,
        initial_variables, session_log_handler

    Depends on methods from DevModeSessionCore:
        _initialize_session_logging, _cleanup_session_logging, _create_stage_context

    Depends on methods from DevModeSnapshotsMixin:
        _cleanup_snapshots
    """

    async def start(self) -> Result[None]:
        """
        Start dev mode session by initializing VM and controllers.

        This reuses step functions from experiment_run() but without cleanup.
        The VM stays running and ready for interactive actions.

        Returns:
            Result[None] with success or error information
        """
        try:
            log.info(f"Starting dev mode session {self.session_id}")

            # QEMU_LIBGUESTFS is no longer forced to 'true' for dev mode.
            # This allows using virtio-fs for shared directories, which enables
            # real-time bidirectional file sync between host and guest.
            #
            # Note: This may impact internal snapshot compatibility (savevm) in some
            # QEMU versions, but Adare primarily uses external qcow2 snapshots/overlays.

            # Import required modules
            from adare.backend.experiment.run import (
                step_connect_websocket,
                step_initialize,
                step_install_and_run_websocket_server,
                step_prepare_run_environment,
                step_setup_experiment_environment,
                step_start_mcp_server,
            )

            # 1. Create ExperimentConfig (test mode + preserve snapshot)
            config = ExperimentConfig(
                project_path=self.project_path,
                experiment_name=self.experiment_name,
                environment_name=self.environment_name,
                test_mode=True,  # Dev mode = test mode (no integrity checks)
                preserve_snapshot=True,  # Keep snapshots for reset
                runlog=True,  # Enable logging
                disable_printing=True,  # No CLI output in dev mode
                gui_mode_override=self.gui_mode,  # Pass GUI mode override
                vm_memory=self.vm_memory or 4096,  # VM RAM (default: 4096)
                vm_cpus=self.vm_cpus or 4,  # VM CPUs (default: 4)
                shared_directories=self.shared_directories,
                dev_mode=True,  # Dev mode session = force dev mode flag
            )

            # 2. Initialize ExperimentRunCtx with fake run
            self.experiment_ctx = ExperimentRunCtx(config=config)
            self.experiment_ctx.test_mode = True
            self.experiment_ctx.debug_screenshots = self.debug_screenshots

            # Use session_id as experiment_run_ulid to ensure persistent linking
            # This fixes issues where checkpoint restoration expects a specific ID format
            # or where we need to find the run later by session ID
            step_initialize(self.experiment_ctx, fake=True, run_ulid=self.session_id)

            log.info(f"Initialized fake experiment run: {self.experiment_ctx.experiment_run_ulid}")

            # Determine ULID for StageCtxManager (use console_ulid if provided for flow console integration)
            stage_ulid = self.console_ulid or self.experiment_ctx.experiment_run_ulid

            # 3-5. Wrap preparation steps in parent stage context
            with StageCtxManager(
                ExperimentPreparationStage(),
                stage_ulid,
                event=self.experiment_ctx.user_interrupt_event
            ):
                if self.experiment_name:
                    # 3. Setup experiment environment (standard flow)
                    step_setup_experiment_environment(self.experiment_ctx)
                    log.info("Experiment environment setup complete")
                else:
                    # 3. Manual setup for bare session (no experiment)
                    self._setup_bare_session()

                # 4. Prepare run directory
                # For bare sessions (no experiment), permanently use "_dev_session" as experiment name
                if not self.experiment_ctx.config.experiment_name:
                    self.experiment_ctx.config.experiment_name = "_dev_session"

                step_prepare_run_environment(self.experiment_ctx, skip_adare_log=True)

                # Store the run directory path in session (will be persisted to DB by service layer)
                self.run_directory_path = self.experiment_ctx.experiment_run_directory.path
                log.info(f"Stored run directory path: {self.run_directory_path}")

                log.info("Run directory prepared")

                # Initialize session-level logging
                self._initialize_session_logging()

                # 5. Start MCP server for target detection
                # Force cleanup of any existing server to ensure we capture logs in this session
                if self.experiment_ctx.mcp_server:
                    log.info("Stopping any existing MCP server to ensure log capture")
                    await self.experiment_ctx.mcp_server.stop(force_external=True)

                await step_start_mcp_server(self.experiment_ctx)
                log.info("MCP server started")

            # 6. Create VM lifecycle manager
            hypervisor = self.experiment_ctx.hypervisor_type or 'virtualbox'
            self.vm_manager = VMLifecycleManager(hypervisor_type=hypervisor)
            log.info(f"Created VM lifecycle manager for {hypervisor}")

            # 7-9. Wrap VM setup in parent stage context
            with StageCtxManager(
                VirtualMachineSetupStage(),
                stage_ulid,
                event=self.experiment_ctx.user_interrupt_event
            ):
                # 7. Create and prepare VM
                await self.vm_manager.create_and_prepare_vm(self.experiment_ctx)
                log.info("VM created and prepared")

                # 8. Setup file transfer and networking
                await self.vm_manager.setup_file_transfer(self.experiment_ctx)
                log.info("File transfer configured")

                await self.vm_manager.setup_networking(self.experiment_ctx)
                log.info("Networking configured")

                # 9. Start VM
                await self.vm_manager.start_vm(self.experiment_ctx)
                log.info("VM started")

            # 10-11. Software installation happens after VM setup completes
            with StageCtxManager(
                SoftwareInstallationStage(),
                stage_ulid,
                event=self.experiment_ctx.user_interrupt_event
            ):
                # 10. Install and run WebSocket server in VM
                await step_install_and_run_websocket_server(self.experiment_ctx)
                log.info("AdareVM WebSocket server installed")

                # 11. Connect to WebSocket
                await step_connect_websocket(self.experiment_ctx)
                log.info("Connected to WebSocket")

            # 12. PlaybookController is now lazily initialized in _ensure_playbook_controller()
            # This avoids crashes when experiment context is incomplete during simple start
            self.playbook_controller = None

            # Store initial variables for reset operations - will be populated when controller initializes
            self.initial_variables = {}

            # 13. Create initial snapshot for reset operations
            #("initial", "Initial VM state for dev mode")
            #log.info("Initial snapshot created")

            # 14. Retrieve and store VM instance ID for cleanup
            try:
                from adare.database.api.experiment import ExperimentApi
                from adare.database.models.project_models import ExperimentRun

                with ExperimentApi(self.experiment_ctx.config.project_path) as api:
                    experiment_run = api._session.query(ExperimentRun).filter(
                        ExperimentRun.id == self.experiment_ctx.experiment_run_ulid
                    ).first()

                    if experiment_run and experiment_run.vm_instance_id:
                        self.vm_instance_id = experiment_run.vm_instance_id
                        log.info(f"Stored VM instance ID for cleanup: {self.vm_instance_id}")
                    else:
                        log.warning("No VM instance ID found in fake experiment run")
            except (DatabaseError, LoggedErrorException) as e:
                log.error(f"Failed to retrieve VM instance ID: {e}")

            self.started_at = datetime.now()
            self.is_running = True
            log.info(f"Dev mode session {self.session_id} started successfully")
            return Result.ok(None)

        except HypervisorException as e:
            log.error(f"Failed to start dev mode session: {e}", exc_info=True)
            await self.stop()  # Cleanup on failure
            return Result.fail("VM_OPERATION_FAILED", f"Failed to start dev mode session: {e}")
        except (WebSocketTimeoutError, ConnectionError, OSError) as e:
            log.error(f"Failed to start dev mode session: {e}", exc_info=True)
            await self.stop()  # Cleanup on failure
            return Result.fail("CONNECTION_FAILED", f"Failed to start dev mode session: {e}")
        except (DatabaseError, ExperimentException) as e:
            log.error(f"Failed to start dev mode session: {e}", exc_info=True)
            await self.stop()  # Cleanup on failure
            return Result.fail("SETUP_FAILED", f"Failed to start dev mode session: {e}")
        except LoggedErrorException as e:
            log.error(f"Failed to start dev mode session: {e}", exc_info=True)
            await self.stop()  # Cleanup on failure
            return Result.fail("SESSION_START_FAILED", f"Failed to start dev mode session: {e}")

    def _setup_bare_session(self):
        """
        Manual setup for bare session (no experiment).

        Sets up project directory, database entries, and environment resolution
        when no experiment name is provided.
        """
        from adare.backend.environment import database as environment_database
        from adare.backend.experiment import database as experiment_database
        from adare.backend.project.directory import ProjectDirectory

        # Setup ProjectDirectory
        self.experiment_ctx.project_directory = ProjectDirectory(self.project_path)

        # Set experiment name to None to avoid validation errors
        self.experiment_ctx.config.experiment_name = None

        # Set base info in DB (using placeholder name for experiment)
        experiment_database.set_experiment_run_base_info(
            self.experiment_ctx.experiment_run_ulid,
            "_dev_session",  # Placeholder
            self.experiment_ctx.config.environment_name,
            self.experiment_ctx.config.project_path
        )

        # Update start timestamp
        experiment_database.update_experiment_run_start(
            self.experiment_ctx.project_directory.path,
            self.experiment_ctx.experiment_run_ulid,
            self.experiment_ctx.timestamp_start
        )

        # Resolve environment manually
        self.experiment_ctx.environment_file = environment_database.get_environment_path_by_project_and_name(
            self.project_path, self.environment_name
        )
        self.experiment_ctx.environment_ulid = environment_database.resolve_environment_identifier(
            self.experiment_name or self.environment_name
        )

        # Resolve VM file and platform
        self.experiment_ctx.vm_file = environment_database.get_environment_vm_file(self.experiment_ctx.environment_ulid)
        self.experiment_ctx.guest_platform = environment_database.get_environment_os(self.experiment_ctx.environment_ulid)
        self.experiment_ctx.hypervisor_type = environment_database.get_environment_hypervisor(self.experiment_ctx.environment_ulid)

        # Fallback parsing if needed
        if not self.experiment_ctx.vm_file or not self.experiment_ctx.guest_platform:
            from adare.types.environment import parse_environment_file
            env_meta = parse_environment_file(self.experiment_ctx.environment_file)
            if not self.experiment_ctx.vm_file:
                self.experiment_ctx.vm_file = Path(env_meta.vm)
            if not self.experiment_ctx.guest_platform:
                self.experiment_ctx.guest_platform = env_meta.os.platform

        log.info(f"Manual environment setup complete: {self.environment_name}")

    async def shutdown(self) -> None:
        """
        Shutdown dev mode session (VM only, keep all resources).

        This is the new default behavior for 'adare dev stop':
        - Shuts down WebSocket and MCP server
        - Stops the VM gracefully
        - Does NOT delete snapshots, VM disks, or database entries
        - Session can be restarted later
        """
        try:
            log.info(f"Shutting down session {self.session_id} (keeping resources)")

            if self.experiment_ctx:
                from adare.backend.experiment.run import (
                    step_shutdown_mcp_server,
                    step_shutdown_ws,
                )

                stage_ulid = self.console_ulid or self.experiment_ctx.experiment_run_ulid
                with StageCtxManager(
                    CleanupShutdownStage(),
                    stage_ulid,
                    event=None
                ):
                    # 1. Shutdown WebSocket connection
                    if self.experiment_ctx.client:
                        try:
                            await step_shutdown_ws(self.experiment_ctx, post_interrupt=True)
                            log.debug("WebSocket shut down")
                        except Exception as e:
                            log.warning(f"Failed to shutdown WebSocket: {e}")

                    # 2. Shutdown MCP server (only if no other sessions are using it)
                    if self.experiment_ctx.mcp_server:
                        try:
                            # Check if other sessions are running
                            from adare.database.api.devmode import DevModeApi
                            with DevModeApi() as api:
                                running_sessions = api.list_running_sessions()
                                # Filter out current session (active or already marked stopped)
                                other_active_sessions = [
                                    s for s in running_sessions
                                    if s.session_id != self.session_id
                                ]

                            if other_active_sessions:
                                log.info(f"Skipping MCP server shutdown - used by {len(other_active_sessions)} other session(s)")
                            else:
                                await step_shutdown_mcp_server(self.experiment_ctx, post_interrupt=True, force=True)
                                log.debug("MCP server shut down (last session)")
                        except Exception as e:
                            log.warning(f"Failed to shutdown MCP server: {e}")

                    # 3. Stop VM (graceful shutdown, keep disk and snapshots)
                    if self.vm_manager:
                        try:
                            await self.vm_manager.stop_vm(self.experiment_ctx, post_interrupt=True)
                            log.debug("VM stopped")
                        except Exception as e:
                            log.warning(f"Failed to stop VM: {e}")

                    # 4. Release VM instance for reuse
                    if self.vm_instance_id:
                        try:
                            from adare.backend.vm.commands import release_vm_instance_for_experiment
                            await release_vm_instance_for_experiment(self.vm_instance_id)
                            log.info(f"Released VM instance {self.vm_instance_id} for reuse")
                        except Exception as e:
                            log.error(f"Failed to release VM instance: {e}")

            # Clean up session logging
            self._cleanup_session_logging()

            self.is_running = False
            log.info(f"Session {self.session_id} shut down (resources preserved)")

        except Exception as e:
            log.error(f"Error during session shutdown: {e}", exc_info=True)
            self.is_running = False

    async def stop_and_remove(self) -> None:
        """
        Stop dev mode session and remove ALL resources.

        This is used by 'adare dev stop --rm' and 'adare dev remove':
        - Stops the VM
        - Deletes VM instance and all disks
        - Deletes all snapshot files (external RAM/disk files)
        - Removes experiment run directory
        - Removes fake experiment run from DB
        - Database session/checkpoint cleanup handled by service layer
        """
        try:
            log.info(f"Stopping and removing session {self.session_id} with full cleanup")

            # Track cleanup failures for better error reporting
            cleanup_failures = []

            if self.experiment_ctx:
                from adare.backend.experiment.run import (
                    step_remove_fake_experiment_run,
                    step_shutdown_mcp_server,
                    step_shutdown_ws,
                )

                stage_ulid = self.console_ulid or self.experiment_ctx.experiment_run_ulid
                with StageCtxManager(
                    CleanupShutdownStage(),
                    stage_ulid,
                    event=None
                ):
                    # 1. Shutdown WebSocket
                    if self.experiment_ctx.client:
                        try:
                            await step_shutdown_ws(self.experiment_ctx, post_interrupt=True)
                            log.debug("WebSocket shut down")
                        except Exception as e:
                            log.warning(f"Failed to shutdown WebSocket: {e}")

                    # 2. Shutdown MCP server (only if no other sessions are using it)
                    if self.experiment_ctx.mcp_server:
                        try:
                            # Check if other sessions are running
                            from adare.database.api.devmode import DevModeApi
                            with DevModeApi() as api:
                                running_sessions = api.list_running_sessions()
                                # Filter out current session
                                other_active_sessions = [
                                    s for s in running_sessions
                                    if s.session_id != self.session_id
                                ]

                            if other_active_sessions:
                                log.info(f"Skipping MCP server shutdown - used by {len(other_active_sessions)} other session(s)")
                            else:
                                await step_shutdown_mcp_server(self.experiment_ctx, post_interrupt=True, force=True)
                                log.debug("MCP server shut down (last session)")
                        except Exception as e:
                            log.warning(f"Failed to shutdown MCP server: {e}")

                    # 3. Stop VM first (required before snapshot deletion)
                    if self.vm_manager and self.experiment_ctx.vm:
                        vm = self.experiment_ctx.vm

                        # Stop VM with force (required for checkpoint cleanup)
                        try:
                            await self.vm_manager.stop_vm(self.experiment_ctx, post_interrupt=True, force=True)
                            log.debug("VM stopped")
                        except Exception as e:
                            log.warning(f"Failed to stop VM: {e}")
                            # Continue anyway - destroy will try again

                    # 4. Delete all checkpoints (requires VM to be stopped)
                    try:
                        await self._cleanup_snapshots()
                        log.debug("Checkpoints cleaned up")
                    except Exception as e:
                        error_msg = f"Failed to cleanup checkpoints: {e}"
                        log.error(error_msg)
                        cleanup_failures.append(error_msg)
                        # Continue with VM destruction

                    # 5. Destroy VM (undefine domain + delete disks)
                    if self.vm_manager and self.experiment_ctx.vm:
                        try:
                            result = await vm.destroy(silent=False)
                            if result != 0:
                                error_msg = f"VM destroy returned error code {result}"
                                log.error(error_msg)
                                cleanup_failures.append(error_msg)
                            else:
                                log.info(f"VM '{vm.vm_name}' destroyed")
                        except Exception as e:
                            error_msg = f"VM destroy failed: {e}"
                            log.error(error_msg)
                            cleanup_failures.append(error_msg)

                    # 6. Release VM instance before removal
                    if self.vm_instance_id:
                        try:
                            from adare.backend.vm.commands import release_vm_instance_for_experiment
                            await release_vm_instance_for_experiment(self.vm_instance_id)
                            log.info(f"Released VM instance {self.vm_instance_id}")
                        except Exception as e:
                            error_msg = f"Failed to release VM instance: {e}"
                            log.error(error_msg)
                            cleanup_failures.append(error_msg)

                    # 7. Delete experiment run directory
                    try:
                        import shutil
                        run_dir = self.experiment_ctx.experiment_run_directory.path
                        if run_dir.exists():
                            shutil.rmtree(run_dir)
                            log.info(f"Deleted experiment run directory: {run_dir}")
                    except Exception as e:
                        log.warning(f"Failed to delete run directory: {e}")

                    # 8. Remove fake experiment run from database
                    try:
                        step_remove_fake_experiment_run(self.experiment_ctx)
                        log.debug("Fake experiment run removed")
                    except Exception as e:
                        log.warning(f"Failed to remove fake experiment run: {e}")

            # Clean up session logging
            self._cleanup_session_logging()

            self.is_running = False

            # Report final status
            if cleanup_failures:
                log.error(f"Session {self.session_id} removal completed with errors: {'; '.join(cleanup_failures)}")
            else:
                log.info(f"Session {self.session_id} completely removed")

        except Exception as e:
            log.error(f"Error during session removal: {e}", exc_info=True)
            self.is_running = False

    async def stop(self, cleanup: bool = True) -> None:
        """
        DEPRECATED: Use shutdown() or stop_and_remove() instead.

        This method is kept for backward compatibility with existing code.
        """
        if cleanup:
            await self.stop_and_remove()
        else:
            await self.shutdown()
