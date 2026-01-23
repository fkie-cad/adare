"""
Development mode session management.

This module provides the core DevModeSession class that wraps the existing
experiment run infrastructure to enable interactive playbook development.
"""

from dataclasses import dataclass, field, is_dataclass, asdict
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, Any, List
import asyncio
import logging
import ulid

from adare.backend.experiment.runctx import ExperimentRunCtx, ExperimentConfig
from adare.backend.experiment.playbook_controller import PlaybookController
from adare.backend.experiment.vm_lifecycle_manager import VMLifecycleManager
from adare.types.playbook import ActionType, Playbook
from adare.hypervisor.exceptions import HypervisorException
from adare.types.stages import (
    Stage,
    ExperimentPreparationStage,
    CleanupShutdownStage,
    SoftwareInstallationStage,
    VirtualMachineSetupStage
)
from adare.backend.experiment.stagectxmanager import StageCtxManager

log = logging.getLogger(__name__)


@dataclass
class DevModeSnapshot:
    """
    Represents an external VM snapshot for dev mode reset operations.

    Attributes:
        snapshot_name: Unique name for the snapshot (libvirt snapshot name)
        created_at: When the snapshot was created
        variable_state: Dictionary of variables at snapshot time
        description: Human-readable description
        memory_file_path: Path to external memory save file
        disk_file_path: Path to external disk overlay file
        checkpoint_id: Database checkpoint ID (ULID)
    """
    snapshot_name: str
    created_at: datetime
    variable_state: Dict[str, Any]
    description: str = ""
    memory_file_path: str = ""
    disk_file_path: str = ""
    checkpoint_id: str = ""


@dataclass
class DevModeState:
    """
    Current state of a dev mode session (for UI/API responses).

    Attributes:
        session_id: Unique session identifier
        vm_running: Whether the VM is currently running
        experiment_name: Name of the experiment
        environment_name: Name of the environment
        actions_executed: Number of actions executed in this session
        current_variables: Current variable context
        available_snapshots: List of available snapshots
    """
    session_id: str
    vm_running: bool
    experiment_name: str
    environment_name: str
    actions_executed: int
    current_variables: Dict[str, Any]
    available_snapshots: List[DevModeSnapshot]


class DevModeSession:
    """
    Development mode session - a long-lived, interactive experiment run.

    This class wraps the standard experiment run infrastructure to provide
    interactive development capabilities while maximizing code reuse.

    Architecture:
        - Facade pattern: Wraps ExperimentRunCtx, PlaybookController, VMLifecycleManager
        - Reuses 95%+ of experiment execution infrastructure
        - Zero modifications to core experiment components

    Usage:
        session = DevModeSession(session_id, project_path, experiment_name, env_name)
        await session.start()
        result = await session.execute_action(action)
        await session.reset_hard()
        await session.stop()
    """

    def __init__(
        self,
        session_id: str,
        project_path: Path,
        experiment_name: str,
        environment_name: str,
        gui_mode: Optional[str] = None,
        vm_memory: Optional[int] = None,
        vm_cpus: Optional[int] = None,
        debug_screenshots: bool = False,
        console_ulid: Optional[str] = None
    ):
        """
        Initialize dev mode session (does not start VM).

        Args:
            session_id: Unique identifier for this session
            project_path: Path to the ADARE project
            experiment_name: Name of the experiment to develop
            environment_name: Name of the environment (VM) to use
            gui_mode: GUI execution mode override ('auto', 'agent', 'host')
            vm_memory: VM RAM in MB (None uses platform defaults)
            vm_cpus: VM CPU count (None uses default of 4)
            debug_screenshots: Save debug screenshots during execution
            console_ulid: Optional flow console ULID for event integration
        """
        self.session_id = session_id
        self.project_path = project_path
        self.experiment_name = experiment_name
        self.environment_name = environment_name
        self.gui_mode = gui_mode
        self.vm_memory = vm_memory
        self.vm_cpus = vm_cpus
        self.debug_screenshots = debug_screenshots
        self.console_ulid = console_ulid

        # Core components (initialized in start())
        self.experiment_ctx: Optional[ExperimentRunCtx] = None
        self.playbook_controller: Optional[PlaybookController] = None
        self.vm_manager: Optional[VMLifecycleManager] = None
        self.vm_instance_id: Optional[str] = None  # Track VM instance for cleanup

        # Dev mode specific state
        self.snapshots: List[DevModeSnapshot] = []
        self.actions_executed: int = 0
        self.started_at: Optional[datetime] = None
        self.is_running: bool = False

        # Store initial variable state for reset operations
        self.initial_variables: Dict[str, Any] = {}

    @staticmethod
    def _make_json_serializable(obj):
        """
        Recursively convert objects to JSON-serializable formats.
        
        Handles:
        - dataclasses -> dict
        - Path -> str
        - datetime -> isoformat str
        - list/tuple -> list
        - dict -> dict
        """
        if isinstance(obj, (str, int, float, bool, type(None))):
            return obj
        if isinstance(obj, (list, tuple)):
            return [DevModeSession._make_json_serializable(x) for x in obj]
        if isinstance(obj, dict):
            return {str(k): DevModeSession._make_json_serializable(v) for k, v in obj.items()}
        if is_dataclass(obj):
            return DevModeSession._make_json_serializable(asdict(obj))
        if isinstance(obj, Path):
            return str(obj)
        if isinstance(obj, datetime):
            return obj.isoformat()
        return str(obj)

    def _create_stage_context(self, stage: Stage):
        """
        Create a StageCtxManager configured for dev mode (skips parent validation).

        Args:
            stage: The stage to wrap

        Returns:
            StageCtxManager configured for dev mode
        """
        # Use console_ulid if provided for flow console integration, otherwise use experiment_run_ulid
        stage_ulid = self.console_ulid or self.experiment_ctx.experiment_run_ulid
        return StageCtxManager(
            stage,
            stage_ulid,
            event=self.experiment_ctx.user_interrupt_event
        )

    async def start(self) -> bool:
        """
        Start dev mode session by initializing VM and controllers.

        This reuses step functions from experiment_run() but without cleanup.
        The VM stays running and ready for interactive actions.

        Returns:
            True if session started successfully, False otherwise
        """
        try:
            log.info(f"Starting dev mode session {self.session_id}")

            # Force QEMU_LIBGUESTFS=true for dev mode because virtiofs is incompatible with
            # the live migration/snapshot mechanism used by checkpoints.
            # This forces file transfer to use libguestfs (copy files to disk before boot)
            # instead of shared folders.
            import os
            os.environ['QEMU_LIBGUESTFS'] = 'true'
            log.info("Forced QEMU_LIBGUESTFS=true to enable snapshots (virtiofs incompatible)")

            # Import required modules
            from adare.backend.experiment.run import (
                step_initialize,
                step_setup_experiment_environment,
                step_prepare_run_environment,
                step_install_and_run_websocket_server,
                step_connect_websocket,
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
                vm_cpus=self.vm_cpus or 4  # VM CPUs (default: 4)
            )

            # 2. Initialize ExperimentRunCtx with fake run
            self.experiment_ctx = ExperimentRunCtx(config=config)
            self.experiment_ctx.test_mode = True
            self.experiment_ctx.debug_screenshots = self.debug_screenshots
            step_initialize(self.experiment_ctx, fake=True)

            log.info(f"Initialized fake experiment run: {self.experiment_ctx.experiment_run_ulid}")

            # Determine ULID for StageCtxManager (use console_ulid if provided for flow console integration)
            stage_ulid = self.console_ulid or self.experiment_ctx.experiment_run_ulid

            # 3-5. Wrap preparation steps in parent stage context
            with StageCtxManager(
                ExperimentPreparationStage(),
                stage_ulid,
                event=self.experiment_ctx.user_interrupt_event
            ):
                # 3. Setup experiment environment
                step_setup_experiment_environment(self.experiment_ctx)
                log.info("Experiment environment setup complete")

                # 4. Prepare run directory
                step_prepare_run_environment(self.experiment_ctx)
                log.info("Run directory prepared")

                # 5. Start MCP server for target detection
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

            # 12. Initialize PlaybookController
            # Get VM credentials for automatic variables
            from adare.config import get_vm_credentials
            vm_os = self.experiment_ctx.guest_platform if self.experiment_ctx.guest_platform else None
            vm_user = None
            if vm_os:
                vm_user, _ = get_vm_credentials(vm_os)

            self.playbook_controller = PlaybookController(
                websocket_client=self.experiment_ctx.client,
                experiment_dir=self.experiment_ctx.experiment_directory.path,
                project_dir=self.experiment_ctx.project_directory.path,
                debug_screenshots=True,
                screenshots_dir=self.experiment_ctx.experiment_run_directory.screenshots_directory,
                playbook=self.experiment_ctx.playbook,
                experiment_run_id=self.console_ulid or self.experiment_ctx.experiment_run_ulid,
                vm=self.experiment_ctx.vm,
                experiment_run_directory=self.experiment_ctx.experiment_run_directory.path,
                vm_os=vm_os,
                vm_user=vm_user,
                test_mode=True,
                config=self.experiment_ctx.config
            )
            log.info("PlaybookController initialized")

            # Store initial variables for reset operations
            if self.experiment_ctx.playbook and self.experiment_ctx.playbook.variables:
                self.initial_variables = self.playbook_controller.execution_context.copy()

            # 13. Create initial snapshot for reset operations
            await self._create_dev_snapshot("initial", "Initial VM state for dev mode")
            log.info("Initial snapshot created")

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
            except Exception as e:
                log.error(f"Failed to retrieve VM instance ID: {e}")

            self.started_at = datetime.now()
            self.is_running = True
            log.info(f"Dev mode session {self.session_id} started successfully")
            return True

        except Exception as e:
            log.error(f"Failed to start dev mode session: {e}", exc_info=True)
            await self.stop()  # Cleanup on failure
            return False

    async def execute_action(self, action: ActionType) -> 'ActionResult':
        """
        Execute a single action interactively.

        This directly uses PlaybookController's action executor - no modification needed!
        Variables are resolved via the existing VariableResolver.

        Args:
            action: The action to execute

        Returns:
            ActionResult with success status and details
        """
        if not self.is_running or not self.playbook_controller:
            from adare.backend.experiment.execution.base import ActionResult
            return ActionResult(success=False, message="Session not running")

        try:
            log.debug(f"Executing action: {action.__class__.__name__}")

            # Execute action via PlaybookController's action_executor
            # This automatically handles:
            # - Variable resolution via VariableResolver
            # - Target resolution via MCPTargetResolver
            # - Action-specific execution logic
            result = await self.playbook_controller.action_executor.execute_action(
                action,
                parent_event_id=None,  # No event tracking in dev mode
                event_emitter=None,  # No event emission in dev mode
                variable_resolver=self.playbook_controller.variable_resolver
            )

            if result.success:
                self.actions_executed += 1
                log.info(f"Action executed successfully: {action.__class__.__name__}")
            else:
                log.warning(f"Action failed: {result.message}")

            return result

        except Exception as e:
            log.error(f"Action execution failed: {e}", exc_info=True)
            from adare.backend.experiment.execution.base import ActionResult
            return ActionResult(success=False, message=str(e))

    async def execute_playbook(self, playbook: Playbook) -> 'PlaybookExecutionResult':
        """
        Execute a full playbook (for testing sequences).

        Reuses PlaybookController.execute_playbook() unchanged!

        Args:
            playbook: The playbook to execute

        Returns:
            PlaybookExecutionResult with execution statistics
        """
        if not self.is_running or not self.playbook_controller:
            raise RuntimeError("Session not running")

        log.info(f"Executing playbook with {len(playbook.actions)} actions")

        # Update playbook reference in controller
        self.playbook_controller.playbook = playbook

        # Update variables if playbook has them
        if playbook.variables:
            var_dict = playbook.variables.to_execution_context(for_tests=False)
            self.playbook_controller.execution_context.update(var_dict)

        # Execute using existing PlaybookController logic
        result = await self.playbook_controller.execute_playbook()

        # Update statistics
        self.actions_executed += result.total_actions

        log.info(
            f"Playbook execution complete: {result.successful_actions}/"
            f"{result.total_actions} actions succeeded"
        )

        return result

    async def reset_soft(self) -> bool:
        """
        Soft reset: Restore VM to initial external snapshot (no full OS reboot).

        For QEMU: Restores external snapshot (memory + disk, ~2-5 seconds, no OS boot)
        For VirtualBox: Only resets variables (fast, <1 second)

        Returns:
            True if reset successful, False otherwise
        """
        try:
            if not self.playbook_controller:
                return False

            # Get initial snapshot (first in list)
            if not self.snapshots:
                log.warning("No snapshots available for soft reset")
                return False

            initial_snapshot = self.snapshots[0]
            vm = self.experiment_ctx.vm

            # QEMU: Restore external snapshot (memory + disk, no OS boot)
            if self.experiment_ctx.hypervisor_type == 'qemu':
                log.info(f"Soft reset: restoring external snapshot '{initial_snapshot.snapshot_name}'")

                try:
                    # Disconnect WebSocket before VM state change
                    if self.experiment_ctx.client:
                        await self.experiment_ctx.client.disconnect()
                        log.debug("WebSocket disconnected")

                    # Restore external snapshot
                    success = vm.restore_external_snapshot(
                        memory_path=initial_snapshot.memory_file_path,
                        disk_path=initial_snapshot.disk_file_path
                    )

                    if not success:
                        log.error("External snapshot restore failed")
                        # Fall back to variable-only reset
                        log.info("Falling back to variable-only reset")
                    else:
                        log.info("External snapshot restored (no OS reboot)")

                        # Reconnect WebSocket
                        from adare.backend.experiment.run import (
                            step_connect_websocket,
                        )
                        with StageCtxManager(
                            SoftwareInstallationStage(),
                            stage_ulid,
                            event=self.experiment_ctx.user_interrupt_event
                        ):
                            await step_connect_websocket(self.experiment_ctx)
                            log.debug("WebSocket reconnected")

                except Exception as e:
                    log.error(f"External snapshot restore failed: {e}", exc_info=True)
                    log.info("Falling back to variable-only reset")

            # Reset playbook variables (always done, for both QEMU and VirtualBox)
            self.playbook_controller.execution_context.clear()
            self.playbook_controller.execution_context.update(
                initial_snapshot.variable_state.copy()
            )

            # Reset counters
            self.actions_executed = 0

            log.info("Soft reset completed successfully")
            return True

        except Exception as e:
            log.error(f"Soft reset failed: {e}", exc_info=True)
            return False

    async def reset_hard(self) -> bool:
        """
        Hard reset: Restore VM to initial snapshot, reset all state.

        This uses VMLifecycleManager snapshot restoration (~10-30 seconds).
        All VM state (files, registry, memory) is restored to initial snapshot.

        Returns:
            True if reset successful, False otherwise
        """
        try:
            if not self.snapshots:
                log.error("No snapshots available for hard reset")
                return False

            initial_snapshot = self.snapshots[0]
            log.info(f"Starting hard reset to snapshot: {initial_snapshot.snapshot_name}")

            # 1. Disconnect WebSocket
            if self.experiment_ctx.client:
                await self.experiment_ctx.client.disconnect()
                log.debug("WebSocket disconnected")

            # 2. Stop VM (don't destroy)
            with self._create_stage_context(CleanupShutdownStage()):
                await self.vm_manager.stop_vm(self.experiment_ctx, post_interrupt=True)
            log.debug("VM stopped")

            # 3. Restore snapshot using hypervisor-specific strategy
            await self._restore_snapshot(initial_snapshot.snapshot_name)
            log.debug("Snapshot restored")

            # 4. Start VM again
            await self.vm_manager.start_vm(self.experiment_ctx)
            log.debug("VM restarted")

            # 5. Install and reconnect to WebSocket
            from adare.backend.experiment.run import (
                step_install_and_run_websocket_server,
                step_connect_websocket,
            )
            with StageCtxManager(
                SoftwareInstallationStage(),
                self.experiment_ctx.experiment_run_ulid,
                event=self.experiment_ctx.user_interrupt_event
            ):
                await step_install_and_run_websocket_server(self.experiment_ctx)
                await step_connect_websocket(self.experiment_ctx)
                log.debug("WebSocket reconnected")

            # 6. Reset playbook controller state
            self.playbook_controller.execution_context.clear()
            self.playbook_controller.execution_context.update(
                initial_snapshot.variable_state.copy()
            )

            # 7. Reset counters
            self.actions_executed = 0

            log.info("Hard reset completed successfully")
            return True

        except Exception as e:
            log.error(f"Hard reset failed: {e}", exc_info=True)
            return False

    async def create_checkpoint(self, name: str, description: str = "") -> bool:
        """
        Create a named snapshot for later restoration.

        Args:
            name: Name for the checkpoint
            description: Optional description

        Returns:
            True if checkpoint created successfully, False otherwise
        """
        try:
            await self._create_dev_snapshot(name, description)
            return True
        except Exception as e:
            log.error(f"Failed to create checkpoint: {e}", exc_info=True)
            return False

    async def _wait_for_vm_ready_after_restore(self, context: ExperimentRunCtx, timeout: int = 60):
        """
        Wait for VM to be ready after external snapshot restore.

        After virsh restore, the VM is running with restored memory state,
        but the guest OS needs time to initialize network and services.

        Args:
            context: Experiment run context
            timeout: Maximum seconds to wait for readiness

        Raises:
            LoggedException: If VM doesn't become ready within timeout
        """
        import asyncio
        import time
        from adare.exceptions import LoggedException

        log.info("Waiting for VM to be ready after snapshot restore...")
        start_time = time.time()

        # For QEMU, wait for guest agent to be ready
        if hasattr(context.vm, '_check_guest_agent'):
            try:
                # Try to wait for guest agent with timeout
                elapsed = 0
                while elapsed < timeout:
                    try:
                        # Check if guest agent is responsive
                        is_ready = context.vm._check_guest_agent()
                        if is_ready:
                            log.info(f"VM ready after {elapsed:.1f}s")
                            return
                    except Exception:
                        pass

                    await asyncio.sleep(2)
                    elapsed = time.time() - start_time

                # Timeout - but don't fail, just warn
                log.warning(f"Guest agent not ready after {timeout}s, continuing anyway")

            except Exception as e:
                log.warning(f"Could not check guest agent readiness: {e}")
        else:
            # Fallback: simple sleep to give VM time to stabilize
            await asyncio.sleep(5)
            log.info("VM stabilization wait completed")

    async def restore_checkpoint(self, name: str) -> bool:
        """
        Restore to a named checkpoint using external snapshot.

        Loads checkpoint from database and restores VM to external snapshot state.

        Args:
            name: Name of the checkpoint to restore

        Returns:
            True if restore successful, False otherwise
        """
        try:
            from adare.database.api.devmode import DevModeApi

            # Load checkpoint from database
            with DevModeApi() as api:
                checkpoint = api.get_checkpoint(self.session_id, name)

            if not checkpoint:
                log.error(f"Checkpoint '{name}' not found in database")
                return False

            log.info(f"Restoring checkpoint: {checkpoint.name}")

            # Find corresponding snapshot in memory (for variable state)
            snapshot = next(
                (s for s in self.snapshots if s.checkpoint_id == checkpoint.checkpoint_id),
                None
            )

            # If not in memory, construct from database checkpoint
            if not snapshot:
                snapshot = DevModeSnapshot(
                    snapshot_name=checkpoint.snapshot_name,
                    created_at=checkpoint.created_at,
                    variable_state=checkpoint.variable_state or {},
                    description=checkpoint.description or "",
                    memory_file_path=checkpoint.memory_file_path,
                    disk_file_path=checkpoint.disk_file_path,
                    checkpoint_id=checkpoint.checkpoint_id
                )

            vm = self.experiment_ctx.vm

            # QEMU: Restore external snapshot
            if self.experiment_ctx.hypervisor_type == 'qemu':
                # Disconnect WebSocket before VM state change
                if self.experiment_ctx.client:
                    await self.experiment_ctx.client.disconnect()

                # Restore external snapshot (destroys VM, updates disk, restores memory)
                success = vm.restore_external_snapshot(
                    memory_path=snapshot.memory_file_path,
                    disk_path=snapshot.disk_file_path
                )

                if not success:
                    log.error(f"Failed to restore external snapshot for checkpoint '{name}'")
                    return False

                # Wait for VM to be ready after memory restore
                # The VM is running after virsh restore, but guest OS needs time to initialize
                log.info("Waiting for VM to be ready after snapshot restore...")
                await self._wait_for_vm_ready_after_restore(self.experiment_ctx)

                # Verify websocket port is set (should be from session restore)
                if not self.experiment_ctx.config.websocket_port:
                    log.error("WebSocket port not set in context - cannot reconnect")
                    return False

                # Reconnect to WebSocket server (server already running in restored memory)
                from adare.backend.experiment.run import step_connect_websocket
                with StageCtxManager(
                    SoftwareInstallationStage(),
                    self.experiment_ctx.experiment_run_ulid,
                    event=self.experiment_ctx.user_interrupt_event
                ):
                    await step_connect_websocket(self.experiment_ctx)

            # VirtualBox path (unchanged)
            elif self.experiment_ctx.hypervisor_type == 'virtualbox':
                # Disconnect WebSocket
                if self.experiment_ctx.client:
                    await self.experiment_ctx.client.disconnect()

                # Stop VM
                with self._create_stage_context(CleanupShutdownStage()):
                    await self.vm_manager.stop_vm(self.experiment_ctx, post_interrupt=True)

                # Restore snapshot
                await self._restore_snapshot(snapshot.snapshot_name)

                # Start VM
                await self.vm_manager.start_vm(self.experiment_ctx)

                # Reconnect WebSocket
                from adare.backend.experiment.run import (
                    step_install_and_run_websocket_server,
                    step_connect_websocket,
                )
                with StageCtxManager(
                    SoftwareInstallationStage(),
                    self.experiment_ctx.experiment_run_ulid,
                    event=self.experiment_ctx.user_interrupt_event
                ):
                    await step_install_and_run_websocket_server(self.experiment_ctx)
                    await step_connect_websocket(self.experiment_ctx)

            # Reset playbook controller state
            self.playbook_controller.execution_context.clear()
            self.playbook_controller.execution_context.update(
                snapshot.variable_state.copy()
            )

            # Reset counters
            self.actions_executed = 0

            log.info(f"Checkpoint '{name}' restored successfully")
            return True

        except Exception as e:
            log.error(f"Failed to restore checkpoint: {e}", exc_info=True)
            return False

    def get_state(self) -> DevModeState:
        """
        Get current session state (for UI/API).

        Returns:
            DevModeState with current session information
        """
        return DevModeState(
            session_id=self.session_id,
            vm_running=self.is_running,
            experiment_name=self.experiment_name,
            environment_name=self.environment_name,
            actions_executed=self.actions_executed,
            current_variables=(
                self.playbook_controller.execution_context.copy()
                if self.playbook_controller else {}
            ),
            available_snapshots=self.snapshots.copy()
        )

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
                    step_shutdown_ws,
                    step_shutdown_mcp_server,
                )

                stage_ulid = self.console_ulid or self.experiment_ctx.experiment_run_ulid
                with StageCtxManager(
                    CleanupShutdownStage(),
                    stage_ulid,
                    event=None
                ):
                    # 1. Shutdown WebSocket connection
                    try:
                        await step_shutdown_ws(self.experiment_ctx, post_interrupt=True)
                        log.debug("WebSocket shut down")
                    except Exception as e:
                        log.warning(f"Failed to shutdown WebSocket: {e}")

                    # 2. Shutdown MCP server
                    try:
                        await step_shutdown_mcp_server(self.experiment_ctx, post_interrupt=True)
                        log.debug("MCP server shut down")
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
                    step_shutdown_ws,
                    step_shutdown_mcp_server,
                    step_remove_fake_experiment_run,
                )

                stage_ulid = self.console_ulid or self.experiment_ctx.experiment_run_ulid
                with StageCtxManager(
                    CleanupShutdownStage(),
                    stage_ulid,
                    event=None
                ):
                    # 1. Shutdown WebSocket
                    try:
                        await step_shutdown_ws(self.experiment_ctx, post_interrupt=True)
                        log.debug("WebSocket shut down")
                    except Exception as e:
                        log.warning(f"Failed to shutdown WebSocket: {e}")

                    # 2. Shutdown MCP server
                    try:
                        await step_shutdown_mcp_server(self.experiment_ctx, post_interrupt=True)
                        log.debug("MCP server shut down")
                    except Exception as e:
                        log.warning(f"Failed to shutdown MCP server: {e}")

                    # 3. Stop VM first (required before snapshot deletion)
                    if self.vm_manager and self.experiment_ctx.vm:
                        vm = self.experiment_ctx.vm

                        # Stop VM with force (required for checkpoint cleanup)
                        try:
                            await self.vm_manager.stop_vm(self.experiment_ctx, post_interrupt=True)
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

                    # 6. Remove fake experiment run from database
                    try:
                        step_remove_fake_experiment_run(self.experiment_ctx)
                        log.debug("Fake experiment run removed")
                    except Exception as e:
                        log.warning(f"Failed to remove fake experiment run: {e}")

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

    # Private helper methods

    async def _create_dev_snapshot(self, name: str, description: str):
        """
        Create VM external snapshot for dev mode.

        For QEMU, creates external libvirt snapshot with memory and disk files.
        Saves checkpoint metadata to database.

        Args:
            name: Name for the snapshot
            description: Description of the snapshot
        """
        from adare.database.api.devmode import DevModeApi
        from adare.database.models.devcheckpoint import DevCheckpoint

        snapshot_name = f"devmode_{self.session_id}_{name}"
        checkpoint_id = str(ulid.ULID())

        log.info(f"Creating external snapshot: {snapshot_name}")

        # Delegate to hypervisor-specific strategy
        if self.experiment_ctx.hypervisor_type == 'virtualbox':
            # VirtualBox: Can create snapshots on running VMs
            vm = self.experiment_ctx.vm
            returncode = vm.create_snapshot(snapshot_name, description)
            if returncode != 0:
                raise HypervisorException(f"Failed to create VirtualBox snapshot '{snapshot_name}'")
            log.debug(f"VirtualBox snapshot created: {snapshot_name}")

            # For VirtualBox, we don't have external files
            memory_file_path = ""
            disk_file_path = ""

        elif self.experiment_ctx.hypervisor_type == 'qemu':
            # QEMU: Create external libvirt snapshot
            vm = self.experiment_ctx.vm

            # Verify VM is running
            if vm.get_state() != 'running':
                raise HypervisorException("VM must be running to create live snapshot")

            # Compute snapshot storage directory
            snapshot_dir = vm._get_snapshot_storage_dir()

            # Generate file paths
            memory_file_path = str(snapshot_dir / f"{snapshot_name}_RAM.save")
            disk_file_path = str(snapshot_dir / f"{snapshot_name}_DISK.qcow2")

            # Create external snapshot
            success = vm.create_external_snapshot(
                snapshot_name=snapshot_name,
                memory_path=memory_file_path,
                disk_path=disk_file_path,
                use_quiesce=True
            )

            if not success:
                raise HypervisorException(f"Failed to create external snapshot '{snapshot_name}'")

            log.info(f"External snapshot created: {snapshot_name}")
            log.debug(f"Memory file: {memory_file_path}")
            log.debug(f"Disk file: {disk_file_path}")

        else:
            log.warning(f"Unknown hypervisor type: {self.experiment_ctx.hypervisor_type}")
            memory_file_path = ""
            disk_file_path = ""

        # Save checkpoint to database
        variable_state = (
            self._make_json_serializable(self.playbook_controller.execution_context)
            if self.playbook_controller else {}
        )

        checkpoint = DevCheckpoint(
            checkpoint_id=checkpoint_id,
            session_id=self.session_id,
            name=name,
            description=description,
            memory_file_path=memory_file_path,
            disk_file_path=disk_file_path,
            snapshot_name=snapshot_name,
            variable_state=variable_state,
            created_at=datetime.now()
        )

        with DevModeApi() as api:
            api.save_checkpoint(checkpoint)

        log.info(f"Checkpoint saved to database: {checkpoint_id}")

        # Store snapshot metadata in memory
        snapshot = DevModeSnapshot(
            snapshot_name=snapshot_name,
            created_at=datetime.now(),
            variable_state=variable_state,
            description=description,
            memory_file_path=memory_file_path,
            disk_file_path=disk_file_path,
            checkpoint_id=checkpoint_id
        )
        self.snapshots.append(snapshot)

        log.info(f"Snapshot metadata stored: {snapshot_name}")

    async def _restore_snapshot(self, snapshot_name: str):
        """
        Restore VM to specific snapshot.

        Args:
            snapshot_name: Name of the snapshot to restore
        """
        log.info(f"Restoring snapshot: {snapshot_name}")

        # Delegate to hypervisor-specific strategy
        if self.experiment_ctx.hypervisor_type == 'virtualbox':
            # VirtualBox: Use VM's snapshot mixin directly
            vm = self.experiment_ctx.vm
            success = vm.restore_snapshot(snapshot_name)
            if not success:
                raise HypervisorException(f"Failed to restore VirtualBox snapshot '{snapshot_name}'")
            log.debug(f"VirtualBox snapshot restored: {snapshot_name}")

        elif self.experiment_ctx.hypervisor_type == 'qemu':
            # QEMU Hard Reset: Restore disk snapshot + full OS reboot
            vm = self.experiment_ctx.vm

            log.info(f"Hard reset: restoring disk snapshot '{snapshot_name}_disk' with full reboot")

            try:
                # Check if disk snapshot exists
                disk_snapshot_name = f"{snapshot_name}_disk"
                if vm.snapshot_exists(disk_snapshot_name):
                    # Restore disk snapshot (qemu-img)
                    success = vm.restore_snapshot(disk_snapshot_name, silent=False)
                    if not success:
                        raise Exception("Disk snapshot restore failed")
                    log.info("Disk snapshot restored")
                else:
                    # Fall back to overlay recreation if snapshot doesn't exist
                    log.warning(f"Disk snapshot '{disk_snapshot_name}' not found, falling back to overlay recreation")

                    experiment_id = self.experiment_ctx.experiment_run_ulid

                    # Delete old overlay disk
                    old_overlay = vm.get_overlay_disk_path(experiment_id)
                    if Path(old_overlay).exists():
                        log.debug(f"Deleting old overlay: {old_overlay}")
                        Path(old_overlay).unlink()

                    # Create fresh overlay from base disk
                    new_overlay = await vm.create_overlay_disk(experiment_id)
                    log.debug(f"Created fresh overlay: {new_overlay}")

                    # Update VM config to use new overlay
                    vm.config.disk_path = new_overlay
                    log.info("QEMU overlay reset complete")

            except Exception as e:
                log.error(f"Hard reset disk restoration failed: {e}", exc_info=True)
                raise

        else:
            log.warning(f"Unknown hypervisor type: {self.experiment_ctx.hypervisor_type}")

        log.info(f"Snapshot restored successfully: {snapshot_name}")

    async def _cleanup_snapshots(self):
        """
        Cleanup all checkpoints and snapshot files for this session.

        Deletes external snapshot files and database checkpoint records.
        """
        from adare.database.api.devmode import DevModeApi

        log.info(f"Cleaning up checkpoints for session {self.session_id}")

        # Load all checkpoints from database
        with DevModeApi() as api:
            checkpoints = api.list_checkpoints(self.session_id)

        if not checkpoints:
            log.debug("No checkpoints to clean up")
            return

        # Delete snapshots based on hypervisor type
        if self.experiment_ctx.hypervisor_type == 'qemu':
            vm = self.experiment_ctx.vm

            for checkpoint in checkpoints:
                try:
                    # Delete external snapshot
                    success = vm.delete_external_snapshot(
                        snapshot_name=checkpoint.snapshot_name,
                        memory_path=checkpoint.memory_file_path,
                        disk_path=checkpoint.disk_file_path
                    )
                    if success:
                        log.debug(f"Deleted external snapshot: {checkpoint.snapshot_name}")
                    else:
                        log.warning(f"Failed to delete external snapshot: {checkpoint.snapshot_name}")

                except Exception as e:
                    log.warning(f"Error deleting external snapshot {checkpoint.snapshot_name}: {e}")

        elif self.experiment_ctx.hypervisor_type == 'virtualbox':
            vm = self.experiment_ctx.vm

            for checkpoint in checkpoints:
                try:
                    success = vm.delete_snapshot(checkpoint.snapshot_name, silent=True)
                    if success:
                        log.debug(f"Deleted VirtualBox snapshot: {checkpoint.snapshot_name}")
                except Exception as e:
                    log.warning(f"Failed to delete VirtualBox snapshot {checkpoint.snapshot_name}: {e}")

        # Delete all checkpoints from database
        with DevModeApi() as api:
            deleted_count = api.delete_session_checkpoints(self.session_id)

        log.info(f"Cleaned up {deleted_count} checkpoints for session {self.session_id}")

        # Clean up empty snapshot directory for QEMU
        if self.experiment_ctx.hypervisor_type == 'qemu':
            try:
                vm = self.experiment_ctx.vm
                snapshot_dir = vm._get_snapshot_storage_dir()
                if snapshot_dir.exists():
                    # Check if directory is empty
                    if not any(snapshot_dir.iterdir()):
                        snapshot_dir.rmdir()
                        log.info(f"CLAUDE: Removed empty snapshot directory: {snapshot_dir}")
                    else:
                        log.warning(f"CLAUDE: Snapshot directory not empty after cleanup: {snapshot_dir}")
            except Exception as e:
                log.warning(f"CLAUDE: Failed to remove snapshot directory: {e}")
