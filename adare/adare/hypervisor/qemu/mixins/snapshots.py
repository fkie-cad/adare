"""
QEMU VM external snapshot operations mixin.

Implements external libvirt snapshots for dev mode checkpoints.
Uses virsh to create external snapshots with separate memory and disk files.

External snapshot approach:
- Memory state saved to external .save file
- Disk state saved to external .qcow2 overlay
- Metadata tracked in database (not libvirt)
- Better reliability and persistence than internal snapshots
"""
import logging
import subprocess
import os
from pathlib import Path
from typing import Optional, Tuple

from adare.hypervisor.base.mixins.snapshots import AbstractSnapshotMixin
from adare.hypervisor.exceptions import HypervisorException, SnapshotNotFoundException

log = logging.getLogger(__name__)


class SnapshotMixin(AbstractSnapshotMixin):
    """Mixin class providing external snapshot operations for QEMU VMs using virsh."""

    def _get_snapshot_storage_dir(self) -> Path:
        """
        Compute snapshot storage directory from VM disk path.

        For VM disk at /path/to/vm.qcow2, returns /path/to/vm/snapshots/

        Returns:
            Path to snapshot storage directory
        """
        if not hasattr(self, 'config') or not self.config.disk_path:
            raise HypervisorException("VM config or disk_path not available")

        disk_path = Path(self.config.disk_path)
        vm_name = disk_path.stem  # Get filename without extension
        parent_dir = disk_path.parent

        snapshot_dir = parent_dir / vm_name / "snapshots"
        return snapshot_dir

    def _ensure_snapshot_dir(self, dir_path: Path) -> None:
        """
        Create snapshot directory if it doesn't exist.

        Args:
            dir_path: Directory to create
        """
        try:
            dir_path.mkdir(parents=True, exist_ok=True)
            log.debug(f"CLAUDE: Ensured snapshot directory: {dir_path}")
        except OSError as e:
            raise HypervisorException(f"Failed to create snapshot directory {dir_path}: {e}")

    def _check_guest_agent(self) -> bool:
        """
        Check if QEMU guest agent is running in the VM.

        Returns:
            True if guest agent is available, False otherwise
        """
        try:
            result = subprocess.run(
                ['virsh', 'qemu-agent-command', self.vm_name, '{"execute":"guest-ping"}'],
                capture_output=True,
                text=True,
                timeout=2,
                check=False
            )
            return result.returncode == 0
        except (subprocess.TimeoutExpired, FileNotFoundError):
            return False

    def create_external_snapshot(
        self,
        snapshot_name: str,
        memory_path: str,
        disk_path: str,
        use_quiesce: bool = True
    ) -> bool:
        """
        Create an external libvirt snapshot with separate memory and disk files.

        Args:
            snapshot_name: Libvirt snapshot name
            memory_path: Path for external memory save file
            disk_path: Path for external disk overlay file
            use_quiesce: Whether to use guest agent to quiesce filesystem (default True)

        Returns:
            True if snapshot created successfully, False otherwise
        """
        log.info(f"CLAUDE: Creating external snapshot '{snapshot_name}' for VM '{self.vm_name}'")

        # Ensure VM is running for live snapshot
        if self.get_state() != "running":
            log.error("CLAUDE: VM must be running to create live snapshot")
            return False

        # Ensure snapshot directory exists
        snapshot_dir = Path(memory_path).parent
        self._ensure_snapshot_dir(snapshot_dir)

        # Check for guest agent if quiesce requested
        if use_quiesce:
            log.warning("CLAUDE: Quiesce incompatible with memory snapshots. Disabling quiesce.")
            use_quiesce = False

        # Build virsh snapshot-create-as command
        args = [
            'virsh', 'snapshot-create-as',
            '--domain', self.vm_name,
            '--name', snapshot_name,
            '--live',
            '--memspec', f'file={memory_path},snapshot=external',
            '--diskspec', f'vda,snapshot=external,file={disk_path}',
            '--atomic'
        ]

        if use_quiesce:
            args.append('--quiesce')

        try:
            result = subprocess.run(
                args,
                capture_output=True,
                text=True,
                check=False
            )

            if result.returncode == 0:
                log.info(f"CLAUDE: Successfully created external snapshot '{snapshot_name}'")
                log.debug(f"CLAUDE: Memory file: {memory_path}")
                log.debug(f"CLAUDE: Disk file: {disk_path}")
                return True
            else:
                log.error(f"CLAUDE: Failed to create external snapshot: {result.stderr}")
                return False

        except FileNotFoundError:
            log.error("CLAUDE: virsh command not found - ensure libvirt is installed")
            return False
        except Exception as e:
            log.error(f"CLAUDE: Error creating external snapshot: {e}")
            return False

    def restore_external_snapshot(
        self,
        memory_path: str,
        disk_path: str
    ) -> bool:
        """
        Restore VM from external snapshot files.

        This involves:
        1. Stop VM (virsh destroy)
        2. Update disk to snapshot overlay (virt-xml)
        3. Restore memory state (virsh restore)

        Args:
            memory_path: Path to external memory save file
            disk_path: Path to external disk overlay file

        Returns:
            True if restoration successful, False otherwise
        """
        log.info(f"CLAUDE: Restoring external snapshot for VM '{self.vm_name}'")
        log.debug(f"CLAUDE: Memory file: {memory_path}")
        log.debug(f"CLAUDE: Disk file: {disk_path}")

        # Verify files exist
        if not os.path.exists(memory_path):
            log.error(f"CLAUDE: Memory file not found: {memory_path}")
            return False
        if not os.path.exists(disk_path):
            log.error(f"CLAUDE: Disk file not found: {disk_path}")
            return False

        try:
            # Step 1: Stop VM forcefully
            log.debug("CLAUDE: Stopping VM")
            destroy_result = subprocess.run(
                ['virsh', 'destroy', self.vm_name],
                capture_output=True,
                text=True,
                check=False
            )

            # It's okay if destroy fails (VM might already be stopped)
            if destroy_result.returncode != 0:
                log.debug(f"CLAUDE: VM destroy returned non-zero (may already be stopped): {destroy_result.stderr}")

            # Step 2: Update disk path to snapshot overlay
            log.debug("CLAUDE: Updating disk path to snapshot overlay")
            virt_xml_result = subprocess.run(
                ['virt-xml', self.vm_name, '--edit', '--disk', f'path={disk_path}'],
                capture_output=True,
                text=True,
                check=False
            )

            if virt_xml_result.returncode != 0:
                log.error(f"CLAUDE: Failed to update disk path: {virt_xml_result.stderr}")
                return False

            # Step 3: Restore memory state (VM will resume immediately)
            log.debug("CLAUDE: Restoring memory state")
            restore_result = subprocess.run(
                ['virsh', 'restore', memory_path],
                capture_output=True,
                text=True,
                check=False
            )

            if restore_result.returncode == 0:
                log.info(f"CLAUDE: Successfully restored external snapshot for VM '{self.vm_name}'")

                # Invalidate PATH cache after snapshot restore
                self._path_discovery_attempted = False
                self._cached_guest_path = None
                log.debug("CLAUDE: PATH cache invalidated after snapshot restore")

                return True
            else:
                log.error(f"CLAUDE: Failed to restore memory state: {restore_result.stderr}")
                return False

        except FileNotFoundError as e:
            log.error(f"CLAUDE: Required command not found (virsh or virt-xml): {e}")
            return False
        except Exception as e:
            log.error(f"CLAUDE: Error restoring external snapshot: {e}")
            return False

    def delete_external_snapshot(
        self,
        snapshot_name: str,
        memory_path: str,
        disk_path: str
    ) -> bool:
        """
        Delete an external snapshot by removing libvirt metadata and files.

        Args:
            snapshot_name: Libvirt snapshot name
            memory_path: Path to external memory save file
            disk_path: Path to external disk overlay file

        Returns:
            True if deletion successful, False otherwise
        """
        log.info(f"CLAUDE: Deleting external snapshot '{snapshot_name}' for VM '{self.vm_name}'")

        success = True

        # Delete libvirt snapshot metadata
        try:
            result = subprocess.run(
                ['virsh', 'snapshot-delete', self.vm_name, snapshot_name],
                capture_output=True,
                text=True,
                check=False
            )

            if result.returncode != 0:
                log.warning(f"CLAUDE: Failed to delete libvirt snapshot metadata: {result.stderr}")
                # Continue with file deletion anyway
        except Exception as e:
            log.warning(f"CLAUDE: Error deleting libvirt snapshot metadata: {e}")
            # Continue with file deletion anyway

        # Delete memory file
        try:
            if os.path.exists(memory_path):
                os.remove(memory_path)
                log.debug(f"CLAUDE: Deleted memory file: {memory_path}")
            else:
                log.debug(f"CLAUDE: Memory file not found (may already be deleted): {memory_path}")
        except OSError as e:
            log.error(f"CLAUDE: Failed to delete memory file {memory_path}: {e}")
            success = False

        # Delete disk file
        try:
            if os.path.exists(disk_path):
                os.remove(disk_path)
                log.debug(f"CLAUDE: Deleted disk file: {disk_path}")
            else:
                log.debug(f"CLAUDE: Disk file not found (may already be deleted): {disk_path}")
        except OSError as e:
            log.error(f"CLAUDE: Failed to delete disk file {disk_path}: {e}")
            success = False

        if success:
            log.info(f"CLAUDE: Successfully deleted external snapshot '{snapshot_name}'")

        return success

    def list_external_snapshots(self) -> list:
        """
        List all libvirt snapshots for the VM.

        Returns:
            List of snapshot names
        """
        try:
            result = subprocess.run(
                ['virsh', 'snapshot-list', self.vm_name, '--name'],
                capture_output=True,
                text=True,
                check=False
            )

            if result.returncode == 0:
                # Parse snapshot names from output (one per line)
                snapshots = [line.strip() for line in result.stdout.splitlines() if line.strip()]
                return snapshots
            else:
                log.warning(f"CLAUDE: Failed to list snapshots: {result.stderr}")
                return []

        except Exception as e:
            log.error(f"CLAUDE: Error listing snapshots: {e}")
            return []

    # Legacy methods kept for backward compatibility but deprecated
    def create_snapshot(self, *args, **kwargs):
        """Deprecated: Use create_external_snapshot instead."""
        raise NotImplementedError(
            "Internal snapshots are deprecated. Use create_external_snapshot instead."
        )

    def snapshot_exists(self, *args, **kwargs):
        """Deprecated: Use database queries instead."""
        raise NotImplementedError(
            "Internal snapshot checking is deprecated. Query the database instead."
        )

    def restore_snapshot(self, *args, **kwargs):
        """Deprecated: Use restore_external_snapshot instead."""
        raise NotImplementedError(
            "Internal snapshots are deprecated. Use restore_external_snapshot instead."
        )

    def delete_snapshot(self, *args, **kwargs):
        """Deprecated: Use delete_external_snapshot instead."""
        raise NotImplementedError(
            "Internal snapshots are deprecated. Use delete_external_snapshot instead."
        )

    async def ensure_initial_snapshot(self, *args, **kwargs):
        """Deprecated: Not applicable for external snapshots."""
        raise NotImplementedError(
            "ensure_initial_snapshot is deprecated for external snapshot workflow."
        )
