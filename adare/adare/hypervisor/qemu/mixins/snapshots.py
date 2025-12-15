"""
QEMU VM snapshot operations mixin.

Implements AbstractSnapshotMixin for QEMU using qcow2 internal snapshots.
"""
import logging
import subprocess
from pathlib import Path
from typing import Optional

from adare.hypervisor.base.mixins.snapshots import AbstractSnapshotMixin
from adare.hypervisor.exceptions import HypervisorException, SnapshotNotFoundException

log = logging.getLogger(__name__)


class SnapshotMixin(AbstractSnapshotMixin):
    """Mixin class providing snapshot operations for QEMU VMs using qcow2 format."""

    def create_snapshot(
        self,
        snapshot_name: str,
        description: str = "",
        ctx_manager=None,
        stop_event=None,
        log_file: Optional[Path] = None,
        silent: bool = False
    ) -> int:
        """
        Create a qcow2 internal snapshot.

        VM must be stopped for snapshot operations.

        Args:
            snapshot_name: Name for the snapshot
            description: Optional description (stored in snapshot metadata)
            ctx_manager: Optional context manager for status updates
            stop_event: Optional threading event to signal cancellation
            log_file: Optional path to log file
            silent: If True, suppress log output

        Returns:
            Return code (0 for success, non-zero for failure)
        """
        if not silent:
            log.info(f"CLAUDE: Creating snapshot '{snapshot_name}' for VM '{self.vm_name}'")

        # Ensure VM is stopped
        if self.get_state() != "poweroff":
            log.error("CLAUDE: VM must be stopped to create snapshot")
            return 1

        if not hasattr(self, 'config') or not self.config.disk_path:
            log.error("CLAUDE: VM config or disk_path not available")
            return 1

        from adare.config import HYPERVISOR_CONFIGS
        qemu_img_exe = HYPERVISOR_CONFIGS.get('qemu', {}).get('qemu_img_exe', 'qemu-img')

        # Build qemu-img snapshot command
        args = [qemu_img_exe, 'snapshot', '-c', snapshot_name, self.config.disk_path]

        try:
            result = subprocess.run(
                args,
                capture_output=True,
                text=True,
                check=False
            )

            if result.returncode == 0:
                if not silent:
                    log.info(f"CLAUDE: Successfully created snapshot '{snapshot_name}'")
            else:
                log.error(f"CLAUDE: Failed to create snapshot: {result.stderr}")

            if log_file:
                with open(log_file, 'a') as f:
                    f.write(f"qemu-img snapshot create: {result.stdout}\n{result.stderr}\n")

            return result.returncode

        except Exception as e:
            log.error(f"CLAUDE: Error creating snapshot: {e}")
            return 1

    def snapshot_exists(self, snapshot_name: str) -> bool:
        """
        Check if a qcow2 snapshot exists.

        Args:
            snapshot_name: Name of the snapshot to check

        Returns:
            True if snapshot exists, False otherwise
        """
        if not hasattr(self, 'config') or not self.config.disk_path:
            log.error("CLAUDE: VM config or disk_path not available")
            return False

        from adare.config import HYPERVISOR_CONFIGS
        qemu_img_exe = HYPERVISOR_CONFIGS.get('qemu', {}).get('qemu_img_exe', 'qemu-img')

        # List snapshots
        args = [qemu_img_exe, 'snapshot', '-l', self.config.disk_path]

        try:
            result = subprocess.run(
                args,
                capture_output=True,
                text=True,
                check=False
            )

            if result.returncode == 0:
                # Parse output to find snapshot
                for line in result.stdout.splitlines():
                    # Snapshot format: "ID TAG VM SIZE DATE VM CLOCK"
                    # We look for lines containing our snapshot name
                    if snapshot_name in line:
                        log.debug(f"CLAUDE: Snapshot '{snapshot_name}' exists")
                        return True

                log.debug(f"CLAUDE: Snapshot '{snapshot_name}' does not exist")
                return False
            else:
                log.error(f"CLAUDE: Failed to list snapshots: {result.stderr}")
                return False

        except Exception as e:
            log.error(f"CLAUDE: Error checking snapshot existence: {e}")
            return False

    def restore_snapshot(
        self,
        snapshot_name: str,
        ctx_manager=None,
        stop_event=None,
        log_file: Optional[Path] = None,
        silent: bool = False
    ) -> bool:
        """
        Restore a qcow2 snapshot.

        VM must be stopped for snapshot operations.

        Args:
            snapshot_name: Name of the snapshot to restore
            ctx_manager: Optional context manager for status updates
            stop_event: Optional threading event to signal cancellation
            log_file: Optional path to log file
            silent: If True, suppress log output

        Returns:
            True if restoration successful, False otherwise
        """
        if not silent:
            log.info(f"CLAUDE: Restoring snapshot '{snapshot_name}' for VM '{self.vm_name}'")

        # Ensure VM is stopped
        if self.get_state() != "poweroff":
            log.error("CLAUDE: VM must be stopped to restore snapshot")
            return False

        if not self.snapshot_exists(snapshot_name):
            log.error(f"CLAUDE: Snapshot '{snapshot_name}' does not exist")
            return False

        if not hasattr(self, 'config') or not self.config.disk_path:
            log.error("CLAUDE: VM config or disk_path not available")
            return False

        from adare.config import HYPERVISOR_CONFIGS
        qemu_img_exe = HYPERVISOR_CONFIGS.get('qemu', {}).get('qemu_img_exe', 'qemu-img')

        # Build qemu-img snapshot restore command
        args = [qemu_img_exe, 'snapshot', '-a', snapshot_name, self.config.disk_path]

        try:
            result = subprocess.run(
                args,
                capture_output=True,
                text=True,
                check=False
            )

            if result.returncode == 0:
                if not silent:
                    log.info(f"CLAUDE: Successfully restored snapshot '{snapshot_name}'")
                return True
            else:
                log.error(f"CLAUDE: Failed to restore snapshot: {result.stderr}")
                return False

        except Exception as e:
            log.error(f"CLAUDE: Error restoring snapshot: {e}")
            return False

    def delete_snapshot(
        self,
        snapshot_name: str,
        ctx_manager=None,
        stop_event=None,
        log_file: Optional[Path] = None,
        silent: bool = False
    ) -> bool:
        """
        Delete a qcow2 snapshot.

        VM must be stopped for snapshot operations.

        Args:
            snapshot_name: Name of the snapshot to delete
            ctx_manager: Optional context manager for status updates
            stop_event: Optional threading event to signal cancellation
            log_file: Optional path to log file
            silent: If True, suppress log output

        Returns:
            True if deletion successful, False otherwise
        """
        if not silent:
            log.info(f"CLAUDE: Deleting snapshot '{snapshot_name}' for VM '{self.vm_name}'")

        # Ensure VM is stopped
        if self.get_state() != "poweroff":
            log.error("CLAUDE: VM must be stopped to delete snapshot")
            return False

        if not self.snapshot_exists(snapshot_name):
            log.warning(f"CLAUDE: Snapshot '{snapshot_name}' does not exist, nothing to delete")
            return True  # Consider it success if already gone

        if not hasattr(self, 'config') or not self.config.disk_path:
            log.error("CLAUDE: VM config or disk_path not available")
            return False

        from adare.config import HYPERVISOR_CONFIGS
        qemu_img_exe = HYPERVISOR_CONFIGS.get('qemu', {}).get('qemu_img_exe', 'qemu-img')

        # Build qemu-img snapshot delete command
        args = [qemu_img_exe, 'snapshot', '-d', snapshot_name, self.config.disk_path]

        try:
            result = subprocess.run(
                args,
                capture_output=True,
                text=True,
                check=False
            )

            if result.returncode == 0:
                if not silent:
                    log.info(f"CLAUDE: Successfully deleted snapshot '{snapshot_name}'")
                return True
            else:
                log.error(f"CLAUDE: Failed to delete snapshot: {result.stderr}")
                return False

        except Exception as e:
            log.error(f"CLAUDE: Error deleting snapshot: {e}")
            return False

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
        log.info(f"CLAUDE: Ensuring initial snapshot '{snapshot_name}' for VM '{self.vm_name}'")

        # Check if VM exists
        if not self.vm_exists():
            log.info(f"CLAUDE: VM '{self.vm_name}' does not exist, importing from '{ovf_path}'")
            await self.create_from_ovf_or_ova(ovf_path, silent=False)

        # Ensure VM is stopped
        state = self.get_state()
        if state == "running":
            log.info("CLAUDE: Stopping VM to manage snapshots")
            await self.stop()

        # Check if snapshot exists
        if self.snapshot_exists(snapshot_name):
            log.info(f"CLAUDE: Snapshot '{snapshot_name}' exists, restoring")
            success = self.restore_snapshot(snapshot_name, silent=False)
            if not success:
                raise HypervisorException(f"Failed to restore snapshot '{snapshot_name}'")
        else:
            log.info(f"CLAUDE: Snapshot '{snapshot_name}' does not exist, creating")
            returncode = self.create_snapshot(snapshot_name, description=snapshot_description, silent=False)
            if returncode != 0:
                raise HypervisorException(f"Failed to create snapshot '{snapshot_name}'")

        log.info(f"CLAUDE: Initial snapshot '{snapshot_name}' ensured for VM '{self.vm_name}'")
