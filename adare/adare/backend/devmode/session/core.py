"""
Core DevModeSession class with initialization, logging, and utility methods.

This module contains the base class with __init__, session logging,
JSON serialization helpers, and state query methods.
"""

import logging
from contextlib import contextmanager
from dataclasses import asdict, dataclass, is_dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from adare.backend.experiment.playbook_controller import PlaybookController
from adare.backend.experiment.runctx import ExperimentRunCtx
from adare.backend.experiment.stagectxmanager import StageCtxManager
from adare.backend.experiment.vm_lifecycle_manager import VMLifecycleManager
from adare.core.result import Result
from adare.exceptions import LoggedErrorException
from adare.types.stages import Stage

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
    variable_state: dict[str, Any]
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
    current_variables: dict[str, Any]
    available_snapshots: list[DevModeSnapshot]
    experiment_name: str | None = None


class DevModeSessionCore:
    """
    Core mixin for DevModeSession providing initialization, logging, and utilities.

    All instance attributes are defined here in __init__.
    Other mixins access these attributes via self.
    """

    def __init__(
        self,
        session_id: str,
        project_path: Path,
        environment_name: str,
        gui_mode: str | None = None,
        vm_memory: int | None = None,
        vm_cpus: int | None = None,
        debug_screenshots: bool = False,
        console_ulid: str | None = None,
        experiment_name: str | None = None,
        shared_directories: dict[str, dict[str, Path]] | None = None
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
        self.experiment_ctx: ExperimentRunCtx | None = None
        self.playbook_controller: PlaybookController | None = None
        self.vm_manager: VMLifecycleManager | None = None
        self.vm_instance_id: str | None = None  # Track VM instance for cleanup

        # Dev mode specific state
        self.snapshots: list[DevModeSnapshot] = []
        self.actions_executed: int = 0
        self.started_at: datetime | None = None
        self.is_running: bool = False
        self.run_directory_path: Path | None = None  # Stored after run dir creation

        # Store initial variable state for reset operations
        self.initial_variables: dict[str, Any] = {}

        # Session-level log handler
        self.session_log_handler: logging.Handler | None = None

        # Recording state
        self.recorder: any | None = None  # SessionRecorder instance

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

        except OSError as e:
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
            except OSError as e:
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
            return [DevModeSessionCore._make_json_serializable(x) for x in obj]
        if isinstance(obj, dict):
            return {str(k): DevModeSessionCore._make_json_serializable(v) for k, v in obj.items()}
        if is_dataclass(obj):
            return DevModeSessionCore._make_json_serializable(asdict(obj))
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

    async def _ensure_playbook_controller(self) -> Result[None]:
        """
        Lazily initialize the PlaybookController if it doesn't exist.

        Returns:
            Result[None] with success or error information
        """
        if self.playbook_controller:
            return Result.ok(None)

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

            return Result.ok(None)

        except (AttributeError, TypeError) as e:
            log.error(f"Failed to initialize PlaybookController: {e}", exc_info=True)
            return Result.fail("CONTROLLER_INIT_FAILED", f"Failed to initialize PlaybookController: {e}")
        except LoggedErrorException as e:
            log.error(f"Failed to initialize PlaybookController: {e}", exc_info=True)
            return Result.fail("CONTROLLER_INIT_FAILED", f"Failed to initialize PlaybookController: {e}")

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
