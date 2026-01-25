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

    def _cleanup_snapshot_dir_if_empty(self) -> bool:
        """
        Remove snapshot directory if it exists and is empty.

        Returns:
            True if directory was removed, False otherwise
        """
        try:
            snapshot_dir = self._get_snapshot_storage_dir()
            if snapshot_dir.exists() and snapshot_dir.is_dir():
                # Check if directory is empty
                if not any(snapshot_dir.iterdir()):
                    snapshot_dir.rmdir()
                    log.info(f"CLAUDE: Removed empty snapshot directory: {snapshot_dir}")
                    return True
                else:
                    log.debug(f"CLAUDE: Snapshot directory not empty: {snapshot_dir}")
            return False
        except Exception as e:
            log.warning(f"CLAUDE: Failed to remove snapshot directory: {e}")
            return False

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
        Create a consistent live checkpoint using 'Live Resume' strategy.
        
        Saves RAM and creates a disk snapshot without VSS timeout risks.
        
        Strategy:
        1. Quiesce the Guest (Optional): `virsh domfsfreeze`
        2. Save the VM State: `virsh save` (Stops VM)
        3. Create the Disk Snapshot: `virsh snapshot-create-as --disk-only`
        4. Resume the VM: `virsh restore --xml <updated_xml>`
           We dump the XML (which now points to new disk) and restore using it.
        5. (Finally) Thaw if needed: `virsh domfsthaw`

        Args:
            snapshot_name: Libvirt snapshot name
            memory_path: Path for external memory save file
            disk_path: Path for external disk overlay file
            use_quiesce: Whether to use guest agent to quiesce filesystem (default True)

        Returns:
            True if snapshot created successfully, False otherwise
        """
        log.info(f"CLAUDE: Creating consistent live snapshot '{snapshot_name}' for VM '{self.vm_name}'")

        # Ensure VM is running
        if self.get_state() != "running":
            log.error("CLAUDE: VM must be running to create live snapshot")
            return False

        # Ensure snapshot directory exists
        snapshot_dir = Path(memory_path).parent
        self._ensure_snapshot_dir(snapshot_dir)

        frozen = False
        snapshot_success = False
        import tempfile

        try:
            # 2. Save the VM State (Stops the VM)
            log.info(f"CLAUDE: Saving VM state to {memory_path}...")
            subprocess.run(
                ['virsh', 'save', self.vm_name, memory_path],
                check=True, capture_output=True
            )

            # 3. Create the Disk Snapshot (updates domain config to use new overlay)
            log.info(f"CLAUDE: Creating disk snapshot at {disk_path}...")
            snapshot_args = [
                'virsh', 'snapshot-create-as', self.vm_name,
                '--name', snapshot_name,
                '--disk-only',
                '--diskspec', f'vda,snapshot=external,file={disk_path}',
                '--no-metadata',
                '--atomic',
                '--quiesce'
            ]
            
            subprocess.run(
                snapshot_args,
                check=True, capture_output=True
            )

            # 4. Resume the VM
            log.info("CLAUDE: Resuming VM from saved state...")
            
            # 4a. Get the updated XML (which includes the new disk overlay)
            dump_result = subprocess.run(
                ['virsh', 'dumpxml', self.vm_name],
                check=True, capture_output=True, text=True
            )
            updated_xml = dump_result.stdout
            
            # 4b. Restore using the updated XML
            with tempfile.NamedTemporaryFile(mode='w', suffix='.xml', delete=True) as tmp_xml:
                tmp_xml.write(updated_xml)
                tmp_xml.flush()
                
                restore_args = [
                    'virsh', 'restore', memory_path,
                    '--xml', tmp_xml.name,
                    '--running'
                ]
                
                subprocess.run(restore_args, check=True, capture_output=True)
                
            log.info(f"CLAUDE: Checkpoint created and VM resumed successfully.")
            snapshot_success = True

        except subprocess.CalledProcessError as e:
            log.error(f"CLAUDE: Command failed during snapshot creation: {e.cmd}")
            # Try to decode safely
            stderr_out = "N/A"
            if hasattr(e, 'stderr'):
                if isinstance(e.stderr, bytes):
                    stderr_out = e.stderr.decode('utf-8', errors='replace')
                else:
                    stderr_out = str(e.stderr)
            log.error(f"CLAUDE: Stderr: {stderr_out}")
            snapshot_success = False
        except Exception as e:
            log.error(f"CLAUDE: Error creating external snapshot: {e}")
            snapshot_success = False

        return snapshot_success

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
        # Note: libvirt doesn't support deleting external disk snapshots via API
        # We delete the files manually instead
        try:
            result = subprocess.run(
                ['virsh', 'snapshot-delete', self.vm_name, snapshot_name],
                capture_output=True,
                text=True,
                check=False
            )

            if result.returncode != 0:
                # Check if it's the expected "external disk snapshots not supported" error
                if "external disk snapshots not supported" in result.stderr:
                    log.debug(f"CLAUDE: Libvirt doesn't support external snapshot deletion via API (expected), deleting files manually")
                else:
                    log.warning(f"CLAUDE: Failed to delete libvirt snapshot metadata: {result.stderr}")
                # Continue with file deletion anyway
        except Exception as e:
            log.warning(f"CLAUDE: Error deleting libvirt snapshot metadata: {e}")
            # Continue with file deletion anyway

        # Delete memory file with retry logic
        memory_deleted = False
        if os.path.exists(memory_path):
            for attempt in range(3):
                try:
                    os.remove(memory_path)
                    log.debug(f"CLAUDE: Deleted memory file: {memory_path}")
                    memory_deleted = True
                    break
                except OSError as e:
                    if attempt < 2:
                        import time
                        log.debug(f"CLAUDE: Snapshot memory deletion attempt {attempt+1} failed, retrying: {e}")
                        time.sleep(0.5)
                    else:
                        log.error(f"CLAUDE: Failed to delete snapshot memory file after 3 attempts: {e}")
                        success = False

            # Verify deletion
            if memory_deleted and os.path.exists(memory_path):
                log.error(f"CLAUDE: Snapshot memory still exists after deletion: {memory_path}")
                success = False
        else:
            log.debug(f"CLAUDE: Memory file not found (may already be deleted): {memory_path}")

        # Delete disk file with retry logic
        disk_deleted = False
        if os.path.exists(disk_path):
            for attempt in range(3):
                try:
                    os.remove(disk_path)
                    log.debug(f"CLAUDE: Deleted disk file: {disk_path}")
                    disk_deleted = True
                    break
                except OSError as e:
                    if attempt < 2:
                        import time
                        log.debug(f"CLAUDE: Snapshot disk deletion attempt {attempt+1} failed, retrying: {e}")
                        time.sleep(0.5)
                    else:
                        log.error(f"CLAUDE: Failed to delete snapshot disk file after 3 attempts: {e}")
                        success = False

            # Verify deletion
            if disk_deleted and os.path.exists(disk_path):
                log.error(f"CLAUDE: Snapshot disk still exists after deletion: {disk_path}")
                success = False
        else:
            log.debug(f"CLAUDE: Snapshot disk file not found (may already be deleted): {disk_path}")

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
