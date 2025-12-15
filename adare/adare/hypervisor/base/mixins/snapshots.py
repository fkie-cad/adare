"""
Abstract snapshot operations mixin for hypervisor VMs.

All hypervisor implementations must provide snapshot functionality.
"""
import logging
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Optional

log = logging.getLogger(__name__)


class AbstractSnapshotMixin(ABC):
    """
    Abstract mixin class defining snapshot operations for VMs.

    All hypervisor implementations must implement these snapshot operations.
    """

    @abstractmethod
    def create_snapshot(
        self,
        snapshot_name: str,
        description: str = "",
        ctx_manager=None,
        stop_event=None,
        log_file: Optional[Path] = None,
        silent: bool = False
    ):
        """
        Create a snapshot of the VM.

        Args:
            snapshot_name: Name for the snapshot
            description: Optional description of the snapshot
            ctx_manager: Optional context manager for status updates
            stop_event: Optional threading event to signal cancellation
            log_file: Optional path to log file for command output
            silent: If True, suppress log output

        Returns:
            Return code (0 for success, non-zero for failure)
        """
        pass

    @abstractmethod
    def snapshot_exists(self, snapshot_name: str) -> bool:
        """
        Check if a snapshot exists for the VM.

        Args:
            snapshot_name: Name of the snapshot to check

        Returns:
            True if snapshot exists, False otherwise
        """
        pass

    @abstractmethod
    def restore_snapshot(
        self,
        snapshot_name: str,
        ctx_manager=None,
        stop_event=None,
        log_file: Optional[Path] = None,
        silent: bool = False
    ) -> bool:
        """
        Restore a snapshot for the VM.

        Args:
            snapshot_name: Name of the snapshot to restore
            ctx_manager: Optional context manager for status updates
            stop_event: Optional threading event to signal cancellation
            log_file: Optional path to log file for command output
            silent: If True, suppress log output

        Returns:
            True if restoration successful, False otherwise
        """
        pass

    @abstractmethod
    def delete_snapshot(
        self,
        snapshot_name: str,
        ctx_manager=None,
        stop_event=None,
        log_file: Optional[Path] = None,
        silent: bool = False
    ) -> bool:
        """
        Delete a snapshot from the VM.

        Args:
            snapshot_name: Name of the snapshot to delete
            ctx_manager: Optional context manager for status updates
            stop_event: Optional threading event to signal cancellation
            log_file: Optional path to log file for command output
            silent: If True, suppress log output

        Returns:
            True if deletion successful, False otherwise
        """
        pass

    @abstractmethod
    async def ensure_initial_snapshot(
        self,
        ovf_path: str,
        snapshot_name: str,
        snapshot_description: str = ""
    ):
        """
        Ensure the VM exists and has an initial snapshot.

        This method:
        1. Creates VM from OVF if it doesn't exist
        2. Creates initial snapshot if it doesn't exist
        3. Restores to initial snapshot if it exists

        Args:
            ovf_path: Path to OVF/OVA file
            snapshot_name: Name for the initial snapshot
            snapshot_description: Optional description for the snapshot
        """
        pass
