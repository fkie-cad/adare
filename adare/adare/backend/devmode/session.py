"""
Development mode session management.

This module provides the core DevModeSession class that wraps the existing
experiment run infrastructure to enable interactive playbook development.
"""

from dataclasses import dataclass, field
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

log = logging.getLogger(__name__)


@dataclass
class DevModeSnapshot:
    """
    Represents a VM snapshot for dev mode reset operations.

    Attributes:
        snapshot_name: Unique name for the snapshot
        created_at: When the snapshot was created
        variable_state: Dictionary of variables at snapshot time
        description: Human-readable description
    """
    snapshot_name: str
    created_at: datetime
    variable_state: Dict[str, Any]
    description: str = ""


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
        environment_name: str
    ):
        """
        Initialize dev mode session (does not start VM).

        Args:
            session_id: Unique identifier for this session
            project_path: Path to the ADARE project
            experiment_name: Name of the experiment to develop
            environment_name: Name of the environment (VM) to use
        """
        self.session_id = session_id
        self.project_path = project_path
        self.experiment_name = experiment_name
        self.environment_name = environment_name

        # Core components (initialized in start())
        self.experiment_ctx: Optional[ExperimentRunCtx] = None
        self.playbook_controller: Optional[PlaybookController] = None
        self.vm_manager: Optional[VMLifecycleManager] = None

        # Dev mode specific state
        self.snapshots: List[DevModeSnapshot] = []
        self.actions_executed: int = 0
        self.started_at: Optional[datetime] = None
        self.is_running: bool = False

        # Store initial variable state for reset operations
        self.initial_variables: Dict[str, Any] = {}

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
                disable_printing=True  # No CLI output in dev mode
            )

            # 2. Initialize ExperimentRunCtx with fake run
            self.experiment_ctx = ExperimentRunCtx(config=config)
            self.experiment_ctx.test_mode = True
            step_initialize(self.experiment_ctx, fake=True)

            log.info(f"Initialized fake experiment run: {self.experiment_ctx.experiment_run_ulid}")

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
        Soft reset: Reset execution context variables only (no VM restart).

        This is fast (<1 second) and useful for quick retries without full VM reset.

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

            # Reset execution context to initial state
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

    async def restore_checkpoint(self, name: str) -> bool:
        """
        Restore to a named checkpoint (like hard reset but to specific snapshot).

        Args:
            name: Name of the checkpoint to restore

        Returns:
            True if restore successful, False otherwise
        """
        try:
            snapshot = next(
                (s for s in self.snapshots if name in s.snapshot_name),
                None
            )
            if not snapshot:
                log.error(f"Checkpoint '{name}' not found")
                return False

            log.info(f"Restoring checkpoint: {snapshot.snapshot_name}")

            # Similar to hard_reset but with specified snapshot
            # 1. Disconnect WebSocket
            if self.experiment_ctx.client:
                await self.experiment_ctx.client.disconnect()

            # 2. Stop VM
            await self.vm_manager.stop_vm(self.experiment_ctx, post_interrupt=True)

            # 3. Restore snapshot
            await self._restore_snapshot(snapshot.snapshot_name)

            # 4. Start VM
            await self.vm_manager.start_vm(self.experiment_ctx)

            # 5. Reconnect WebSocket
            from adare.backend.experiment.run import (
                step_install_and_run_websocket_server,
                step_connect_websocket,
            )
            await step_install_and_run_websocket_server(self.experiment_ctx)
            await step_connect_websocket(self.experiment_ctx)

            # 6. Reset playbook controller state
            self.playbook_controller.execution_context.clear()
            self.playbook_controller.execution_context.update(
                snapshot.variable_state.copy()
            )

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

    async def stop(self) -> None:
        """
        Stop dev mode session and cleanup resources.

        Reuses cleanup logic from experiment_run() finally block.
        """
        try:
            log.info(f"Stopping dev mode session {self.session_id}")

            if self.experiment_ctx:
                # Reuse step cleanup functions
                from adare.backend.experiment.run import (
                    step_shutdown_ws,
                    step_shutdown_mcp_server,
                    step_remove_fake_experiment_run,
                )

                # 1. Shutdown WebSocket connection
                await step_shutdown_ws(self.experiment_ctx, post_interrupt=True)
                log.debug("WebSocket shut down")

                # 2. Shutdown MCP server
                await step_shutdown_mcp_server(self.experiment_ctx, post_interrupt=True)
                log.debug("MCP server shut down")

                # 3. Stop VM
                if self.vm_manager:
                    await self.vm_manager.stop_vm(self.experiment_ctx, post_interrupt=True)
                    log.debug("VM stopped")

                    # 4. Cleanup VM resources
                    await self.vm_manager.cleanup_vm(self.experiment_ctx, post_interrupt=True)
                    log.debug("VM cleaned up")

                # 5. Remove fake experiment run from database
                step_remove_fake_experiment_run(self.experiment_ctx)
                log.debug("Fake experiment run removed")

            self.is_running = False
            log.info(f"Dev mode session {self.session_id} stopped successfully")

        except Exception as e:
            log.error(f"Error during session stop: {e}", exc_info=True)
            self.is_running = False

    # Private helper methods

    async def _create_dev_snapshot(self, name: str, description: str):
        """
        Create VM snapshot for dev mode.

        Args:
            name: Name for the snapshot
            description: Description of the snapshot
        """
        snapshot_name = f"devmode_{self.session_id}_{name}"

        log.info(f"Creating snapshot: {snapshot_name}")

        # Delegate to hypervisor-specific strategy
        if self.experiment_ctx.hypervisor_type == 'virtualbox':
            # VirtualBox: Use VM's snapshot mixin directly
            vm = self.experiment_ctx.vm
            returncode = vm.create_snapshot(snapshot_name, description)
            if returncode != 0:
                raise HypervisorException(f"Failed to create VirtualBox snapshot '{snapshot_name}'")
            log.debug(f"VirtualBox snapshot created: {snapshot_name}")

        elif self.experiment_ctx.hypervisor_type == 'qemu':
            # QEMU: Use VM's snapshot mixin (qemu-img snapshot on stopped VM)
            vm = self.experiment_ctx.vm
            returncode = vm.create_snapshot(snapshot_name, description)
            if returncode != 0:
                raise HypervisorException(f"Failed to create QEMU snapshot '{snapshot_name}'")
            log.debug(f"QEMU snapshot created: {snapshot_name}")

        else:
            log.warning(f"Unknown hypervisor type: {self.experiment_ctx.hypervisor_type}")

        # Store snapshot metadata
        snapshot = DevModeSnapshot(
            snapshot_name=snapshot_name,
            created_at=datetime.now(),
            variable_state=(
                self.playbook_controller.execution_context.copy()
                if self.playbook_controller else {}
            ),
            description=description
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
            # QEMU: Use VM's snapshot mixin (qemu-img snapshot on stopped VM)
            vm = self.experiment_ctx.vm
            success = vm.restore_snapshot(snapshot_name)
            if not success:
                raise HypervisorException(f"Failed to restore QEMU snapshot '{snapshot_name}'")
            log.debug(f"QEMU snapshot restored: {snapshot_name}")

        else:
            log.warning(f"Unknown hypervisor type: {self.experiment_ctx.hypervisor_type}")

        log.info(f"Snapshot restored successfully: {snapshot_name}")
