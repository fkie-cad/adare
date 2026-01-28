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

        return snapshot_success

    def _get_attached_virtiofs_payloads(self) -> list:
        """
        Get XML payloads for all currently attached virtiofs devices.
        
        Returns:
            List of XML strings for attached filesystems
        """
        import libvirt
        import xml.etree.ElementTree as ET
        
        payloads = []
        try:
            # Get current domain XML
            xml_desc = self._libvirt_domain.XMLDesc(0)
            root = ET.fromstring(xml_desc)
            
            # Find all filesystem devices with type='virtiofs' (driver type)
            # XPath: ./devices/filesystem/driver[@type='virtiofs']/..
            devices = root.find('devices')
            if devices is not None:
                for fs in devices.findall('filesystem'):
                    driver = fs.find('driver')
                    if driver is not None and driver.get('type') == 'virtiofs':
                        # Convert element back to string
                        payload = ET.tostring(fs, encoding='unicode')
                        payloads.append(payload)
                        
            log.debug(f"CLAUDE: Found {len(payloads)} attached virtiofs devices")
            return payloads
            
        except Exception as e:
            log.error(f"CLAUDE: Failed to get attached virtiofs devices: {e}")
            return []

    def _detach_virtiofs_shares(self, payloads: list) -> bool:
        """
        Hot-unplug virtiofs devices with verification.
        
        Args:
            payloads: List of XML strings for devices to detach
            
        Returns:
            True if all detached successfully
        """
        if not payloads:
            return True
            
        import libvirt
        import time
        
        count = len(payloads)
        log.info(f"CLAUDE: Detaching {count} virtiofs devices for snapshotting...")
        
        # 1. Request detachment for all devices
        for i, xml in enumerate(payloads):
            try:
                # Detach device (live config)
                self._libvirt_domain.detachDevice(xml)
                log.debug(f"CLAUDE: Requested detach for virtiofs device {i+1}/{count}")
            except libvirt.libvirtError as e:
                log.error(f"CLAUDE: Failed to detach virtiofs device {i+1}: {e}")
                return False

        # 2. Poll until all virtiofs devices are gone
        # Max wait 10 seconds (usually takes < 1s)
        timeout = 10
        start_time = time.time()
        
        while time.time() - start_time < timeout:
            remaining = self._get_attached_virtiofs_payloads()
            if not remaining:
                log.info("CLAUDE: All virtiofs devices successfully detached")
                return True
            
            # Log progress if waiting
            elapsed = time.time() - start_time
            if elapsed > 1.0:
                 log.debug(f"CLAUDE: Waiting for detachment... ({len(remaining)} remaining)")
            
            time.sleep(0.5)
            
        log.error(f"CLAUDE: Timeout waiting for virtiofs detachment. {len(remaining)} devices remaining.")
        return False

    def _attach_virtiofs_shares(self, payloads: list) -> bool:
        """
        Hot-plug virtiofs devices.
        
        Args:
            payloads: List of XML strings for devices to attach
            
        Returns:
            True if all attached successfully
        """
        if not payloads:
            return True
            
        import libvirt
        
        count = len(payloads)
        log.info(f"CLAUDE: Re-attaching {count} virtiofs devices after snapshot...")
        
        success = True
        for i, xml in enumerate(payloads):
            try:
                # Attach device (live config)
                self._libvirt_domain.attachDevice(xml)
                log.debug(f"CLAUDE: Attached virtiofs device {i+1}/{count}")
            except libvirt.libvirtError as e:
                log.error(f"CLAUDE: Failed to attach virtiofs device {i+1}: {e}")
                success = False
                
        return success

    def _prepare_guest_for_snapshot(self) -> None:
        """
        Prepare guest OS for snapshot by releasing shared folder handles.
        
        This prevents "Invalid Handle" errors and ensures a clean state for restoration.
        """
        if not self.config.virtiofs_enabled or not self.config.virtiofs_shares:
            return

        try:
            # Only attempt if guest agent is responsive
            if not self._check_guest_agent():
                log.warning("CLAUDE: Guest agent not responsive, skipping pre-snapshot unmount")
                return

            log.info("CLAUDE: Preparing guest for snapshot (releasing shared folders)...")
            
            # Detect OS
            is_windows = 'windows' in self.guest_os.lower()
            
            if is_windows:
                # Kill virtiofs.exe processes to release handles
                # /F = force, /IM = image name
                cmd = 'taskkill /F /IM virtiofs.exe'
                try:
                    self._run_guest_agent_command_sync(cmd)
                    log.debug("CLAUDE: Killed virtiofs.exe processes in guest")
                except Exception as e:
                    log.warning(f"CLAUDE: Failed to kill virtiofs.exe (might not be running): {e}")
            else:
                # Linux: Lazy unmount all shares
                for share in self.config.virtiofs_shares:
                    mount_point = share['guest_mount']
                    cmd = f'umount -l {mount_point}'
                    try:
                        self._run_guest_agent_command_sync(cmd)
                    except Exception as e:
                        log.warning(f"CLAUDE: Failed to unmount {mount_point}: {e}")
                        
        except Exception as e:
            log.warning(f"CLAUDE: Error during guest migration preparation: {e}")

    def _refresh_guest_mounts(self) -> None:
        """
        Refresh/Remount shared folders in the guest after restoration.
        """
        if not self.config.virtiofs_enabled or not self.config.virtiofs_shares:
            return

        try:
            # Wait for agent to come back (it should be running as we restored state)
            import time
            time.sleep(2)
            if not self._check_guest_agent():
                log.warning("CLAUDE: Guest agent not responsive after restore, cannot refresh mounts")
                return

            log.info("CLAUDE: Refreshing guest mounts...")
            
            is_windows = 'windows' in self.guest_os.lower()
            
            if is_windows:
                # Re-run virtiofs.exe for each share using Scheduled Task for Session 0 isolation escape
                # This ensures the mount is visible to the user session
                virtiofs_exe = r"C:\Program Files\VirtIO-Win\VioFS\virtiofs.exe"
                
                for share in self.config.virtiofs_shares:
                    tag = share['tag']
                    mount_point = str(share['guest_mount']).replace('/', '\\')
                    
                    # Force remove the directory first (virtiofs fails if it exists)
                    # Then run the mount command
                    # Note: We must escape the double quotes for the PS string
                    mount_cmd = (
                        f'if (Test-Path "{mount_point}") {{ Remove-Item "{mount_point}" -Force -Recurse -ErrorAction SilentlyContinue }}; '
                        f'& "{virtiofs_exe}" -t {tag} -m "{mount_point}"'
                    )
                    
                    try:
                        self._run_as_user_windows_sync(mount_cmd)
                        log.debug(f"CLAUDE: Restarted virtiofs for {tag} (user session)")
                    except Exception as e:
                        log.error(f"CLAUDE: Failed to remount {tag}: {e}")
            else:
                # Linux: Remount
                for share in self.config.virtiofs_shares:
                    tag = share['tag']
                    mount_point = share['guest_mount']
                    cmd = f'mount -t virtiofs {tag} {mount_point}'
                    try:
                        self._run_guest_agent_command_sync(cmd)
                        log.debug(f"CLAUDE: Remounted {mount_point}")
                    except Exception as e:
                        log.error(f"CLAUDE: Failed to remount {mount_point}: {e}")
                        
        except Exception as e:
            log.error(f"CLAUDE: Error refreshing guest mounts: {e}")

    def _run_as_user_windows_sync(self, command: str) -> None:
        """
        Run a command in Windows guest as the logged-in user using Scheduled Tasks.
        Replicates logic from mixins/commands.py _build_guest_command_args.
        Synchronous version for snapshot operations.
        """
        import time
        import base64
        import uuid
        
        # Parameters
        user = self.username
        pw = self.password
        
        # Use UUID to ensure uniqueness for rapid consecutive calls (looping through shares)
        unique_id = str(uuid.uuid4())[:8]
        task_name = f"adare_snap_{unique_id}"
        script_path = f"C:\\Windows\\Temp\\adare_{unique_id}.ps1"
        rl = "LIMITED" # or HIGHEST if admin needed, default to LIMITED for regular user
        
        # Construct the complex PowerShell script
        # Note: We need to escape internal quotes carefully
        ps_command = (                                                                                                                                 
            f"& {{ "                                                                                                                                       
            f"$u = '{user}'; $p = '{pw}'; $t = '{task_name}'; "                                                                                 
            f"$script = '{script_path}'; "                                                                                                                 
            f"$st = (Get-Date).AddMinutes(2).ToString('HH:mm'); "                                                                                                                                                                                                 
            f"'{command}' | Out-File -FilePath $script -Encoding ascii; "                                                                                  
            f"$c = \"powershell.exe -NoProfile -ExecutionPolicy Bypass -File $script\"; "                                                                  
            f"schtasks /Create /TN $t /TR \"$c\" /SC ONCE /ST $st /RU $u /RP $p /RL {rl} /F; "                                                          
            f"schtasks /Run /TN $t; "                                                                                                                      
            f"Start-Sleep -Seconds 15; "                                                                                                                    
            f"if (Test-Path $script) {{ Remove-Item $script -Force }}; "
            # Try to delete task as well (might fail if running, but good hygiene)
            f"schtasks /Delete /TN $t /F | Out-Null; "                                                                                   
            f"}} "                                                                                                                                         
        )
        
        # Base64 encode for -EncodedCommand
        command_base64 = base64.b64encode(ps_command.encode('utf-16le')).decode('utf-8')
        
        # Call via QGA using powershell.exe
        # qemu-agent-command takes arguments, but here we just pass the full string to our helper
        # which wraps it in cmd.exe /c
        
        # Helper expects the raw command string, it wraps it in 'cmd /c'
        # But we need to run 'powershell -EncodedCommand ...'
        full_cmd = f"powershell.exe -EncodedCommand {command_base64}"
        
        self._run_guest_agent_command_sync(full_cmd)

    def _run_guest_agent_command_sync(self, cmd_str: str) -> None:
        """Helper to run QGA commands synchronously via libvirt qemu-agent-command."""
        import json
        try:
            # Construct QMP command for guest-exec
            # We use capture-output to avoid hanging if the command produces output
            if 'windows' in self.guest_os.lower():
                qmp_cmd = {
                    "execute": "guest-exec",
                    "arguments": {
                        "path": "cmd.exe",
                        "arg": ["/c", cmd_str],
                        "capture-output": True
                    }
                }
            else:
                qmp_cmd = {
                    "execute": "guest-exec",
                    "arguments": {
                        "path": "/bin/sh",
                        "arg": ["-c", cmd_str],
                        "capture-output": True
                    }
                }
            
            cmd_json = json.dumps(qmp_cmd)
            subprocess.run(
                ['virsh', 'qemu-agent-command', self.vm_name, cmd_json],
                check=False, capture_output=True
            )
            
        except Exception as e:
            log.warning(f"CLAUDE: Failed to run sync guest command: {e}")

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
        2. Detach VirtioFS devices (hot-unplug) - REQUIRED for migration/save
        3. Save the VM State: `virsh save` (Stops VM)
        4. Create the Disk Snapshot: `virsh snapshot-create-as --disk-only`
        5. Resume the VM: `virsh restore --xml <updated_xml>`
           We dump the XML (which now points to new disk) and restore using it.
        6. Re-attach VirtioFS devices (hot-plug)
        7. (Finally) Thaw if needed: `virsh domfsthaw`

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
        virtiofs_payloads = []
        import tempfile

        try:
            # 1.5. Detach VirtioFS devices (they block migration/save)
            virtiofs_payloads = []
            if self.config.virtiofs_enabled and self.config.virtiofs_shares:
                # NEW: Release handles in guest BEFORE detach
                self._prepare_guest_for_snapshot()
                virtiofs_payloads = self._get_attached_virtiofs_payloads()
            
            if virtiofs_payloads:
                if not self._detach_virtiofs_shares(virtiofs_payloads):
                    # If detach fails, likely devices are still busy, but we killed procs?
                    # Try to maintain state by re-attaching
                    log.warning("CLAUDE: Failed to detach some virtiofs devices, snapshot might fail")
                    # Should we abort? If we proceed, save will fail.
                    # Let's try to abort gracefully
                    log.error("CLAUDE: Aborting snapshot due to detach failure")
                    self._attach_virtiofs_shares(virtiofs_payloads)
                    self._refresh_guest_mounts()
                    return False

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
            
            # 4b. Strip virtiofs devices from XML to match saved state
            # The saved state has 0 filesystems (because we detached them).
            # The dumped XML might still have them if they are in the persistent config.
            # We must remove them to avoid "Target domain filesystem count mismatch".
            try:
                import xml.etree.ElementTree as ET
                root = ET.fromstring(updated_xml)
                devices = root.find('devices')
                if devices is not None:
                    # Find and remove all virtiofs filesystems
                    for fs in devices.findall('filesystem'):
                        driver = fs.find('driver')
                        if driver is not None and driver.get('type') == 'virtiofs':
                            devices.remove(fs)
                            log.debug("CLAUDE: Stripped virtiofs device from restore XML")
                    
                    updated_xml = ET.tostring(root, encoding='unicode')
            except Exception as e:
                log.error(f"CLAUDE: Failed to strip filesystems from XML: {e}")
            
            # 4c. Restore using the updated (and stripped) XML
            with tempfile.NamedTemporaryFile(mode='w', suffix='.xml', delete=True) as tmp_xml:
                tmp_xml.write(updated_xml)
                tmp_xml.flush()
                
                restore_args = [
                    'virsh', 'restore', memory_path,
                    '--xml', tmp_xml.name,
                    '--running'
                ]
                
                subprocess.run(restore_args, check=True, capture_output=True)
                
            # 6. Re-attach VirtioFS devices
            if virtiofs_payloads:
                self._attach_virtiofs_shares(virtiofs_payloads)
                # NEW: Refresh guest mounts
                self._refresh_guest_mounts()
                
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
            
            # Attempt to re-attach devices if we failed after detach but before/during save
            if virtiofs_payloads and self.get_state() == "running":
                try:
                    self._attach_virtiofs_shares(virtiofs_payloads)
                    self._refresh_guest_mounts()
                except Exception:
                    pass
        except Exception as e:
            log.error(f"CLAUDE: Error creating external snapshot: {e}")
            snapshot_success = False
            
            # Attempt recovery
            if virtiofs_payloads and self.get_state() == "running":
                try:
                    self._attach_virtiofs_shares(virtiofs_payloads)
                    self._refresh_guest_mounts()
                except Exception:
                    pass

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

                # RE-INITIALIZE DOMAIN OBJECT
                # The domain ID changes after restore, and sometimes the existing object becomes invalid/stale.
                # We must refresh it to ensure subsequent operations (like attachDevice) work correctly.
                try:
                    conn = self._get_libvirt_connection()
                    self._libvirt_domain = conn.lookupByName(self.vm_name)
                    log.debug("CLAUDE: Refreshed libvirt domain object after restore")
                except Exception as e:
                    log.error(f"CLAUDE: Failed to refresh libvirt domain object: {e}")
                    # Continue anyway, we might still have a working object or fail later

                # Invalidate PATH cache after snapshot restore
                self._path_discovery_attempted = False
                self._cached_guest_path = None
                log.debug("CLAUDE: PATH cache invalidated after snapshot restore")

                # Re-attach configured virtiofs shares
                # When we snapshot, we hot-unplug these devices.
                # When we restore, they are still missing (because we restored to the unplugged state).
                # We need to re-attach them now.
                if self.config.virtiofs_enabled and self.config.virtiofs_shares:
                    log.info("CLAUDE: Re-attaching virtiofs shares after restore...")
                    try:
                        from adare.hypervisor.qemu.libvirt_xml import generate_virtiofs_xml_element
                        import xml.etree.ElementTree as ET
                        
                        is_q35 = 'q35' in self.machine or (self.config.boot_mode == 'uefi')
                        base_bus = 6
                        base_slot = 7
                        
                        payloads = []
                        for idx, share in enumerate(self.config.virtiofs_shares):
                            elem = generate_virtiofs_xml_element(share, is_q35, idx, base_bus, base_slot)
                            payloads.append(ET.tostring(elem, encoding='unicode'))
                            
                        self._attach_virtiofs_shares(payloads)
                        
                        # NEW: Refresh guest mounts
                        self._refresh_guest_mounts()
                            
                    except Exception as e:
                        log.error(f"CLAUDE: Failed to re-attach virtiofs shares after restore: {e}")

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
        Delete an external snapshot by removing snapshot files.

        External snapshots created with --no-metadata have no libvirt metadata
        to delete, only the external files need to be removed.

        Args:
            snapshot_name: Snapshot name (for logging only)
            memory_path: Path to external memory save file
            disk_path: Path to external disk overlay file

        Returns:
            True if deletion successful, False otherwise
        """
        log.info(f"CLAUDE: Deleting external snapshot '{snapshot_name}' for VM '{self.vm_name}'")

        success = True

        # External snapshots created with --no-metadata have no libvirt metadata
        # Only the external files need to be removed

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
            log.info(f"CLAUDE: Successfully deleted external snapshot files for '{snapshot_name}'")

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
