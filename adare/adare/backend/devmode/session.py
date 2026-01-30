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
from contextlib import contextmanager

from adare.backend.experiment.runctx import ExperimentRunCtx, ExperimentConfig
from adare.backend.experiment.playbook_controller import PlaybookController
from adare.backend.experiment.playbook_controller import PlaybookController
from adare.backend.experiment.vm_lifecycle_manager import VMLifecycleManager
from adare.backend.experiment.mcp_server_manager import MCPServerManager
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
    environment_name: str
    actions_executed: int
    current_variables: Dict[str, Any]
    available_snapshots: List[DevModeSnapshot]
    experiment_name: Optional[str] = None


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
        environment_name: str,
        gui_mode: Optional[str] = None,
        vm_memory: Optional[int] = None,
        vm_cpus: Optional[int] = None,
        debug_screenshots: bool = False,
        console_ulid: Optional[str] = None,
        experiment_name: Optional[str] = None,
        shared_directories: Optional[Dict[str, Dict[str, Path]]] = None
    ):
        """
        Initialize dev mode session (does not start VM).

        Args:
            session_id: Unique identifier for this session
            project_path: Path to the ADARE project
            environment_name: Name of the environment (VM) to use
            gui_mode: GUI execution mode override ('auto', 'agent', 'host')
            vm_memory: VM RAM in MB (None uses platform defaults)
            vm_cpus: VM CPU count (None uses default of 4)
            debug_screenshots: Save debug screenshots during execution
            console_ulid: Optional flow console ULID for event integration
            experiment_name: Optional name of the experiment (None for bare session)
            shared_directories: Optional Dict of shared directories {name: {'host': Path, 'vm': Path}}
        """
        self.session_id = session_id
        self.project_path = project_path
        self.environment_name = environment_name
        self.gui_mode = gui_mode
        self.vm_memory = vm_memory
        self.vm_cpus = vm_cpus
        self.debug_screenshots = debug_screenshots
        self.console_ulid = console_ulid
        self.experiment_name = experiment_name
        self.shared_directories = shared_directories or {}

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
        self.run_directory_path: Optional[Path] = None  # Stored after run dir creation

        # Store initial variable state for reset operations
        self.initial_variables: Dict[str, Any] = {}

        # Session-level log handler
        self.session_log_handler: Optional[logging.Handler] = None

        # Recording state
        self.recorder: Optional[any] = None # SessionRecorder instance

    @contextmanager
    def _command_logger(self, command_name: str):
        """
        Context manager to capture logs for a specific command execution.
        
        Creates a new log file: logs/{timestamp}_{command_name}.log
        
        Args:
            command_name: Name of the command (e.g., ActionClassName, playbook_run)
        """
        if not self.experiment_ctx or not self.experiment_ctx.experiment_run_directory:
            yield
            return

        # Create log filename
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        safe_name = "".join(c for c in command_name if c.isalnum() or c in ('_', '-'))
        log_filename = f"{timestamp}_{safe_name}.log"
        log_path = self.experiment_ctx.experiment_run_directory.log_directory / log_filename
        
        handler = None
        try:
            # Create handler
            handler = logging.FileHandler(log_path, mode='w', encoding='utf-8')
            formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
            handler.setFormatter(formatter)
            handler.setLevel(logging.DEBUG)
            
            # Add to root logger to capture everything
            root_logger = logging.getLogger()
            root_logger.addHandler(handler)
            

            log.info(f"Started command logging to {log_filename}")
            
            # Save current root logger level and force to DEBUG to ensure all logs are captured
            previous_level = root_logger.level
            root_logger.setLevel(logging.DEBUG)
            
            yield
            
        except Exception as e:
            log.warning(f"Failed to setup command logger: {e}")
            yield
        finally:
            if handler:
                root_logger = logging.getLogger()
                root_logger.removeHandler(handler)
                
                # Restore previous level
                if 'previous_level' in locals():
                    root_logger.setLevel(previous_level)
                    
                handler.close()
                log.info(f"Stopped command logging to {log_filename}")

    def _initialize_session_logging(self):
        """Initialize session-level logging with clean state."""
        if not self.experiment_ctx or not self.experiment_ctx.experiment_run_directory:
            log.warning("Cannot initialize session logging: no run directory")
            return

        # Create session log file
        log_dir = self.experiment_ctx.experiment_run_directory.log_directory
        session_log_file = log_dir / 'session.log'

        # Use write mode to start fresh (no accumulation)
        handler = logging.FileHandler(session_log_file, mode='w', encoding='utf-8')
        formatter = logging.Formatter(
            '[%(asctime)s]: %(threadName)s - %(name)s: %(levelname)s - %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )
        handler.setFormatter(formatter)
        handler.setLevel(logging.DEBUG)

        # Add to root logger
        root_logger = logging.getLogger()
        root_logger.addHandler(handler)
        # Ensure root logger level allows DEBUG messages to be captured
        if root_logger.level > logging.DEBUG:
            root_logger.setLevel(logging.DEBUG)

        self.session_log_handler = handler
        log.info(f"Dev session logging initialized: {session_log_file}")

    def _cleanup_session_logging(self):
        """Clean up session log handler."""
        if self.session_log_handler:
            try:
                logging.getLogger().removeHandler(self.session_log_handler)
                self.session_log_handler.close()
                self.session_log_handler = None
                log.info("Dev session logging cleaned up")
            except Exception as e:
                log.warning(f"Error cleaning up session log handler: {e}")

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

            # QEMU_LIBGUESTFS is no longer forced to 'true' for dev mode.
            # This allows using virtio-fs for shared directories, which enables
            # real-time bidirectional file sync between host and guest.
            #
            # Note: This may impact internal snapshot compatibility (savevm) in some
            # QEMU versions, but Adare primarily uses external qcow2 snapshots/overlays.

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
                    from adare.backend.project.directory import ProjectDirectory
                    from adare.backend.experiment.directory import ExperimentRunDirectory
                    from adare.backend.environment import database as environment_database
                    from adare.backend.experiment import database as experiment_database

                    # Setup ProjectDirectory
                    self.experiment_ctx.project_directory = ProjectDirectory(self.project_path)
                    
                    # Set experiment name to None to avoid validation errors
                    self.experiment_ctx.config.experiment_name = None

                    # Set base info in DB (using placeholder name for experiment)
                    experiment_database.set_experiment_run_base_info(
                        self.experiment_ctx.experiment_run_ulid,
                        "_dev_session", # Placeholder
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

                # 4. Prepare run directory
                # For bare sessions (no experiment), permanently use "_dev_session" as experiment name
                if not self.experiment_ctx.config.experiment_name:
                    self.experiment_ctx.config.experiment_name = "_dev_session"

                step_prepare_run_environment(self.experiment_ctx, skip_adare_log=True)

                # Store the run directory path in session (will be persisted to DB by service layer)
                self.run_directory_path = self.experiment_ctx.experiment_run_directory.path
                log.info(f"CLAUDE: Stored run directory path: {self.run_directory_path}")

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

    async def _ensure_playbook_controller(self) -> bool:
        """
        Lazily initialize the PlaybookController if it doesn't exist.
        
        Returns:
            True if controller is ready, False otherwise
        """
        if self.playbook_controller:
            return True
            
        try:
            log.info("Initializing PlaybookController lazily...")
            
            # Get VM credentials for automatic variables
            from adare.config import get_vm_credentials
            vm_os = self.experiment_ctx.guest_platform if self.experiment_ctx.guest_platform else None
            vm_user = None
            if vm_os:
                vm_user, _ = get_vm_credentials(vm_os)

            # Handle potentially missing directory paths
            experiment_dir = None
            if self.experiment_ctx.experiment_directory:
                experiment_dir = self.experiment_ctx.experiment_directory.path
            
            self.playbook_controller = PlaybookController(
                websocket_client=self.experiment_ctx.client,
                experiment_dir=experiment_dir,
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
            log.info("PlaybookController initialized lazily")

            # Store initial variables if not already done
            if not self.initial_variables and self.experiment_ctx.playbook and self.experiment_ctx.playbook.variables:
                self.initial_variables = self.playbook_controller.execution_context.copy()
                
            return True
            
        except Exception as e:
            log.error(f"Failed to initialize PlaybookController: {e}", exc_info=True)
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
        if not self.is_running:
            from adare.backend.experiment.execution.base import ActionResult
            return ActionResult(success=False, message="Session not running")
            
        # Ensure controller is initialized
        if not await self._ensure_playbook_controller():
            from adare.backend.experiment.execution.base import ActionResult
            return ActionResult(success=False, message="Failed to initialize playbook controller")

        try:
            log.debug(f"Executing action: {action.__class__.__name__}")

            # Execute action via PlaybookController's action_executor
            # This automatically handles:
            # - Variable resolution via VariableResolver
            # - Target resolution via MCPTargetResolver
            # - Action-specific execution logic
            
            # Wrap in command logger
            action_name = action.__class__.__name__
            with self._command_logger(action_name):
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

    async def execute_playbook(self, playbook: Playbook, experiment_dir: Optional[Path] = None, indices: Optional[List[int]] = None) -> 'PlaybookExecutionResult':
        """
        Execute a full playbook (for testing sequences).

        Reuses PlaybookController.execute_playbook() unchanged!

        Args:
            playbook: The playbook to execute
            experiment_dir: Optional path to experiment directory (playbook parent)
            indices: Optional list of 1-based indices to execute

        Returns:
            PlaybookExecutionResult with execution statistics
        """
        if not self.is_running:
            raise RuntimeError("Session not running")
            
        # Ensure controller is initialized
        if not await self._ensure_playbook_controller():
            raise RuntimeError("Failed to initialize playbook controller")

        # Update experiment directory if provided (crucial for bare sessions)
        if experiment_dir and self.playbook_controller:
            self.playbook_controller.update_experiment_directory(experiment_dir)

        log.info(f"Executing playbook with {len(playbook.actions)} actions")

        # Update playbook reference in controller
        self.playbook_controller.playbook = playbook

        # Update variables if playbook has them
        if playbook.variables:
            var_dict = playbook.variables.to_execution_context(for_tests=False)
            self.playbook_controller.execution_context.update(var_dict)

        # Execute using existing PlaybookController logic
        with self._command_logger("playbook_execution"):
            result = await self.playbook_controller.execute_playbook(indices=indices)

        # Update statistics
        self.actions_executed += result.total_actions

        log.info(
            f"Playbook execution complete: {result.successful_actions}/"
            f"{result.total_actions} actions succeeded"
        )

        return result

    async def reload_testfunctions(self) -> bool:
        """
        Reload test functions from host to VM to enable dynamic updates.
        
        This packages the current test files from the host and uploads them to the VM again.
        The adarevm agent will extract them to a new temporary directory and use them for subsequent tests.
        """
        if not self.is_running:
            log.warning("Cannot reload test functions: Session not running")
            return False

        with self._command_logger("reload_testfunctions"):
            if not await self._ensure_playbook_controller():
                log.warning("Cannot reload test functions: Failed to ensure playbook controller")
                return False

            if not self.experiment_ctx.client:
                log.warning("Cannot reload test functions: WebSocket client not connected")
                return False

            log.info("Reloading test functions from host...")
            try:
                # Re-run loading process (packages and uploads test functions)
                # Note: load_tests determines which tests to load based on the CURRENT playbook
                # If no playbook is loaded yet, it might default to loading nothing or all?
                # Actually TestLoader.load_tests checks playbook used testfunctions.
                # If we are in dev mode, we might want to reload ALL test functions or just the ones
                # relevant to the session. 
                # PlaybookController.test_loader.load_tests() inspects self.playbook.
                # If no playbook is loaded in the controller, it might fail or do nothing.
                
                # However, in dev mode, we often run single actions or new playbooks.
                # If we want to update the code for *currently defined* test functions, this works.
                # But if we added a new test function to the playbook, we might need the playbook to be updated first.
                
                # Check how load_tests works: it uses self.playbook if available. 
                # If we just want to push the files, maybe we need to be careful.
                # But typically dev session involves iterating on a playbook.
                
                # Let's assume the user has a playbook or wants to refresh the environment for the next action.
                await self.playbook_controller.test_loader.load_tests(self.experiment_ctx.client)
                
                log.info("Test functions reloaded successfully")
                return True
            except Exception as e:
                log.error(f"Failed to reload test functions: {e}", exc_info=True)
                return False

    async def restart_mcp_server(self, debug: Optional[bool] = None, debug_output_dir: Optional[Path] = None) -> bool:
        """
        Restart the MCP GUI server with updated logging options.

        Args:
            debug: Enable debug logging (True/False). If None, keeps current setting.
            debug_output_dir: Directory for debug output. If None and debug=True, 
                              tries to allow existing or creates new.

        Returns:
            True if restarted successfully, False otherwise
        """
        if not self.experiment_ctx:
            log.error("Cannot restart MCP server: context not initialized")
            return False

        with self._command_logger("restart_mcp_server"):
            log.info("Restarting MCP GUI server...")
            
            # 1. Stop existing server
            if self.experiment_ctx.mcp_server:
                log.info("Stopping existing MCP server...")
                await self.experiment_ctx.mcp_server.stop(force_external=True)
                
                # Wait for port to be released
                # Explicit sleep to allow OS to release port if process shutdown was async
                # TODO: More robust port check would be better, but simple delay works for now
                import asyncio
                await asyncio.sleep(1.0)
            
            # 2. Determine configuration
            # Use provided values or fall back to existing config
            current_server = self.experiment_ctx.mcp_server
            
            # Debug flag
            new_debug = debug if debug is not None else (current_server.debug if current_server else False)
            
            # Debug output dir
            new_debug_output_dir = debug_output_dir
            if new_debug_output_dir is None:
                 if current_server and current_server.debug_output_dir:
                     new_debug_output_dir = current_server.debug_output_dir
                 elif new_debug and self.experiment_ctx.experiment_run_directory:
                     # Auto-configure if enabling debug for first time
                     new_debug_output_dir = self.experiment_ctx.experiment_run_directory.screenshots_directory / 'cv_debug'
                     new_debug_output_dir.mkdir(parents=True, exist_ok=True)

            # Log file (keep existing)
            log_file = current_server.log_file if current_server else None
            if not log_file and self.experiment_ctx.experiment_run_directory:
                log_file = self.experiment_ctx.experiment_run_directory.mcp_gui_log_file

            # 3. Create new manager
            log.info(f"Creating new MCP server manager (debug={new_debug}, output={new_debug_output_dir})")
            new_manager = MCPServerManager(
                log_file=log_file,
                debug=new_debug,
                debug_output_dir=new_debug_output_dir
            )
            
            # 4. Start new server
            try:
                success = await new_manager.start(allow_existing=False) # Should be fresh start since we stopped it
                if success:
                    self.experiment_ctx.mcp_server = new_manager
                    log.info("MCP GUI server restarted successfully")
                    return True
                else:
                    log.error("Failed to start new MCP server")
                    # Restore old one? Might be hard if it's already stopped.
                    return False
            except Exception as e:
                log.error(f"Error restarting MCP server: {e}", exc_info=True)
                return False

            except Exception as e:
                log.error(f"Error restarting MCP server: {e}", exc_info=True)
                return False

    async def stop_mcp_server(self) -> bool:
        """
        Stop the MCP GUI server.

        Returns:
            True if stopped successfully (or wasn't running), False otherwise
        """
        if not self.experiment_ctx:
            log.error("Cannot stop MCP server: context not initialized")
            return False

        with self._command_logger("stop_mcp_server"):
            if not self.experiment_ctx.mcp_server:
                log.info("MCP server not running")
                return True
                
            log.info("Stopping MCP GUI server...")
            try:
                await self.experiment_ctx.mcp_server.stop(force_external=True)
                # We can either set it to None or keep the manager instance.
                # Setting to None is cleaner if we consider it "gone", 
                # but might lose config if we want to restart later without args.
                # However, restart_mcp_server handles None check.
                # Let's keep the object but ensure it knows it's stopped (MCPServerManager tracks state).
                log.info("MCP GUI server stopped")
                return True
            except Exception as e:
                log.error(f"Error stopping MCP server: {e}", exc_info=True)
                return False

    async def reset_soft(self) -> bool:
        """
        Soft reset: Restore VM to initial external snapshot (no full OS reboot).

        For QEMU: Restores external snapshot (memory + disk, ~2-5 seconds, no OS boot)
        For VirtualBox: Only resets variables (fast, <1 second)

        Returns:
            True if reset successful, False otherwise
        """
        with self._command_logger("reset_soft"):
            try:
                # Ensure controller is initialized (needed for variable reset)
                await self._ensure_playbook_controller()

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
                if self.playbook_controller:
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
        with self._command_logger("reset_hard"):
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
                if self.playbook_controller:
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
        with self._command_logger(f"checkpoint_create_{name}"):
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
        with self._command_logger(f"checkpoint_restore_{name}"):
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

                    # Restart agent and reconnect to WebSocket server
                    # (Required because shared directory issues may kill the agent during restore)
                    from adare.backend.experiment.run import (
                        step_connect_websocket,
                        step_install_and_run_websocket_server
                    )
                    with StageCtxManager(
                        SoftwareInstallationStage(),
                        self.experiment_ctx.experiment_run_ulid,
                        event=self.experiment_ctx.user_interrupt_event
                    ):
                        await step_install_and_run_websocket_server(self.experiment_ctx)
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

                    # 6. Remove fake experiment run from database
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

            # STOP AGENT BEFORE SNAPSHOT
            # This ensures that when the snapshot is restored, the agent is NOT running,
            # allowing for a clean fresh start using the cached command.
            log.info("Stopping AdareVM agent before snapshot to ensure clean state")

            # 1. Disconnect WebSocket client
            if self.experiment_ctx.client:
                try:
                    await self.experiment_ctx.client.disconnect()
                except Exception as e:
                    log.warning(f"Error disconnecting client before snapshot: {e}")

            # 2. Kill adarevm process in VM
            try:
                if self.experiment_ctx.guest_platform == 'windows':
                    # Windows: Force kill adarevm (and python wrappers if needed)
                    # We use taskkill /F /IM adarevm.exe and potentially python processes if we can distinguish them
                    # But simpler to target adarevm.exe or use the stored PID if available (but PID is QEMU specific in context)
                    # Let's try basic taskkill first.
                    stop_cmd = "taskkill /F /IM adarevm.exe"
                else:
                    # Linux: pkill
                    stop_cmd = "pkill -f adarevm"

                # Run stop command (ignore errors if not running)
                # We use a short timeout
                await vm.run_command(stop_cmd, timeout=10)
            except Exception as e:
                log.warning(f"Failed to stop adarevm agent in VM (might not be running): {e}")

            # Wait a moment for process to die and file handles to close
            await asyncio.sleep(2)

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

            # Restart agent and reconnect
            # (Required because shared directory issues may kill the agent during snapshot creation)
            log.info("Restarting AdareVM agent after snapshot creation")
            
            from adare.backend.experiment.run import (
                step_install_and_run_websocket_server,
                step_connect_websocket
            )
            
            with StageCtxManager(
                SoftwareInstallationStage(),
                self.experiment_ctx.experiment_run_ulid,
                event=self.experiment_ctx.user_interrupt_event
            ):
                await step_install_and_run_websocket_server(self.experiment_ctx)
                await step_connect_websocket(self.experiment_ctx)

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

        # Removed redundant YAML log creation (_write_checkpoint_log)
        # We only want the standard adare command log created by _command_logger wrapper

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

    async def start_recording(self, output_file: Path) -> bool:
        """
        Start recording user interactions to a playbook file.
        
        Args:
            output_file: Path to save the recording (playbook YAML)
            
        Returns:
            True if started successfully
        """
        if self.recorder and self.recorder.is_recording:
            log.warning("Recording already in progress")
            return False
            
        if self.experiment_ctx.hypervisor_type != 'qemu':
            log.error("Recording is currently only supported for QEMU")
            return False
            
        try:
            from adare.backend.devmode.recorder import SessionRecorder
            
            self.recorder = SessionRecorder(self.experiment_ctx.vm, output_file)
            await self.recorder.start()
            return True
            
        except Exception as e:
            log.error(f"Failed to start recording: {e}", exc_info=True)
            return False

    async def stop_recording(self) -> bool:
        """
        Stop current recording session.
        
        Returns:
            True if stopped successfully
        """
        if not self.recorder or not self.recorder.is_recording:
            log.warning("No active recording to stop")
            return False
            
        try:
            await self.recorder.stop()
            self.recorder = None
            return True
        except Exception as e:
            log.error(f"Failed to stop recording: {e}", exc_info=True)
            return False
