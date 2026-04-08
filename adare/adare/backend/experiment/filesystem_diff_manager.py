"""
Filesystem Diff Manager for experiment execution.

Manages filesystem snapshot capture and diff computation during experiments.
Extracts snapshot/diff logic from PlaybookController for cleaner separation.
"""

import logging
import shutil
from pathlib import Path
from typing import Optional, Dict, Any

from adare.backend.experiment.filesystem_snapshot import (
    FilesystemSnapshot, calculate_diff, export_diff_json, export_diff_csv, export_diff_bodyfile
)

log = logging.getLogger(__name__)


class FilesystemDiffManager:
    """Manages filesystem snapshot capture and diff during experiment execution."""

    def __init__(
        self,
        vm: Optional[Any],
        execution_context: Dict[str, Any],
        experiment_run_directory: Optional[Path],
        action_executor: Any,
    ):
        """
        Initialize the filesystem diff manager.

        Args:
            vm: VM instance (used to detect hypervisor type)
            execution_context: Shared execution context dict (stores snapshot variables)
            experiment_run_directory: Run directory for artifact export
            action_executor: ActionExecutor for executing snapshot actions
        """
        self.vm = vm
        self.execution_context = execution_context
        self.experiment_run_directory = experiment_run_directory
        self.action_executor = action_executor

    # ------------------------------------------------------------------
    # Mode detection / resolution
    # ------------------------------------------------------------------

    def determine_diff_enabled(self, playbook: Any) -> bool:
        """Determine if filesystem diff should run (CLI > playbook).

        Args:
            playbook: The parsed Playbook object (checked for settings)

        Returns:
            True if diff is enabled
        """
        config = self.execution_context.get('config')
        if config and hasattr(config, 'enable_diff') and config.enable_diff is not None:
            return config.enable_diff  # CLI override

        # Fall back to playbook setting
        if hasattr(playbook, 'settings') and playbook.settings:
            return playbook.settings.enable_filesystem_diff

        return False

    def resolve_diff_mode(self) -> str:
        """Resolve diff mode: auto -> guest/host based on capabilities.

        Returns:
            'guest' or 'host'
        """
        config = self.execution_context.get('config')
        requested_mode = getattr(config, 'diff_mode', 'auto') if config else 'auto'

        if requested_mode == 'auto':
            # Smart selection based on hypervisor and tool availability
            if self._is_qemu_vm():
                if self._is_virt_diff_available():
                    log.info("Auto mode: Using host-side diff (QEMU + virt-diff available)")
                    return 'host'
                else:
                    log.warning("Auto mode: virt-diff not found, falling back to guest-side diff")
                    log.warning("For faster diffs, install: sudo apt-get install libguestfs-tools")
                    return 'guest'
            else:
                log.debug("Auto mode: Using guest-side diff (non-QEMU hypervisor)")
                return 'guest'

        return requested_mode

    def validate_host_mode_support(self):
        """Validate that host mode is supported (QEMU + virt-diff).

        Raises:
            LoggedException: If host mode requirements are not met
        """
        if not self._is_qemu_vm():
            from adare.exceptions import LoggedException
            raise LoggedException(
                log,
                f"Host-side diff (--diff-mode=host) requires QEMU hypervisor. "
                f"Current hypervisor: {self.vm.__class__.__name__ if self.vm else 'unknown'}. "
                f"Use --diff-mode=guest or switch to QEMU environment."
            )

        if not self._is_virt_diff_available():
            from adare.exceptions import LoggedException
            raise LoggedException(
                log,
                "Host-side diff requires libguestfs-tools but guestfish not found.\n"
                "Installation: sudo apt-get install libguestfs-tools\n"
                "Alternative: Use --diff-mode=guest for VM-based diff."
            )

    # ------------------------------------------------------------------
    # Snapshot capture
    # ------------------------------------------------------------------

    async def capture_automatic_snapshot(self, variable_name: str) -> Optional[FilesystemSnapshot]:
        """
        Capture filesystem snapshot programmatically (for automatic diff).

        Args:
            variable_name: Variable name to store snapshot (internal, starts with _)

        Returns:
            FilesystemSnapshot object, or None if capture failed
        """
        from adare.types.playbook import SnapshotFilesystemAction

        try:
            # Create programmatic snapshot action
            snapshot_action = SnapshotFilesystemAction(
                variable=variable_name,
                timeout=300.0,  # 5 minute timeout
                description="Automatic snapshot for filesystem diff"
            )

            # Execute via simple actions executor
            result = await self.action_executor.simple_actions.execute_snapshot_filesystem(
                snapshot_action,
                parent_event_id=None,
                event_emitter=None
            )

            if not result.success:
                log.error(f"Failed to capture automatic snapshot: {result.message}")
                return None

            # Retrieve snapshot from execution context
            snapshot = self.execution_context.get(variable_name)
            if not snapshot or not isinstance(snapshot, FilesystemSnapshot):
                log.error(f"Snapshot variable '{variable_name}' not found or invalid type")
                return None

            return snapshot

        except (KeyError, TypeError, ValueError) as e:
            log.error(f"Error capturing automatic snapshot: {e}", exc_info=True)
            return None

    # ------------------------------------------------------------------
    # Diff export
    # ------------------------------------------------------------------

    async def capture_and_export_diff(
        self,
        initial_snapshot: FilesystemSnapshot,
        final_variable: str,
    ):
        """
        Capture final snapshot, calculate diff, and export to files.

        Args:
            initial_snapshot: Initial snapshot captured at experiment start
            final_variable: Variable name for final snapshot
        """
        try:
            # Capture final snapshot
            final_snapshot = await self.capture_automatic_snapshot(final_variable)
            if not final_snapshot:
                log.error("Failed to capture final filesystem snapshot - diff export skipped")
                return

            # Calculate diff
            log.info("Calculating filesystem diff...")
            diff = calculate_diff(initial_snapshot, final_snapshot)

            log.info(
                f"Filesystem changes detected - "
                f"Added: {len(diff['added'])}, "
                f"Removed: {len(diff['removed'])}, "
                f"Modified: {len(diff['modified'])}"
            )

            # Determine output directory (artifacts folder in run directory)
            if not self.experiment_run_directory:
                log.warning("No experiment run directory set - cannot export filesystem diff")
                return

            artifacts_dir = self.experiment_run_directory / 'artifacts'
            artifacts_dir.mkdir(parents=True, exist_ok=True)

            # Prepare metadata for JSON export
            tool_name = 'MFTReader' if initial_snapshot.os_type == 'Windows' else 'LinuxFSSnapshot'
            metadata = {
                'diff_mode': 'guest',
                'tool': tool_name,
                'initial_snapshot_time': initial_snapshot.timestamp,
                'final_snapshot_time': final_snapshot.timestamp,
                'os_type': initial_snapshot.os_type,
                'experiment_run_directory': str(self.experiment_run_directory)
            }

            # Export JSON
            json_path = artifacts_dir / 'filesystem_diffs.json'
            export_diff_json(diff, json_path, metadata)

            # Export CSV
            csv_path = artifacts_dir / 'filesystem_diffs.csv'
            export_diff_csv(diff, csv_path)

            # Export bodyfile (mactime format for forensic tools)
            bodyfile_path = artifacts_dir / 'filesystem_diffs.bodyfile'
            export_diff_bodyfile(diff, bodyfile_path, initial_snapshot, final_snapshot)

            log.info(f"Filesystem diff exported to {artifacts_dir}")

        except (KeyError, TypeError, ValueError, OSError) as e:
            log.error(f"Error exporting filesystem diff: {e}", exc_info=True)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _is_qemu_vm(self) -> bool:
        """Check if VM is QEMU."""
        if not self.vm:
            return False
        return self.vm.__class__.__name__ == 'QEMUVM'

    def _is_virt_diff_available(self) -> bool:
        """Check if libguestfs virt-diff is installed."""
        return shutil.which('guestfish') is not None
