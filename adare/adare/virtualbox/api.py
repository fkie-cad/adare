"""
VirtualBox API - Main VM class with modular operations.
"""
import asyncio
import contextlib
import logging
import platform
import threading
from pathlib import Path
from typing import Optional, List, Dict, Any

from adarelib.constants import StatusEnum

from .manager import VirtualBoxManager
from .models import VMImportException, VMAlreadyRunningException, VMNotFoundException
from .commands import CommandExecutionMixin
from .snapshots import SnapshotMixin
from .networking import NetworkingMixin
from .utils import run_subprocess, read_file_hash

log = logging.getLogger(__name__)


class VirtualBoxVM(CommandExecutionMixin, SnapshotMixin, NetworkingMixin):
    """
    VirtualBox VM management class with modular operations.
    Inherits from mixins for command execution, snapshots, and networking.
    """
    
    def __init__(
        self,
        vm_name: str,
        guest_os: str,
        manager: 'VirtualBoxManager',
        username: str,
        password: str,
        cpus: int = 1,
        ram: int = 1024,
        network: str = "nat"
    ):
        self.vm_name = vm_name
        self.guest_os = guest_os
        self.username = username
        self.password = password
        self.cpus = cpus
        self.ram = ram
        self.network = network
        self.host_os = platform.system().lower()
        self.vboxmanage_exe = 'VBoxManage.exe' if self.host_os == 'windows' else 'VBoxManage'
        self.manager = manager
        self._background_pids = []
        self._command_queue = []
        log.info(f"Initialized VirtualBoxVM for '{self.vm_name}' ({self.guest_os})")

    async def create(self, ctx_manager=None, stop_event=None, log_file: Optional[Path] = None, silent: bool = False):
        """Create a new VM with the specified configuration."""
        async def _create_async():
            log.info(f"Creating VM '{self.vm_name}' with {self.cpus} CPUs, {self.ram}MB RAM, network: {self.network}")
            commands = [
                ["createvm", "--name", self.vm_name, "--register"],
                ["modifyvm", self.vm_name, "--ostype", self.guest_os],
                ["modifyvm", self.vm_name, "--cpus", str(self.cpus)],
                ["modifyvm", self.vm_name, "--memory", str(self.ram)],
                ["modifyvm", self.vm_name, "--nic1", self.network],
                ["modifyvm", self.vm_name, "--graphicscontroller", "vmsvga"],
                ["modifyvm", self.vm_name, "--vram", "128"]
            ]
            
            total_return_value = 0
            for args in commands:
                return_value, _, _ = await self._execute_streaming_command_async(
                    args, 
                    log_file=log_file,
                    stop_event=stop_event,
                    silent=silent,
                    ctx_manager=ctx_manager,
                    operation_name=f"VM creation step: {args[0]}"
                )
                if return_value != 0:
                    total_return_value = return_value
                    break
            
            if total_return_value == 0:
                log.info(f"VM '{self.vm_name}' created and configured.")
            return total_return_value
        
        return await self.manager.run_async(_create_async)

    async def start(self, ctx_manager=None, raise_if_running: bool = False, stop_event=None, log_file: Optional[Path] = None, silent: bool = False):
        """Start the VM."""
        async def _start_async():
            current_state = self._get_state(raise_on_missing=False)
            
            if current_state == "running":
                message = f"VM '{self.vm_name}' is already running."
                if raise_if_running:
                    raise VMAlreadyRunningException(message)
                log.info(message)
                return 0
            
            log.info(f"Starting VM '{self.vm_name}'")
            args = ["startvm", self.vm_name, "--type", "headless"]
            
            return_value, _, _ = await self._execute_streaming_command_async(
                args,
                log_file=log_file,
                stop_event=stop_event,
                silent=silent,
                ctx_manager=ctx_manager,
                operation_name="VM startup"
            )
            
            if return_value == 0:
                log.info(f"VM '{self.vm_name}' started successfully")
            else:
                log.error(f"Failed to start VM '{self.vm_name}': return code {return_value}")
            
            return return_value
        
        return await self.manager.run_async(_start_async)

    async def set_video_mode_hint(self, width: int = 1920, height: int = 1080, depth: int = 32, ctx_manager=None, stop_event=None, log_file: Optional[Path] = None, silent: bool = False):
        """Set video mode hint for the VM (must be running)."""
        async def _set_video_mode_async():
            state = self._get_state()
            if state != "running":
                log.warning(f"VM '{self.vm_name}' is not running (state: {state}). Cannot set video mode hint.")
                return 1
            
            log.info(f"Setting video mode hint for VM '{self.vm_name}' to {width}x{height}x{depth}")
            args = ["controlvm", self.vm_name, "setvideomodehint", str(width), str(height), str(depth)]
            return_value, _, _ = await self._execute_streaming_command_async(
                args,
                log_file=log_file,
                stop_event=stop_event,
                silent=silent,
                ctx_manager=ctx_manager,
                operation_name="video mode hint"
            )
            
            if return_value == 0:
                log.info(f"Video mode hint set successfully for VM '{self.vm_name}'")
            else:
                log.error(f"Failed to set video mode hint for VM '{self.vm_name}': return code {return_value}")
            
            return return_value
        
        return await self.manager.run_async(_set_video_mode_async)

    async def run_command(
        self,
        command: str,
        background: bool = False,
        silent: bool = False,
        stop_event: Optional[threading.Event] = None,
        cwd: Optional[str] = None,
        win_noprofile: bool = True,
        use_cmd: bool = False
    ):
        """Run a command inside the VM guest."""
        from collections import namedtuple
        CommandResult = namedtuple('CommandResult', ['returncode', 'stdout', 'stderr'])

        async def _run_command_async():
            try:
                log.info(f"Running command in VM '{self.vm_name}': {command}")

                args = self._build_guest_command_args(command, background, cwd, win_noprofile, use_cmd)
                return_value, stdout, stderr = await self._execute_streaming_command_async(
                    args,
                    stop_event=stop_event,
                    silent=silent,
                    operation_name=f"guest command: {command}"
                )

                if background and return_value == 0:
                    # For background commands, try to extract PID from stdout
                    try:
                        pid = int(stdout.strip().split('\n')[-1])
                        self._background_pids.append(pid)
                        log.info(f"Background command started with PID {pid}")
                    except (ValueError, IndexError):
                        log.debug(f"Could not extract PID from background command output: {stdout}")

                return CommandResult(returncode=return_value, stdout=stdout, stderr=stderr)
            except Exception as e:
                log.error(f"Error running command in VM '{self.vm_name}': {e}")
                return CommandResult(returncode=1, stdout='', stderr=str(e))

        return await self.manager.run_async(_run_command_async)

    def queue_command(self, command: str, description: str = None):
        """Add a command to the queue for batch execution."""
        self._command_queue.append({
            'command': command,
            'description': description or f"Execute: {command}"
        })
        log.debug(f"Queued command for VM '{self.vm_name}': {description or command}")

    def clear_command_queue(self):
        """Clear all queued commands."""
        cleared_count = len(self._command_queue)
        self._command_queue.clear()
        log.debug(f"Cleared {cleared_count} queued commands for VM '{self.vm_name}'")

    async def execute_queued_commands(self, ctx_manager=None, stop_event=None, log_file: Optional[Path] = None, silent: bool = False, win_noprofile: bool = False):
        """Execute all queued commands in a single batch."""
        async def _execute_queued_commands_async():
            if not self._command_queue:
                log.info(f"No queued commands to execute for VM '{self.vm_name}'")
                return 0
            
            log.info(f"Executing {len(self._command_queue)} queued commands for VM '{self.vm_name}'")
            total_return_value = 0
            
            for cmd_info in self._command_queue:
                command = cmd_info['command']
                description = cmd_info['description']
                
                if not silent:
                    log.info(f"[{self.vm_name}] {description}")
                
                return_value = await self.run_command(
                    command,
                    silent=silent,
                    stop_event=stop_event,
                    win_noprofile=win_noprofile,
                    use_cmd='net use' in command or 'mklink' in command
                )

                if return_value.returncode != 0:
                    log.error(f"Command failed in VM '{self.vm_name}': {description}")
                    total_return_value = return_value.returncode
                    break
            
            # Clear the queue after execution
            self.clear_command_queue()
            
            if total_return_value == 0:
                log.info(f"All queued commands executed successfully for VM '{self.vm_name}'")
            
            return total_return_value
        
        return await self.manager.run_async(_execute_queued_commands_async)

    def cleanup_background_processes(self):
        """Kill all tracked background processes."""
        if not self._background_pids:
            return
        
        if 'windows' in self.guest_os.lower():
            for pid in self._background_pids:
                try:
                    kill_cmd = f"taskkill /F /PID {pid}"
                    log.debug(f"Killing background process {pid} in VM '{self.vm_name}'")
                    # Don't await this, just fire and forget
                    asyncio.create_task(self.run_command(kill_cmd, silent=True))
                except Exception as e:
                    log.debug(f"Failed to kill background process {pid}: {e}")
        else:
            for pid in self._background_pids:
                try:
                    kill_cmd = f"kill -9 {pid}"
                    log.debug(f"Killing background process {pid} in VM '{self.vm_name}'")
                    asyncio.create_task(self.run_command(kill_cmd, silent=True))
                except Exception as e:
                    log.debug(f"Failed to kill background process {pid}: {e}")
        
        self._background_pids.clear()
        log.debug(f"Cleaned up background processes for VM '{self.vm_name}'")

    def is_fully_booted(self, silent: bool = False) -> bool:
        """Check if the VM is fully booted by running a simple test command."""
        try:
            command = "echo Fully booted"
            return_value = asyncio.run(self.run_command(command, silent=silent))
            is_booted = return_value == 0
            if is_booted and not silent:
                log.info(f"VM '{self.vm_name}' is fully booted.")
            elif not is_booted and not silent:
                log.debug(f"VM '{self.vm_name}' is not fully booted yet.")
            return is_booted
        except Exception as e:
            if not silent:
                log.debug(f"Error checking if VM '{self.vm_name}' is booted: {e}")
            return False

    async def stop(self, ctx_manager=None, log_file: Optional[Path] = None, silent: bool = False):
        """Stop the VM."""
        async def _stop_async():
            current_state = self._get_state(raise_on_missing=False)
            
            if current_state not in ["running", "paused"]:
                log.info(f"VM '{self.vm_name}' is not running (state: {current_state})")
                return 0
            
            log.info(f"Stopping VM '{self.vm_name}'")
            args = ["controlvm", self.vm_name, "poweroff"]
            
            return_value, _, _ = await self._execute_streaming_command_async(
                args,
                log_file=log_file,
                stop_event=None,  # Don't allow stopping the stop operation
                silent=silent,
                ctx_manager=ctx_manager,
                operation_name="VM shutdown"
            )
            
            if return_value == 0:
                log.info(f"VM '{self.vm_name}' stopped successfully")
            else:
                log.error(f"Failed to stop VM '{self.vm_name}': return code {return_value}")
            
            return return_value
        
        return await self.manager.run_async(_stop_async)

    async def remove(self, ctx_manager=None, stop_event=None, log_file: Optional[Path] = None, silent: bool = False):
        """Remove the VM completely."""
        async def _remove_async():
            try:
                log.info(f"Removing VM '{self.vm_name}' completely")
                
                # First try to stop the VM if it's running
                current_state = self._get_state(raise_on_missing=False)
                if current_state in ["running", "paused"]:
                    log.info(f"VM '{self.vm_name}' is {current_state}, stopping it first")
                    await self.stop(ctx_manager=ctx_manager, log_file=log_file, silent=silent)
                
                args = ["unregistervm", self.vm_name, "--delete"]
                return_value, _, _ = await self._execute_streaming_command_async(
                    args,
                    log_file=log_file,
                    stop_event=stop_event,
                    silent=silent,
                    ctx_manager=ctx_manager,
                    operation_name="VM removal"
                )
                
                if return_value == 0:
                    log.info(f"VM '{self.vm_name}' removed successfully")
                else:
                    log.error(f"Failed to remove VM '{self.vm_name}': return code {return_value}")
                
                return return_value
            except Exception as e:
                log.error(f"Error removing VM '{self.vm_name}': {e}")
                return 1
        
        return await self.manager.run_async(_remove_async)

    async def destroy(self, ctx_manager=None, stop_event=None, log_file: Optional[Path] = None, silent: bool = False):
        """Alias for remove() method for consistency with other VM operations."""
        return await self.remove(ctx_manager=ctx_manager, stop_event=stop_event, log_file=log_file, silent=silent)

    def _get_state(self, raise_on_missing: bool = True) -> str:
        """Get the current state of the VM."""
        def _get_vm_state():
            try:
                result = run_subprocess(
                    [self.vboxmanage_exe, "showvminfo", self.vm_name, "--machinereadable"],
                    log_prefix=f"_get_state({self.vm_name}): ",
                    check=False
                )
                
                if result.returncode != 0:
                    if raise_on_missing:
                        raise VMNotFoundException(f"VM '{self.vm_name}' not found")
                    return "not_found"
                
                # Parse the output for the VM state
                for line in result.stdout.split('\n'):
                    if line.startswith('VMState='):
                        state = line.split('=', 1)[1].strip('"')
                        log.debug(f"VM '{self.vm_name}' state: {state}")
                        return state
                
                log.warning(f"Could not determine state for VM '{self.vm_name}'")
                return "unknown"
            except Exception as e:
                log.error(f"Error getting state for VM '{self.vm_name}': {e}")
                if raise_on_missing:
                    raise
                return "error"
        
        return self.manager.run(_get_vm_state)

    def get_state(self) -> str:
        """Public method to get the current state of the VM."""
        return self._get_state(raise_on_missing=True)

    def vm_exists(self) -> bool:
        """Check if the VM exists."""
        def _vm_exists():
            try:
                result = run_subprocess(
                    [self.vboxmanage_exe, "showvminfo", self.vm_name, "--machinereadable"],
                    log_prefix=f"vm_exists({self.vm_name}): ",
                    check=False
                )
                exists = result.returncode == 0
                log.debug(f"VM '{self.vm_name}' exists: {exists}")
                return exists
            except Exception as e:
                log.error(f"Error checking if VM '{self.vm_name}' exists: {e}")
                return False
        
        return self.manager.run(_vm_exists)

    @classmethod
    def get_vm_by_name(cls, vm_name: str, manager: Optional[VirtualBoxManager] = None):
        """Get VM information by name and create a VirtualBoxVM instance."""
        def _get_vm_info():
            try:
                vboxmanage_exe = 'VBoxManage.exe' if platform.system().lower() == 'windows' else 'VBoxManage'
                result = run_subprocess(
                    [vboxmanage_exe, "showvminfo", vm_name, "--machinereadable"],
                    log_prefix=f"get_vm_by_name({vm_name}): ",
                    check=False
                )
                
                if result.returncode != 0:
                    log.warning(f"VM '{vm_name}' not found")
                    return None
                
                # Parse VM information
                vm_info = {}
                for line in result.stdout.split('\n'):
                    if '=' in line:
                        key, value = line.split('=', 1)
                        vm_info[key] = value.strip('"')
                
                # Extract relevant information
                guest_os = vm_info.get('ostype', 'Other')
                cpus = int(vm_info.get('cpus', '1'))
                ram = int(vm_info.get('memory', '1024'))
                
                # Create VirtualBoxVM instance
                if manager is None:
                    manager = VirtualBoxManager()
                
                vm = cls(
                    vm_name=vm_name,
                    guest_os=guest_os,
                    manager=manager,
                    cpus=cpus,
                    ram=ram
                )
                
                log.info(f"Retrieved VM '{vm_name}' with {cpus} CPUs, {ram}MB RAM, OS: {guest_os}")
                return vm
                
            except Exception as e:
                log.error(f"Error getting VM info for '{vm_name}': {e}")
                return None
        
        if manager is None:
            manager = VirtualBoxManager()
        
        return manager.run(_get_vm_info)

    @staticmethod
    def get_vm_uuid_by_name(vm_name: str) -> Optional[str]:
        """Get VM UUID by name."""
        try:
            vboxmanage_exe = 'VBoxManage.exe' if platform.system().lower() == 'windows' else 'VBoxManage'
            result = run_subprocess(
                [vboxmanage_exe, "showvminfo", vm_name, "--machinereadable"],
                log_prefix=f"get_vm_uuid_by_name({vm_name}): ",
                check=False
            )
            
            if result.returncode != 0:
                return None
            
            for line in result.stdout.split('\n'):
                if line.startswith('UUID='):
                    uuid = line.split('=', 1)[1].strip('"')
                    log.debug(f"VM '{vm_name}' UUID: {uuid}")
                    return uuid
            
            return None
        except Exception as e:
            log.error(f"Error getting UUID for VM '{vm_name}': {e}")
            return None

    def get_vm_uuid(self) -> Optional[str]:
        """Get VM UUID for this instance (convenience method)."""
        return self.get_vm_uuid_by_name(self.vm_name)

    @staticmethod
    def get_vm_info_by_uuid(vbox_uuid: str) -> Optional[dict]:
        """Get VM information by UUID."""
        try:
            vboxmanage_exe = 'VBoxManage.exe' if platform.system().lower() == 'windows' else 'VBoxManage'
            result = run_subprocess(
                [vboxmanage_exe, "showvminfo", vbox_uuid, "--machinereadable"],
                log_prefix=f"get_vm_info_by_uuid({vbox_uuid}): ",
                check=False
            )
            
            if result.returncode != 0:
                return None
            
            vm_info = {}
            for line in result.stdout.split('\n'):
                if '=' in line:
                    key, value = line.split('=', 1)
                    vm_info[key] = value.strip('"')
            
            return vm_info
        except Exception as e:
            log.error(f"Error getting VM info by UUID '{vbox_uuid}': {e}")
            return None

    @staticmethod
    def verify_vm_exists_by_uuid(vbox_uuid: str) -> bool:
        """Verify if a VM exists by its UUID."""
        try:
            vboxmanage_exe = 'VBoxManage.exe' if platform.system().lower() == 'windows' else 'VBoxManage'
            result = run_subprocess(
                [vboxmanage_exe, "showvminfo", vbox_uuid, "--machinereadable"],
                log_prefix=f"verify_vm_exists_by_uuid({vbox_uuid}): ",
                check=False
            )
            return result.returncode == 0
        except Exception as e:
            log.error(f"Error verifying VM existence by UUID '{vbox_uuid}': {e}")
            return False

    @staticmethod
    def get_vm_name_by_uuid(vbox_uuid: str) -> Optional[str]:
        """Get VM name by UUID."""
        try:
            vm_info = VirtualBoxVM.get_vm_info_by_uuid(vbox_uuid)
            if vm_info:
                return vm_info.get('name')
            return None
        except Exception as e:
            log.error(f"Error getting VM name by UUID '{vbox_uuid}': {e}")
            return None

    async def wait_until_fully_booted(self, timeout: int = 300, ctx_manager=None, stop_event: Optional[threading.Event] = None):
        """Wait until VM is fully booted and accessible."""
        async def _wait_async():
            with ctx_manager if ctx_manager else contextlib.nullcontext():
                import time
                start_time = time.time()
                last_vm_check = 0
                while time.time() - start_time < timeout:
                    # Check stop_event every 0.2s
                    if stop_event and stop_event.is_set():
                        log.info(f"Stop event detected while waiting for VM '{self.vm_name}' to boot")
                        if ctx_manager:
                            ctx_manager.set_status(StatusEnum.INTERRUPTED)
                        return False
                    current_time = time.time()
                    if current_time - last_vm_check >= 3:
                        last_vm_check = current_time
                        try:
                            if self.guest_os.lower() == 'windows':
                                exe = "cmd.exe"
                                args = ["/c", "echo", "Ready"]
                            else:
                                exe = "/bin/echo"
                                args = ["Ready"]
                            # Use async subprocess for responsive cancellation
                            proc = await asyncio.create_subprocess_exec(
                                self.vboxmanage_exe, "guestcontrol", self.vm_name,
                                "--username", self.username, "--password", self.password,
                                "run", "--exe", exe, "--", *args,
                                stdout=asyncio.subprocess.PIPE,
                                stderr=asyncio.subprocess.PIPE
                            )
                            try:
                                stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=10)
                                stdout_str = stdout.decode('utf-8', errors='replace')
                                stderr_str = stderr.decode('utf-8', errors='replace')
                                
                                if proc.returncode == 0 and "Ready" in stdout_str:
                                    log.info(f"VM '{self.vm_name}' is fully booted and responsive")
                                    return True
                                else:
                                    log.debug(f"VM not ready yet. Output: {stdout_str.strip()}, Error: {stderr_str.strip()}")
                            except asyncio.TimeoutError:
                                log.debug(f"VM '{self.vm_name}' boot check timed out")
                                proc.kill()
                                await proc.wait()
                        except Exception as e:
                            log.debug(f"Error checking VM '{self.vm_name}' boot status: {e}")
                    
                    await asyncio.sleep(0.2)
                
                log.warning(f"VM '{self.vm_name}' did not boot within {timeout} seconds")
                return False
        
        return await self.manager.run_async(_wait_async)

    async def create_from_ovf_or_ova(self, file_path: Path, try_extract: bool = True, ctx_manager=None, stop_event=None, log_file: Optional[Path] = None, silent: bool = False):
        """Create VM by importing from OVF or OVA file."""
        async def _import_async():
            with ctx_manager if ctx_manager else contextlib.nullcontext():
                if file_path.suffix.lower() not in ('.ovf', '.ova'):
                    log.error("File must be .ovf or .ova")
                    raise VMImportException(f"File '{file_path}' must be .ovf or .ova")

                args = [
                    "import", str(file_path),
                    "--vsys", "0",
                    "--vmname", self.vm_name
                ]

                try:
                    log.info(f"Importing VM '{self.vm_name}' from '{file_path}'")
                    return_value, stdout, stderr = await self._execute_streaming_command_async(
                        args,
                        log_file=log_file,
                        stop_event=stop_event,
                        silent=silent,
                        ctx_manager=ctx_manager,
                        operation_name="VM import"
                    )

                    if return_value == 0:
                        log.info(f"VM '{self.vm_name}' imported successfully from '{file_path}'")
                    else:
                        # Log the actual VirtualBox error output
                        error_output = stdout.strip() if stdout.strip() else "No error output"
                        log.error(f"Failed to import VM '{self.vm_name}' from '{file_path}': return code {return_value}. VirtualBox output: {error_output}")

                    return return_value, stdout
                except Exception as e:
                    log.error(f"Error importing VM '{self.vm_name}' from '{file_path}': {e}")
                    raise VMImportException(f"Failed to import VM '{self.vm_name}' from '{file_path}': {e}")

        return await self.manager.run_async(_import_async)

    def ovf_is_identical(self, ovf_path: str) -> bool:
        """Check if OVF file is identical to stored hash."""
        def _ovf_is_identical():
            try:
                current_hash = read_file_hash(ovf_path)
                if not current_hash:
                    return False
                
                # Get stored hash from VM info
                result = run_subprocess(
                    [self.vboxmanage_exe, "getextradata", self.vm_name, "ovf_hash"],
                    log_prefix=f"ovf_is_identical({ovf_path}): ",
                    check=False
                )
                
                if result.returncode != 0:
                    return False
                
                stored_hash = result.stdout.strip()
                is_identical = current_hash == stored_hash
                log.debug(f"OVF hash comparison for '{self.vm_name}': {is_identical}")
                return is_identical
            except Exception as e:
                log.error(f"Error checking OVF hash for '{self.vm_name}': {e}")
                return False
        
        return self.manager.run(_ovf_is_identical)

    def store_ovf_hash(self, ovf_path: str):
        """Store OVF file hash in VM metadata."""
        def _store_ovf_hash():
            try:
                file_hash = read_file_hash(ovf_path)
                if not file_hash:
                    return False
                
                result = run_subprocess(
                    [self.vboxmanage_exe, "setextradata", self.vm_name, "ovf_hash", file_hash],
                    log_prefix=f"store_ovf_hash({ovf_path}): "
                )
                
                log.debug(f"Stored OVF hash for VM '{self.vm_name}': {file_hash}")
                return True
            except Exception as e:
                log.error(f"Error storing OVF hash for VM '{self.vm_name}': {e}")
                return False
        
        return self.manager.run(_store_ovf_hash)

    # !keep unused at the moment but maybe use later -> makes clock weird. Timezone and time do not match in vm
    async def disable_time_sync(self, ctx_manager=None, stop_event=None, log_file: Optional[Path] = None, silent: bool = False):
        """
        Disable time synchronization for the VM to prevent syncing with host time
        and configure RTC to use UTC.
        
        Args:
            ctx_manager: Context manager for operation tracking
            stop_event: Event to check for cancellation
            log_file: Optional log file for output
            silent: Whether to suppress output
        
        Returns:
            Return code (0 for success)
        """
        async def _disable_time_sync_async():
            log.info(f"Disabling time synchronization and configuring RTC for VM '{self.vm_name}'")
            
            # Commands to configure time settings
            commands = [
                ["setextradata", self.vm_name, "VBoxInternal/Devices/VMMDev/0/Config/GetHostTimeDisabled", "1"],
                ["modifyvm", self.vm_name, "--rtcuseutc", "on"]
            ]
            
            total_return_value = 0
            for args in commands:
                return_value, _, _ = await self._execute_streaming_command_async(
                    args,
                    log_file=log_file,
                    stop_event=stop_event,
                    silent=silent,
                    ctx_manager=ctx_manager,
                    operation_name=f"Time config: {args[0]}"
                )
                if return_value != 0:
                    total_return_value = return_value
                    log.error(f"Failed to execute {args[0]} for VM '{self.vm_name}': return code {return_value}")
                    break
            
            if total_return_value == 0:
                log.info(f"Successfully disabled time synchronization and set RTC to UTC for VM '{self.vm_name}'")
            
            return total_return_value
        
        return await self.manager.run_async(_disable_time_sync_async)