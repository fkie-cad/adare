"""
Executors for simple playbook actions (GUI interactions and system operations).

Includes: click, drag, keyboard, idle, scroll, goto, screenshot, command,
save_timestamp, and pull actions.

The actual action methods are organized into mixins:
- GUIActionsMixin: click, drag, keyboard, idle, scroll, goto, screenshot
- DataActionsMixin: command, save_timestamp, save_variable, pull
- FilesystemActionsMixin: snapshot_filesystem, pull_changed_files
"""

import logging
import re
from pathlib import Path

from .base import ActionResult  # noqa: F401 - re-exported for backward compatibility
from .data_actions import DataActionsMixin
from .filesystem_actions import FilesystemActionsMixin
from .gui_actions import GUIActionsMixin

log = logging.getLogger(__name__)


def sanitize_filename(name: str) -> str:
    """
    Sanitize filename to remove invalid characters and ensure safety.

    Args:
        name: Desired filename (without extension)

    Returns:
        Sanitized filename safe for filesystem use
    """
    # Remove or replace invalid characters
    sanitized = re.sub(r'[<>:"/\\|?*\x00-\x1f]', '_', name)
    # Remove leading/trailing whitespace and dots
    sanitized = sanitized.strip(' .')
    # Limit length to 200 characters (leaves room for extension and path)
    sanitized = sanitized[:200]
    # If empty after sanitization, use fallback
    if not sanitized:
        sanitized = 'screenshot'
    return sanitized


class SimpleActionsExecutor(GUIActionsMixin, DataActionsMixin, FilesystemActionsMixin):
    """Handles execution of simple playbook actions (GUI and system operations)."""

    def __init__(self, websocket_client, target_resolution_executor, experiment_run_id: str | None = None,
                 playbook = None, execution_context: dict = None, vm = None,
                 experiment_run_directory: Path | None = None):
        """
        Initialize simple actions executor.

        Args:
            websocket_client: Connected WebSocket client to adarevm
            target_resolution_executor: Target resolution executor for finding targets
            experiment_run_id: Experiment run ID for event emission
            playbook: Playbook reference for variable access
            execution_context: Execution context for variable resolution
            vm: VM instance for file operations and GUI execution mode
            experiment_run_directory: Run directory for artifacts
        """
        self.client = websocket_client
        self.target_resolution = target_resolution_executor
        self.experiment_run_id = experiment_run_id
        self.playbook = playbook
        self.execution_context = execution_context if execution_context is not None else {}
        self.vm = vm
        self.experiment_run_directory = experiment_run_directory
        self.explicit_screenshot_counter = 0  # Counter for explicit screenshot actions
        self.custom_screenshot_counters = {}  # Track counters for custom screenshot names

        # Initialize GUI executor based on VM type and playbook settings
        from .gui_executor_factory import create_gui_executor, resolve_gui_execution_mode
        playbook_settings = playbook.settings if playbook and hasattr(playbook, 'settings') else None
        # Get CLI override from config if available
        cli_override = None
        if execution_context and 'config' in execution_context:
            config = execution_context['config']
            if config and hasattr(config, 'gui_mode_override'):
                cli_override = config.gui_mode_override
        gui_mode = resolve_gui_execution_mode(vm, playbook_settings, cli_override=cli_override)
        self.gui_executor = create_gui_executor(
            mode=gui_mode,
            websocket_client=websocket_client,
            vm=vm,
            target_resolution_executor=target_resolution_executor,
            experiment_run_id=experiment_run_id,
            playbook=playbook,
            execution_context=execution_context,
            experiment_run_directory=experiment_run_directory
        )
        log.info(f"SimpleActionsExecutor initialized with GUI mode: {gui_mode.value}")

    def _resolve_pull_mode(self, requested_mode: str) -> str:
        """Resolve effective pull mode based on VM type and requested mode.

        QEMU's copy_from_guest uses libguestfs which requires a stopped VM,
        so 'hypervisor' mode can't work during execution. Auto-switch to 'websocket'.
        VirtualBox's copy_from_guest works on running VMs, so 'hypervisor' is fine.
        """
        if requested_mode == 'hypervisor' and self._is_qemu_vm():
            log.debug("Auto-switching pull mode from 'hypervisor' to 'websocket' (QEMU VM)")
            return 'websocket'
        return requested_mode

    def _is_qemu_vm(self) -> bool:
        """Check if current VM is a QEMU instance."""
        from adare.hypervisor.qemu.vm import QEMUVM
        return isinstance(self.vm, QEMUVM)

    def get_click_handler(self, click_type: str):
        """Get the appropriate click handler based on click type."""
        # Delegate to GUI executor
        return lambda x, y: self.gui_executor.click(x, y, click_type)

    def _process_capture(self, capture_spec, command_result):
        """
        Process command output capture based on capture specification.

        Args:
            capture_spec: CaptureSpec object defining what to capture
            command_result: Result dict from execute_shell containing stdout, stderr, returncode

        Returns:
            Captured and optionally parsed value

        Raises:
            ValueError: If capture processing fails
        """

        # Extract the output based on source
        if capture_spec.source == 'stdout':
            raw_output = command_result.get('stdout', '')
        elif capture_spec.source == 'stderr':
            raw_output = command_result.get('stderr', '')
        elif capture_spec.source == 'returncode':
            raw_output = command_result.get('returncode', -1)
        elif capture_spec.source == 'all':
            raw_output = {
                'stdout': command_result.get('stdout', ''),
                'stderr': command_result.get('stderr', ''),
                'returncode': command_result.get('returncode', -1)
            }
        else:
            raise ValueError(f"Invalid capture source: {capture_spec.source}")

        # If no parser specified, strip whitespace from string outputs for cleaner variable usage
        if not capture_spec.parser:
            # Auto-strip stdout/stderr to avoid trailing newlines in variable substitution
            if capture_spec.source in ('stdout', 'stderr') and isinstance(raw_output, str):
                return raw_output.strip()
            return raw_output

        # Apply parser expression (user has full control with parser)
        return self._evaluate_parser(capture_spec.parser, raw_output)

    def _evaluate_parser(self, parser_expr: str, raw_output):
        """
        Safely evaluate parser expression with restricted context.

        Args:
            parser_expr: Python expression to evaluate
            raw_output: The output value to parse

        Returns:
            Parsed value

        Raises:
            ValueError: If parser evaluation fails
        """
        import json
        import re

        # Create safe evaluation context
        safe_context = {
            'output': raw_output,
            # Safe utilities
            'json': json,
            're': re,
            'int': int,
            'float': float,
            'str': str,
            'bool': bool,
            'len': len,
            'range': range,
            'enumerate': enumerate,
            'zip': zip,
            'list': list,
            'dict': dict,
            'tuple': tuple,
            'set': set,
            # String methods are available through output.strip(), etc.
        }

        try:
            # Evaluate the parser expression in safe context
            result = eval(parser_expr, {"__builtins__": {}}, safe_context)
            log.debug(f"Parser evaluation successful: '{parser_expr}' -> {result}")
            return result
        except SyntaxError as e:
            raise ValueError(f"Parser syntax error: {e}")
        except NameError as e:
            raise ValueError(f"Parser references undefined name: {e}")
        except Exception as e:
            raise ValueError(f"Parser evaluation failed: {e}")
