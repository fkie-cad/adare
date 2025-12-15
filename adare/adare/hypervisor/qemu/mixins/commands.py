"""
QEMU VM command execution operations mixin.

Implements AbstractCommandMixin for QEMU-specific command execution using:
- QEMU Guest Agent for runtime commands
- libguestfs for file operations when VM is stopped
"""
import asyncio
import json
import logging
import os
import subprocess
import threading
import time
from pathlib import Path
from typing import List, Optional, Tuple

from adare.hypervisor.base.mixins.commands import AbstractCommandMixin
from adare.hypervisor.exceptions import HypervisorException

log = logging.getLogger(__name__)


class CommandExecutionMixin(AbstractCommandMixin):
    """Mixin class providing command execution operations for QEMU VMs."""

    async def _execute_streaming_command_async(
        self,
        args: List[str],
        log_file: Optional[Path] = None,
        stop_event: Optional[threading.Event] = None,
        silent: bool = False,
        ctx_manager=None,
        operation_name: str = "command execution"
    ) -> Tuple[int, str, str]:
        """
        Execute a QEMU command asynchronously with streaming output.

        For QEMU, this typically executes qemu-img or other QEMU utilities,
        NOT guest commands (those use Guest Agent).

        Args:
            args: Command arguments list
            log_file: Optional path to log file
            stop_event: Optional threading event to signal cancellation
            silent: If True, suppress log output
            ctx_manager: Optional context manager for status updates
            operation_name: Description of operation

        Returns:
            Tuple of (return_code, stdout, stderr)
        """
        if not silent:
            log.info(f"CLAUDE: Executing {operation_name}: {' '.join(args)}")

        try:
            proc = await asyncio.create_subprocess_exec(
                *args,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )

            stdout_lines = []
            stderr_lines = []

            # Read output with cancellation support
            while True:
                if stop_event and stop_event.is_set():
                    log.info(f"CLAUDE: Stop event detected during {operation_name}")
                    proc.kill()
                    await proc.wait()
                    break

                try:
                    line = await asyncio.wait_for(proc.stdout.readline(), timeout=0.1)
                    if not line:
                        break
                    line_str = line.decode('utf-8', errors='replace').rstrip()
                    stdout_lines.append(line_str)
                    if not silent and log_file:
                        with open(log_file, 'a') as f:
                            f.write(line_str + '\n')
                except asyncio.TimeoutError:
                    if proc.returncode is not None:
                        break
                    continue

            # Read any remaining stderr
            stderr_data = await proc.stderr.read()
            stderr_str = stderr_data.decode('utf-8', errors='replace')
            stderr_lines.append(stderr_str)

            await proc.wait()

            stdout = '\n'.join(stdout_lines)
            stderr = '\n'.join(stderr_lines)

            if not silent:
                log.debug(f"CLAUDE: {operation_name} completed with return code {proc.returncode}")

            return proc.returncode, stdout, stderr

        except Exception as e:
            log.error(f"CLAUDE: Error executing {operation_name}: {e}")
            raise HypervisorException(f"Command execution failed: {e}")

    def _execute_streaming_command(
        self,
        args: List[str],
        log_file: Optional[Path] = None,
        stop_event: Optional[threading.Event] = None,
        silent: bool = False,
        ctx_manager=None,
        operation_name: str = "command execution",
        timeout: Optional[int] = None
    ) -> int:
        """
        Execute a QEMU command synchronously with streaming output.

        Args:
            args: Command arguments list
            log_file: Optional path to log file
            stop_event: Optional threading event to signal cancellation
            silent: If True, suppress log output
            ctx_manager: Optional context manager for status updates
            operation_name: Description of operation
            timeout: Optional timeout in seconds

        Returns:
            Return code from command execution
        """
        if not silent:
            log.info(f"CLAUDE: Executing {operation_name}: {' '.join(args)}")

        try:
            proc = subprocess.Popen(
                args,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                bufsize=0
            )

            output_lines = []
            while True:
                if stop_event and stop_event.is_set():
                    log.info(f"CLAUDE: Stop event detected during {operation_name}")
                    proc.terminate()
                    proc.wait(timeout=5)
                    break

                line = proc.stdout.readline()
                if not line:
                    break

                line_str = line.decode('utf-8', errors='replace').rstrip()
                output_lines.append(line_str)

                if not silent:
                    log.debug(f"CLAUDE: {line_str}")

                if log_file:
                    with open(log_file, 'a') as f:
                        f.write(line_str + '\n')

            proc.wait()

            if not silent:
                log.debug(f"CLAUDE: {operation_name} completed with return code {proc.returncode}")

            return proc.returncode

        except Exception as e:
            log.error(f"CLAUDE: Error executing {operation_name}: {e}")
            raise HypervisorException(f"Command execution failed: {e}")

    def _build_guest_command_args(
        self,
        command: str,
        background: bool = False,
        cwd: Optional[str] = None,
        win_noprofile: bool = True,
        use_cmd: bool = False,
        admin: bool = False
    ) -> List[str]:
        """
        Build QEMU Guest Agent command arguments.

        For QEMU, we'll execute commands via Guest Agent, so this method
        returns the command formatted for guest-exec.

        Args:
            command: Command to execute in guest
            background: If True, don't wait for command to complete
            cwd: Optional working directory
            win_noprofile: Windows-specific: ignored for QEMU
            use_cmd: Windows-specific: use cmd.exe instead of sh
            admin: If True, run with elevated privileges

        Returns:
            List of command arguments formatted for guest agent
        """
        # For guest agent, we need to determine shell based on guest OS
        if 'windows' in self.guest_os.lower():
            if use_cmd:
                shell = ['cmd.exe', '/c']
            else:
                shell = ['powershell.exe', '-Command']
        else:
            shell = ['/bin/sh', '-c']

        # Return shell command that guest agent will execute
        return shell + [command]

    async def copy_from_guest(
        self,
        guest_path: str,
        host_path: str,
        recursive: bool = True
    ) -> bool:
        """
        Copy files/directories from guest to host using libguestfs.

        IMPORTANT: VM must be stopped for this operation.

        Args:
            guest_path: Path in guest VM
            host_path: Path on host
            recursive: If True, copy directories recursively

        Returns:
            True if successful, False otherwise
        """
        log.info(f"CLAUDE: Copying '{guest_path}' from guest to '{host_path}' on host")

        # Check if VM is stopped
        if self.get_state() != "poweroff":
            log.error("CLAUDE: VM must be stopped to use libguestfs file operations")
            return False

        try:
            import guestfs
        except ImportError:
            log.error("CLAUDE: libguestfs Python bindings not available. Install python3-guestfs.")
            return False

        try:
            g = guestfs.GuestFS(python_return_dict=True)

            # Add the VM disk
            if not hasattr(self, 'config') or not hasattr(self.config, 'disk_path'):
                log.error("CLAUDE: VM config or disk_path not available")
                return False

            disk_path = self.config.disk_path
            if not os.path.exists(disk_path):
                log.error(f"CLAUDE: VM disk not found at {disk_path}")
                return False

            log.debug(f"CLAUDE: Adding disk {disk_path} to libguestfs")
            g.add_drive_opts(disk_path, readonly=1)

            # Launch and mount
            log.debug("CLAUDE: Launching libguestfs")
            g.launch()

            # Inspect and mount filesystems
            roots = g.inspect_os()
            if not roots:
                log.error("CLAUDE: No operating system found in VM disk")
                g.close()
                return False

            root = roots[0]
            log.debug(f"CLAUDE: Detected OS root: {root}")

            # Mount filesystems
            mps = g.inspect_get_mountpoints(root)

            # Sort mountpoints by length (mount / before /usr, etc.)
            for mountpoint, device in sorted(mps.items(), key=lambda x: len(x[0])):
                try:
                    log.debug(f"CLAUDE: Mounting {device} on {mountpoint}")
                    g.mount_ro(device, mountpoint)
                except RuntimeError as e:
                    log.warning(f"CLAUDE: Could not mount {device}: {e}")

            # Copy file or directory
            host_path_obj = Path(host_path)
            host_path_obj.parent.mkdir(parents=True, exist_ok=True)

            if recursive:
                # Check if it's a directory
                try:
                    is_dir = g.is_dir(guest_path)
                except RuntimeError:
                    log.error(f"CLAUDE: Guest path '{guest_path}' not found")
                    g.close()
                    return False

                if is_dir:
                    log.debug(f"CLAUDE: Copying directory '{guest_path}' recursively")
                    g.copy_out(guest_path, str(host_path_obj.parent))
                else:
                    log.debug(f"CLAUDE: Copying file '{guest_path}'")
                    g.download(guest_path, host_path)
            else:
                log.debug(f"CLAUDE: Copying file '{guest_path}'")
                g.download(guest_path, host_path)

            g.close()
            log.info(f"CLAUDE: Successfully copied '{guest_path}' to '{host_path}'")
            return True

        except Exception as e:
            log.error(f"CLAUDE: Failed to copy from guest: {e}")
            return False

    async def _execute_guest_command_via_agent(
        self,
        command: str,
        background: bool = False,
        stop_event: Optional[threading.Event] = None,
        timeout: int = 300
    ) -> Tuple[int, str, str]:
        """
        Execute command in guest via QEMU Guest Agent.

        Args:
            command: Command to execute
            background: If True, don't wait for command completion
            stop_event: Optional event to signal cancellation
            timeout: Timeout in seconds

        Returns:
            Tuple of (returncode, stdout, stderr)
        """
        if self.get_state() != "running":
            log.error("CLAUDE: VM must be running to execute guest commands")
            return -1, "", "VM not running"

        if not hasattr(self, 'config') or not self.config.guest_agent_socket_path:
            log.error("CLAUDE: Guest agent socket not configured")
            return -1, "", "Guest agent not configured"

        socket_path = self.config.guest_agent_socket_path
        if not os.path.exists(socket_path):
            log.error(f"CLAUDE: Guest agent socket not found at {socket_path}")
            return -1, "", "Guest agent socket not found"

        try:
            # Build command args for guest agent
            cmd_args = self._build_guest_command_args(command, background=background)

            # Execute via QMP using guest-exec
            # Format: {"execute": "guest-exec", "arguments": {"path": "/bin/sh", "arg": ["-c", "command"]}}
            qga_cmd = {
                "execute": "guest-exec",
                "arguments": {
                    "path": cmd_args[0],
                    "arg": cmd_args[1:] if len(cmd_args) > 1 else [],
                    "capture-output": True
                }
            }

            # Send command to guest agent socket
            qga_response = await self._send_qga_command(socket_path, qga_cmd)

            if 'error' in qga_response:
                error_msg = qga_response['error'].get('desc', 'Unknown error')
                log.error(f"CLAUDE: Guest agent error: {error_msg}")
                return -1, "", error_msg

            # Get PID from response
            pid = qga_response.get('return', {}).get('pid')
            if not pid:
                log.error("CLAUDE: No PID returned from guest-exec")
                return -1, "", "No PID returned"

            if background:
                log.debug(f"CLAUDE: Command started in background with PID {pid}")
                return 0, f"Started with PID {pid}", ""

            # Wait for command to complete and get status
            start_time = time.time()
            while time.time() - start_time < timeout:
                if stop_event and stop_event.is_set():
                    log.info("CLAUDE: Stop event detected, abandoning guest command wait")
                    return -1, "", "Cancelled"

                status_cmd = {
                    "execute": "guest-exec-status",
                    "arguments": {"pid": pid}
                }

                status_response = await self._send_qga_command(socket_path, status_cmd)

                if 'error' in status_response:
                    error_msg = status_response['error'].get('desc', 'Unknown error')
                    log.error(f"CLAUDE: Guest agent status error: {error_msg}")
                    return -1, "", error_msg

                status_data = status_response.get('return', {})
                if status_data.get('exited', False):
                    returncode = status_data.get('exitcode', -1)
                    stdout_b64 = status_data.get('out-data', '')
                    stderr_b64 = status_data.get('err-data', '')

                    # Decode base64 output
                    import base64
                    stdout = base64.b64decode(stdout_b64).decode('utf-8', errors='replace') if stdout_b64 else ""
                    stderr = base64.b64decode(stderr_b64).decode('utf-8', errors='replace') if stderr_b64 else ""

                    log.debug(f"CLAUDE: Guest command completed with return code {returncode}")
                    return returncode, stdout, stderr

                # Sleep briefly before checking again
                await asyncio.sleep(0.5)

            log.error("CLAUDE: Timeout waiting for guest command to complete")
            return -1, "", "Timeout"

        except Exception as e:
            log.error(f"CLAUDE: Error executing guest command: {e}")
            return -1, "", str(e)

    async def _send_qga_command(self, socket_path: str, command: dict) -> dict:
        """
        Send command to QEMU Guest Agent socket.

        Args:
            socket_path: Path to guest agent Unix socket
            command: QGA command dictionary

        Returns:
            Response dictionary
        """
        try:
            reader, writer = await asyncio.open_unix_connection(socket_path)

            # Send command as JSON
            cmd_json = json.dumps(command) + '\n'
            writer.write(cmd_json.encode('utf-8'))
            await writer.drain()

            # Read response
            response_line = await reader.readline()
            response = json.loads(response_line.decode('utf-8'))

            writer.close()
            await writer.wait_closed()

            return response

        except Exception as e:
            log.error(f"CLAUDE: Error communicating with guest agent: {e}")
            return {"error": {"desc": str(e)}}
