"""
VirtualBox VM snapshot operations mixin.

Implements AbstractSnapshotMixin for VirtualBox-specific snapshot operations.
"""
import contextlib
import logging
from pathlib import Path
from typing import Optional, List, Dict
import threading

from adare.hypervisor.base.mixins.snapshots import AbstractSnapshotMixin
from adare.hypervisor.virtualbox.utils import run_subprocess

log = logging.getLogger(__name__)


def list_snapshots(vm_name: str, vboxmanage_exe: str = 'VBoxManage') -> List[Dict[str, str]]:
    """
    List all snapshots for a given VM.

    Args:
        vm_name: Name of the VM
        vboxmanage_exe: Path to VBoxManage executable (defaults to 'VBoxManage')

    Returns:
        List of dictionaries with snapshot information (name, uuid, description)
    """
    try:
        result = run_subprocess(
            [vboxmanage_exe, "snapshot", vm_name, "list", "--machinereadable"],
            log_prefix=f"list_snapshots({vm_name}): ",
            check=False
        )

        if result.returncode != 0:
            log.debug(f"No snapshots found for VM '{vm_name}' or command failed")
            return []

        # Parse the output
        snapshots = []
        current_snapshot = {}

        for line in result.stdout.split('\n'):
            line = line.strip()
            if not line:
                continue

            # Format: SnapshotName-<uuid>="<snapshot_name>"
            if line.startswith('SnapshotName'):
                if current_snapshot and 'name' in current_snapshot:
                    snapshots.append(current_snapshot)
                    current_snapshot = {}

                # Extract UUID and name
                parts = line.split('=', 1)
                if len(parts) == 2:
                    uuid = parts[0].replace('SnapshotName-', '').strip()
                    name = parts[1].strip('"')
                    current_snapshot = {'uuid': uuid, 'name': name, 'description': ''}

            # Format: SnapshotDescription-<uuid>="<description>"
            elif line.startswith('SnapshotDescription') and current_snapshot:
                parts = line.split('=', 1)
                if len(parts) == 2:
                    description = parts[1].strip('"')
                    current_snapshot['description'] = description

        # Add the last snapshot if it exists
        if current_snapshot and 'name' in current_snapshot:
            snapshots.append(current_snapshot)

        return snapshots

    except Exception as e:
        log.error(f"Error listing snapshots for VM '{vm_name}': {e}")
        return []


class SnapshotMixin(AbstractSnapshotMixin):
    """Mixin class providing snapshot operations for VirtualBox VMs."""
    
    def create_snapshot(self, snapshot_name: str, description: str = "", ctx_manager=None, stop_event=None, log_file: Optional[Path] = None, silent: bool = False):
        """Create a snapshot of the VM."""
        def _create_snapshot():
            args = [
                "snapshot", self.vm_name, "take", snapshot_name
            ]
            if description:
                args.extend(["--description", description])
            
            return_value = self._execute_streaming_command(
                args,
                log_file=log_file,
                stop_event=stop_event,
                silent=silent,
                ctx_manager=ctx_manager,
                operation_name="snapshot creation",
                timeout=240  # 4 minute timeout for snapshot creation
            )
            
            if return_value == 0:
                log.info(f"Snapshot '{snapshot_name}' created successfully for VM '{self.vm_name}'")
            else:
                log.error(f"Failed to create snapshot '{snapshot_name}' for VM '{self.vm_name}': return code {return_value}")
            
            return return_value
        
        return self.manager.run(_create_snapshot)

    def snapshot_exists(self, snapshot_name: str) -> bool:
        """Check if a snapshot exists for the VM."""
        def _snapshot_exists():
            try:
                log.debug(f"Checking if snapshot '{snapshot_name}' exists for VM '{self.vm_name}'.")
                result = run_subprocess(
                    [self.vboxmanage_exe, "snapshot", self.vm_name, "list", "--machinereadable"],
                    log_prefix=f"snapshot_exists({snapshot_name}): ",
                    check=False
                )
                
                if result.returncode != 0:
                    log.debug(f"Command failed with return code {result.returncode}. Assuming no snapshots exist.")
                    return False
                
                # Parse the output for snapshot names
                for line in result.stdout.split('\n'):
                    if line.startswith('SnapshotName'):
                        # Format: SnapshotName-<uuid>="<snapshot_name>"
                        if f'="{snapshot_name}"' in line:
                            log.debug(f"Found snapshot '{snapshot_name}' for VM '{self.vm_name}'.")
                            return True
                
                log.debug(f"Snapshot '{snapshot_name}' not found for VM '{self.vm_name}'.")
                return False
            except Exception as e:
                log.error(f"Error checking if snapshot '{snapshot_name}' exists for VM '{self.vm_name}': {e}")
                return False
        
        return self.manager.run(_snapshot_exists)

    def restore_snapshot(self, snapshot_name: str, ctx_manager=None, stop_event=None, log_file: Optional[Path] = None, silent: bool = False) -> bool:
        """Restore a snapshot for the VM."""
        def _restore_snapshot():
            try:
                log.info(f"Restoring VM '{self.vm_name}' to snapshot '{snapshot_name}'.")
                args = ["snapshot", self.vm_name, "restore", snapshot_name]
                return_value = self._execute_streaming_command(
                    args,
                    log_file=log_file,
                    stop_event=stop_event,
                    silent=silent,
                    ctx_manager=ctx_manager,
                    operation_name="snapshot restoration",
                    timeout=180  # 3 minute timeout for snapshot operations
                )
                
                if return_value == 0:
                    log.info(f"VM '{self.vm_name}' successfully restored to snapshot '{snapshot_name}'.")
                    return True
                else:
                    log.error(f"Failed to restore VM '{self.vm_name}' to snapshot '{snapshot_name}': return code {return_value}")
                    return False
            except Exception as e:
                log.error(f"Error restoring VM '{self.vm_name}' to snapshot '{snapshot_name}': {e}")
                return False
        
        return self.manager.run(_restore_snapshot)

    def delete_snapshot(self, snapshot_name: str, ctx_manager=None, stop_event=None, log_file: Optional[Path] = None, silent: bool = False) -> bool:
        """Delete a snapshot from the VM."""
        def _delete_snapshot():
            try:
                log.info(f"Deleting snapshot '{snapshot_name}' from VM '{self.vm_name}'.")
                args = ["snapshot", self.vm_name, "delete", snapshot_name]
                return_value = self._execute_streaming_command(
                    args,
                    log_file=log_file,
                    stop_event=stop_event,
                    silent=silent,
                    ctx_manager=ctx_manager,
                    operation_name="snapshot deletion"
                )
                
                if return_value == 0:
                    log.info(f"Snapshot '{snapshot_name}' deleted successfully from VM '{self.vm_name}'.")
                    return True
                else:
                    log.error(f"Failed to delete snapshot '{snapshot_name}' from VM '{self.vm_name}': return code {return_value}")
                    return False
            except Exception as e:
                log.error(f"Error deleting snapshot '{snapshot_name}' from VM '{self.vm_name}': {e}")
                return False
        
        return self.manager.run(_delete_snapshot)

    async def ensure_initial_snapshot(
        self,
        ovf_path: str,
        snapshot_name: str,
        snapshot_description: str = ""
    ):
        """Ensure the VM exists and has an initial snapshot."""
        if not self.vm_exists():
            log.info(f"VM '{self.vm_name}' does not exist. Importing from OVF and creating initial snapshot.")
            await self.create_from_ovf_or_ova(file_path=Path(ovf_path))
            self.create_snapshot(snapshot_name=snapshot_name, description=snapshot_description)
            log.info(f"VM '{self.vm_name}' created and initial snapshot '{snapshot_name}' taken.")
        else:
            if self.snapshot_exists(snapshot_name):
                log.info(f"Restoring VM '{self.vm_name}' to initial snapshot '{snapshot_name}'.")
                self.restore_snapshot(snapshot_name)
                log.info(f"Restored VM '{self.vm_name}' to snapshot '{snapshot_name}'.")
            else:
                log.warning(f"Initial snapshot '{snapshot_name}' not found for VM '{self.vm_name}'. Starting VM as is.")