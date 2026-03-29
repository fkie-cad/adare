"""
VirtualBox VM networking operations mixin.

Implements AbstractNetworkingMixin for VirtualBox-specific networking operations.
"""
import asyncio
import logging
from pathlib import Path
from typing import Dict, Optional
import threading

from adare.hypervisor.base.mixins.networking import AbstractNetworkingMixin
from adare.hypervisor.virtualbox.models import PortForwardingRule, SharedFolderConfig
from adare.hypervisor.virtualbox.utils import run_subprocess

log = logging.getLogger(__name__)


class NetworkingMixin(AbstractNetworkingMixin):
    """Mixin class providing networking operations for VirtualBox VMs."""
    
    async def list_port_forwarding_rules(self, ctx_manager=None, stop_event=None, log_file: Optional[Path] = None, silent: bool = False) -> Dict[str, PortForwardingRule]:
        """List all port forwarding rules for the VM."""
        async def _list_port_forwards_async():
            try:
                result = run_subprocess(
                    [self.vboxmanage_exe, "showvminfo", self.vm_name, "--machinereadable"],
                    log_prefix="list_port_forwarding_rules: ",
                    check=False
                )
                
                if result.returncode != 0:
                    log.warning(f"Failed to get VM info for '{self.vm_name}': return code {result.returncode}")
                    return {}
                
                rules = {}
                for line in result.stdout.split('\n'):
                    # Look for lines like: Forwarding(0)="name,protocol,host_ip,host_port,guest_ip,guest_port"
                    if line.startswith('Forwarding(') and ')=' in line:
                        try:
                            # Extract the rule string
                            rule_str = line.split('=', 1)[1].strip('"')
                            rule = PortForwardingRule.from_vbox_format(rule_str)
                            rules[rule.name] = rule
                        except Exception as e:
                            log.warning(f"Failed to parse port forwarding rule: {line} - {e}")
                
                if not silent:
                    log.debug(f"Found {len(rules)} port forwarding rules for VM '{self.vm_name}'")
                return rules
            except Exception as e:
                log.error(f"Error listing port forwarding rules for VM '{self.vm_name}': {e}")
                return {}
        
        return await self.manager.run_async(_list_port_forwards_async)

    async def add_port_forwarding(
        self,
        name: str,
        protocol: str,
        host_port: int,
        guest_port: int,
        host_ip: str = "",
        guest_ip: str = "",
        ctx_manager=None,
        stop_event=None,
        log_file: Optional[Path] = None,
        silent: bool = False
    ) -> int:
        """Add a port forwarding rule to the VM."""
        async def _add_port_forward_async():
            # Create rule object for comparison
            new_rule = PortForwardingRule(
                name=name,
                protocol=protocol,
                host_ip=host_ip,
                host_port=host_port,
                guest_ip=guest_ip,
                guest_port=guest_port
            )
            
            # First check if identical rule already exists
            existing_rules = await self.list_port_forwarding_rules(ctx_manager, stop_event, log_file, silent)
            
            if name in existing_rules:
                existing_rule = existing_rules[name]
                # Check if the existing rule is identical
                if new_rule.matches(existing_rule):
                    if not silent:
                        log.info(f"Port forward '{name}' already exists with identical configuration - skipping")
                    return 0
                else:
                    log.warning(f"Port forward '{name}' exists but with different configuration - will attempt to remove and re-add")
                    log.debug(f"Existing: {existing_rule}, New: {new_rule}")
                    # Remove existing rule first
                    remove_args = ["modifyvm", self.vm_name, "--natpf1", "delete", name]
                    try:
                        await self._execute_streaming_command_async(
                            remove_args,
                            log_file=log_file,
                            stop_event=stop_event,
                            silent=silent,
                            ctx_manager=ctx_manager,
                            operation_name="port forward removal"
                        )
                    except Exception as e:
                        log.warning(f"Failed to remove existing port forward '{name}': {e}")
            
            # Add the port forwarding rule
            args = [
                "modifyvm", self.vm_name,
                "--natpf1", new_rule.to_vbox_format()
            ]
            
            try:
                log.info(f"Adding port forward '{name}' ({protocol}) {host_ip}:{host_port} -> {guest_ip}:{guest_port} for VM '{self.vm_name}'")
                return_value, _, _ = await self._execute_streaming_command_async(
                    args,
                    log_file=log_file,
                    stop_event=stop_event,
                    silent=silent,
                    ctx_manager=ctx_manager,
                    operation_name="port forward addition"
                )
                
                if return_value == 0:
                    log.info(f"Port forward '{name}' added successfully to VM '{self.vm_name}'")
                else:
                    log.error(f"Failed to add port forward '{name}' to VM '{self.vm_name}': return code {return_value}")
                
                return return_value
            except Exception as e:
                log.error(f"Error adding port forward '{name}' to VM '{self.vm_name}': {e}")
                return 1
        
        return await self.manager.run_async(_add_port_forward_async)

    async def remove_port_forwarding(
        self,
        name: str,
        ctx_manager=None,
        stop_event=None,
        log_file: Optional[Path] = None,
        silent: bool = False
    ) -> int:
        """Remove a port forwarding rule from the VM."""
        async def _remove_port_forward_async():
            # First check if the rule exists
            existing_rules = await self.list_port_forwarding_rules(ctx_manager, stop_event, log_file, silent=True)

            if name not in existing_rules:
                if not silent:
                    log.info(f"Port forward '{name}' does not exist - skipping removal")
                return 0

            # Remove the port forwarding rule
            args = ["modifyvm", self.vm_name, "--natpf1", "delete", name]

            try:
                log.info(f"Removing port forward '{name}' from VM '{self.vm_name}'")
                return_value, _, _ = await self._execute_streaming_command_async(
                    args,
                    log_file=log_file,
                    stop_event=stop_event,
                    silent=silent,
                    ctx_manager=ctx_manager,
                    operation_name="port forward removal"
                )

                if return_value == 0:
                    log.info(f"Port forward '{name}' removed successfully from VM '{self.vm_name}'")
                else:
                    log.error(f"Failed to remove port forward '{name}' from VM '{self.vm_name}': return code {return_value}")

                return return_value
            except Exception as e:
                log.error(f"Error removing port forward '{name}' from VM '{self.vm_name}': {e}")
                return 1

        return await self.manager.run_async(_remove_port_forward_async)

    async def add_shared_folder(self, name: str, host_path: Path, readonly: bool = False, ctx_manager=None, stop_event=None, log_file: Optional[Path] = None, silent: bool = False):
        """
        Add a shared folder to the VM (VirtualBox configuration only).
        Checks if an identical shared folder already exists to prevent conflicts.
        For Windows guests with custom mountpoint, this only adds the shared folder - use mount_shared_folder() after VM startup.
        For other cases, uses VirtualBox's built-in shared folder mechanism with automount.
        
        Args:
            name: Name of the shared folder
            host_path: Path on the host machine
            readonly: Whether the share is read-only
            ctx_manager: Context manager for status updates
            stop_event: Event to signal stop
            log_file: Log file for output
            silent: Whether to suppress logging
        """
        async def _add_shared_folder_async():
            # Create config object for comparison
            new_config = SharedFolderConfig(
                name=name,
                host_path=str(host_path),
                readonly=readonly
            )
            
            # First check if identical folder already exists
            existing_folders = await self.list_shared_folders(ctx_manager, stop_event, log_file, silent)
            
            if name in existing_folders:
                existing_config = existing_folders[name]
                # Check if the existing folder is identical
                if new_config.matches(existing_config):
                    if not silent:
                        log.info(f"Shared folder '{name}' already exists with identical configuration - skipping")
                    return 0
                else:
                    log.warning(f"Shared folder '{name}' exists but with different configuration - will attempt to remove and re-add")
                    log.debug(f"Existing: {existing_config}, New: {new_config}")
                    # Remove existing folder first
                    remove_args = ["sharedfolder", "remove", self.vm_name, "--name", name]
                    try:
                        await self._execute_streaming_command_async(
                            remove_args,
                            log_file=log_file,
                            stop_event=stop_event,
                            silent=silent,
                            ctx_manager=ctx_manager,
                            operation_name="shared folder removal"
                        )
                    except Exception as e:
                        log.warning(f"Failed to remove existing shared folder '{name}': {e}")
            
            # Add the shared folder
            args = [
                "sharedfolder", "add", self.vm_name,
                "--name", name,
                "--hostpath", str(host_path)
            ]
            
            if readonly:
                args.append("--readonly")
            
            try:
                log.info(f"Adding shared folder '{name}' (host: {host_path}) to VM '{self.vm_name}'")
                log.debug(f"VBoxManage command: {' '.join(args)}")
                return_value, stdout, stderr = await self._execute_streaming_command_async(
                    args,
                    log_file=log_file,
                    stop_event=stop_event,
                    silent=silent,
                    ctx_manager=ctx_manager,
                    operation_name="shared folder addition"
                )

                if return_value == 0:
                    log.info(f"Shared folder '{name}' added to VM '{self.vm_name}' successfully")
                    # NOTE: Verification removed - VBoxManage return code is authoritative
                else:
                    log.error(f"Failed to add shared folder '{name}' to VM '{self.vm_name}': return code {return_value}")
                    if stdout:
                        log.error(f"stdout: {stdout}")
                    if stderr:
                        log.error(f"stderr: {stderr}")

                return return_value
            except Exception as e:
                log.error(f"Error adding shared folder '{name}' to VM '{self.vm_name}': {e}")
                import traceback
                log.debug(f"Traceback: {traceback.format_exc()}")
                return 1
        
        return await self.manager.run_async(_add_shared_folder_async)

    def _build_mount_commands(self, name: str, mountpoint: Path) -> list:
        """Build mounting commands for a shared folder."""
        commands = []
        
        if 'windows' in self.guest_os.lower():
            from pathlib import PureWindowsPath
            unc_path = f"\\\\vboxsvr\\{name}"
            mountpoint_str = str(mountpoint)
            
            # Check if it's a drive letter (like Z:, X:, Y:, etc.)
            if len(mountpoint_str) == 2 and mountpoint_str[1] == ':' and mountpoint_str[0].isalpha():
                # Check if drive is already in use and disconnect it first
                drive_letter = mountpoint_str.upper()
                commands.append({
                    'command': f'net use {drive_letter} /delete /y 2>$null',
                    'description': f"Disconnect existing drive {drive_letter} if present",
                    'ignore_errors': True
                })
                
                # Mount to drive letter using net use command
                mount_cmd = f'net use {drive_letter} "{unc_path}" /persistent:yes'
                commands.append({
                    'command': mount_cmd,
                    'description': f"Mount shared folder {name} to drive {drive_letter}",
                    'ignore_errors': False
                })
            else:
                # Mount to directory path using symbolic link (copy behavior from old API)
                from pathlib import PureWindowsPath
                win_mountpoint = mountpoint_str.replace('/', '\\')
                parent_dir = PureWindowsPath(win_mountpoint).parent.as_posix()
                
                # Create parent directory
                commands.append({
                    'command': f'if (!(Test-Path "{parent_dir}")) {{ New-Item -ItemType Directory -Path "{parent_dir}" -Force }}',
                    'description': f"Create parent directory for {name}",
                    'ignore_errors': True
                })
                
                # Remove existing symbolic link if it exists
                commands.append({
                    'command': f'if (Test-Path "{win_mountpoint}") {{ Remove-Item "{win_mountpoint}" -Force -Recurse -ErrorAction SilentlyContinue }}',
                    'description': f"Remove existing link for {name}",
                    'ignore_errors': True
                })
                
                # Create symbolic link (exact copy from old API)
                mount_cmd = f'mklink /D "{win_mountpoint}" "{unc_path}"'
                commands.append({
                    'command': f"cmd /c '{mount_cmd}'",
                    'description': f"Create symlink for {name}",
                    'ignore_errors': False
                })
        else:
            # Linux mounting with proper permissions for adare user
            unix_mountpoint = str(mountpoint)
            
            # Create mount point directory
            commands.append({
                'command': f'sudo mkdir -p {unix_mountpoint}',
                'description': f"Create mount point for {name}",
                'ignore_errors': True
            })
            
            # Check if already mounted and unmount if necessary
            commands.append({
                'command': f'sudo umount {unix_mountpoint} 2>/dev/null || true',
                'description': f"Unmount existing mount at {unix_mountpoint} if present",
                'ignore_errors': True
            })
            
            # Mount with proper uid/gid for adare user (1000:1000)
            # Use /sbin/mount.vboxsf directly for better stability
            commands.append({
                'command': f'sudo /sbin/mount.vboxsf -o uid=1000,gid=1000,dmode=775,fmode=664 {name} {unix_mountpoint}',
                'description': f"Mount shared folder {name} with adare user permissions",
                'ignore_errors': False
            })
        
        return commands

    async def mount_shared_folder(self, name: str, mountpoint: Path, ctx_manager=None, stop_event=None, log_file: Optional[Path] = None, silent: bool = False):
        """Mount a shared folder inside the guest VM."""
        async def _mount_shared_folder_async():
            try:
                log.info(f"Mounting shared folder '{name}' to '{mountpoint}' in VM '{self.vm_name}'")
                
                commands = self._build_mount_commands(name, mountpoint)
                total_return_value = 0
                
                for cmd_info in commands:
                    command = cmd_info['command']
                    description = cmd_info['description']
                    ignore_errors = cmd_info['ignore_errors']
                    
                    if not silent:
                        log.info(f"[{self.vm_name}] {description}")
                    
                    args = self._build_guest_command_args(command)
                    return_value, _, _ = await self._execute_streaming_command_async(
                        args,
                        log_file=log_file,
                        stop_event=stop_event,
                        silent=silent,
                        ctx_manager=ctx_manager,
                        operation_name=f"mount command: {description}"
                    )
                    
                    if return_value != 0:
                        if ignore_errors:
                            log.debug(f"Command failed but errors ignored: {description}")
                        else:
                            log.error(f"Mount command failed: {description}")
                            total_return_value = return_value
                            break
                
                if total_return_value == 0:
                    log.info(f"Shared folder '{name}' mounted successfully to '{mountpoint}' in VM '{self.vm_name}'")
                
                return total_return_value
                
            except Exception as e:
                log.error(f"Error mounting shared folder '{name}' in VM '{self.vm_name}': {e}")
                return 1
        
        return await self.manager.run_async(_mount_shared_folder_async)

    async def _execute_linux_mount_with_retry(self, mount_command: str, description: str, stop_event=None, max_retries: int = 2) -> bool:
        """
        Execute a Linux mount command with retry logic.

        Args:
            mount_command: The mount command to execute
            description: Description of what's being mounted
            stop_event: Event to check for cancellation
            max_retries: Maximum number of retries (default: 2, so 3 total attempts)

        Returns:
            True if mount succeeded, False if all retries exhausted
        """
        retry_delays = [1, 3]  # Delays in seconds: 1s after first failure, 3s after second

        for attempt in range(max_retries + 1):  # +1 for initial attempt
            if stop_event and stop_event.is_set():
                log.info("Mount operation cancelled by stop event")
                return False

            attempt_label = f"attempt {attempt + 1}/{max_retries + 1}"
            if attempt == 0:
                log.info(f"Executing mount command: {description}")
            else:
                log.info(f"Retrying mount command ({attempt_label}): {description}")

            # Execute the mount command
            args = self._build_guest_command_args(mount_command)
            return_value, stdout, stderr = await self._execute_streaming_command_async(
                args,
                stop_event=stop_event,
                silent=False,
                operation_name=f"mount {description} ({attempt_label})"
            )

            if return_value == 0:
                log.info(f"Mount succeeded on {attempt_label}: {description}")
                return True
            else:
                # Mount failed
                log.warning(f"Mount failed on {attempt_label}: {description} (return code: {return_value})")
                if stderr:
                    log.debug(f"Mount error output: {stderr.strip()}")

                # If this wasn't the last attempt, wait before retrying
                if attempt < max_retries:
                    delay = retry_delays[attempt]
                    log.info(f"Waiting {delay}s before retry...")
                    await asyncio.sleep(delay)

        # All retries exhausted
        log.error(f"Mount failed after {max_retries + 1} attempts: {description}")
        return False

    async def list_shared_folders(self, ctx_manager=None, stop_event=None, log_file: Optional[Path] = None, silent: bool = False) -> Dict[str, SharedFolderConfig]:
        """List all shared folders for the VM."""
        async def _list_shared_folders_async():
            try:
                result = run_subprocess(
                    [self.vboxmanage_exe, "showvminfo", self.vm_name, "--machinereadable"],
                    log_prefix="list_shared_folders: ",
                    check=False,
                    timeout=30
                )

                if result.returncode != 0:
                    log.warning(f"Failed to get VM info for '{self.vm_name}': return code {result.returncode}")
                    return {}

                # O(n) single-pass parsing: build three dictionaries
                name_map = {}      # {mapping_num: folder_name}
                path_map = {}      # {mapping_num: folder_path}
                readonly_map = {}  # {mapping_num: readonly_bool}

                for line in result.stdout.split('\n'):
                    try:
                        if line.startswith('SharedFolderNameMachineMapping'):
                            # Extract: SharedFolderNameMachineMapping3="my_folder"
                            remainder = line[len('SharedFolderNameMachineMapping'):]
                            mapping_num, value = remainder.split('=', 1)
                            name_map[mapping_num] = value.strip('"')

                        elif line.startswith('SharedFolderPathMachineMapping'):
                            remainder = line[len('SharedFolderPathMachineMapping'):]
                            mapping_num, value = remainder.split('=', 1)
                            path_map[mapping_num] = value.strip('"')

                        elif line.startswith('SharedFolderReadOnlyMachineMapping'):
                            remainder = line[len('SharedFolderReadOnlyMachineMapping'):]
                            mapping_num, value = remainder.split('=', 1)
                            readonly_map[mapping_num] = value.strip('"').lower() == 'on'

                    except ValueError as e:
                        log.warning(f"Failed to parse shared folder mapping line: {line} - {e}")
                        continue

                # Combine mappings into SharedFolderConfig objects
                shared_folders = {}
                for mapping_num, folder_name in name_map.items():
                    try:
                        folder_path = path_map.get(mapping_num, "")
                        readonly = readonly_map.get(mapping_num, False)

                        shared_folders[folder_name] = SharedFolderConfig(
                            name=folder_name,
                            host_path=folder_path,
                            readonly=readonly
                        )
                    except ValueError as e:
                        log.warning(f"Failed to create SharedFolderConfig for mapping {mapping_num}: {e}")

                if not silent:
                    log.debug(f"Found {len(shared_folders)} shared folders for VM '{self.vm_name}'")
                return shared_folders

            except subprocess.TimeoutExpired:
                log.error(f"Timeout listing shared folders for VM '{self.vm_name}' (30s limit exceeded)")
                return {}
            except ValueError as e:
                log.error(f"Error parsing shared folder data for VM '{self.vm_name}': {e}")
                return {}

        return await self.manager.run_async(_list_shared_folders_async)

    async def remove_shared_folder(self, name: str, mountpoint: Optional[str] = None, ctx_manager=None, stop_event=None, log_file: Optional[Path] = None, silent: bool = False):
        """Remove a shared folder from the VM."""
        async def _remove_shared_folder_async():
            try:
                log.info(f"Removing shared folder '{name}' from VM '{self.vm_name}'")
                
                # First try to unmount from guest if mountpoint provided
                if mountpoint:
                    if 'windows' in self.guest_os.lower():
                        if len(mountpoint) == 2 and mountpoint[1] == ':':
                            # Drive letter
                            unmount_cmd = f'net use {mountpoint.upper()} /delete /y'
                        else:
                            # Directory path - remove symbolic link
                            unmount_cmd = f'if (Test-Path "{mountpoint}") {{ Remove-Item "{mountpoint}" -Force -Recurse }}'
                    else:
                        # Linux guest
                        unmount_cmd = f'sudo umount "{mountpoint}" 2>/dev/null || true'
                    
                    args = self._build_guest_command_args(unmount_cmd)
                    try:
                        await self._execute_streaming_command_async(
                            args,
                            log_file=log_file,
                            stop_event=stop_event,
                            silent=True,  # Don't log unmount errors
                            ctx_manager=ctx_manager,
                            operation_name="shared folder unmount"
                        )
                    except Exception:
                        pass  # Ignore unmount errors
                
                # Remove shared folder from VM configuration
                args = ["sharedfolder", "remove", self.vm_name, "--name", name]
                return_value, _, _ = await self._execute_streaming_command_async(
                    args,
                    log_file=log_file,
                    stop_event=stop_event,
                    silent=silent,
                    ctx_manager=ctx_manager,
                    operation_name="shared folder removal"
                )
                
                if return_value == 0:
                    log.info(f"Shared folder '{name}' removed successfully from VM '{self.vm_name}'")
                else:
                    log.error(f"Failed to remove shared folder '{name}' from VM '{self.vm_name}': return code {return_value}")
                
                return return_value
            except Exception as e:
                log.error(f"Error removing shared folder '{name}' from VM '{self.vm_name}': {e}")
                return 1
        
        return await self.manager.run_async(_remove_shared_folder_async)

    async def remove_all_shared_folders(self, ctx_manager=None, stop_event=None, log_file: Optional[Path] = None, silent: bool = False):
        """Remove all shared folders from the VM."""
        async def _remove_all_shared_folders_async():
            try:
                log.info(f"Removing all shared folders from VM '{self.vm_name}'")
                
                # First get list of all shared folders
                shared_folders = await self.list_shared_folders(ctx_manager, stop_event, log_file, silent=True)
                
                if not shared_folders:
                    if not silent:
                        log.info(f"No shared folders found for VM '{self.vm_name}'")
                    return 0
                
                total_return_value = 0
                for folder_name in shared_folders.keys():
                    return_value = await self.remove_shared_folder(
                        folder_name,
                        ctx_manager=ctx_manager,
                        stop_event=stop_event,
                        log_file=log_file,
                        silent=silent
                    )
                    if return_value != 0:
                        total_return_value = return_value
                
                if total_return_value == 0:
                    log.info(f"All shared folders removed successfully from VM '{self.vm_name}'")
                
                return total_return_value
            except Exception as e:
                log.error(f"Error removing all shared folders from VM '{self.vm_name}': {e}")
                return 1
        
        return await self.manager.run_async(_remove_all_shared_folders_async)

    def queue_mount_shared_folder(self, name: str, mountpoint: Path):
        """Queue a shared folder mount command using the consolidated mounting logic."""
        commands = self._build_mount_commands(name, mountpoint)
        # Queue all the commands from the consolidated logic
        for cmd_info in commands:
            self.queue_command(cmd_info['command'], cmd_info['description'])

    async def mount_multiple_shared_folders(self, folders: dict, ctx_manager=None, stop_event=None, log_file: Optional[Path] = None, silent: bool = False):
        """Mount multiple shared folders with retry logic for Linux mounts."""
        is_linux = 'linux' in self.guest_os.lower()

        # Phase 1: Setup (cleanup and directory creation) - no retries needed
        self.clear_command_queue()

        if is_linux:
            # Clean slate approach: remove /adare directory to avoid any mount conflicts
            self.queue_command('sudo rm -rf /adare 2>/dev/null || true', "Remove /adare directory to clean any stale mounts")

            # Create parent directories and set ownership
            processed_parents = set()
            for name, mountpoint in folders.items():
                parent_dir = mountpoint.parent
                parent_str = str(parent_dir)

                if parent_str not in processed_parents:
                    mkdir_command = f'sudo mkdir -p {parent_dir}'
                    chown_command = f'sudo chown -R adare:adare {parent_dir}'
                    self.queue_command(mkdir_command, f"Create parent directory {parent_dir}")
                    self.queue_command(chown_command, f"Set ownership of {parent_dir} to adare user")
                    processed_parents.add(parent_str)

            # Execute setup commands
            log.info("Executing directory setup commands")
            setup_result = await self.execute_queued_commands(ctx_manager, stop_event, log_file, silent, win_noprofile=True)
            if setup_result != 0:
                log.error(f"Directory setup failed with return code {setup_result}")
                return setup_result

        # Phase 2: Mount commands - with retry logic for Linux
        if is_linux:
            # Execute mount commands individually with retry logic
            log.info(f"Mounting {len(folders)} shared folders with retry logic")
            for name, mountpoint in folders.items():
                # Create mount point
                mkdir_cmd = f'sudo mkdir -p {mountpoint}'
                umount_cmd = f'sudo umount {mountpoint} 2>/dev/null || true'
                # Use /sbin/mount.vboxsf directly for better stability
                mount_cmd = f'sudo /sbin/mount.vboxsf -o uid=1000,gid=1000,dmode=775,fmode=664 {name} {mountpoint}'

                # Execute mkdir and umount without retry
                log.debug(f"Creating mount point {mountpoint}")
                args = self._build_guest_command_args(mkdir_cmd)
                await self._execute_streaming_command_async(args, stop_event=stop_event, silent=True)

                log.debug(f"Unmounting any existing mount at {mountpoint}")
                args = self._build_guest_command_args(umount_cmd)
                await self._execute_streaming_command_async(args, stop_event=stop_event, silent=True)

                # Execute mount with retry logic
                mount_success = await self._execute_linux_mount_with_retry(
                    mount_cmd,
                    f"shared folder {name} to {mountpoint}",
                    stop_event=stop_event,
                    max_retries=2
                )

                if not mount_success:
                    # Mount failed after retries - raise exception to stop execution
                    from adare.exceptions import LoggedException
                    raise LoggedException(
                        log,
                        f"Failed to mount shared folder '{name}' after 3 attempts (initial + 2 retries). "
                        f"This likely indicates VirtualBox shared folder is not properly configured or Guest Additions issue."
                    )

            log.info("All shared folders mounted successfully")
            return 0
        else:
            # Windows: use existing queue-based approach (no retry needed for Windows)
            for name, mountpoint in folders.items():
                self.queue_mount_shared_folder(name, mountpoint)

            return await self.execute_queued_commands(ctx_manager, stop_event, log_file, silent, win_noprofile=True)