"""
QEMU VM command execution operations mixin.

Implements AbstractCommandMixin for QEMU-specific command execution using:
- QEMU Guest Agent for runtime commands
- libguestfs for file operations when VM is stopped
"""
import asyncio
import json
import libvirt_qemu
import logging
import os
import subprocess
import threading
import time
from pathlib import Path
from typing import List, Optional, Tuple

from adare.hypervisor.base.mixins.commands import AbstractCommandMixin
from adare.hypervisor.exceptions import HypervisorException
from adare.hypervisor.qemu.libvirt_stderr_redirect import (
    LibvirtStderrRedirect,
    get_experiment_log_file
)

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
            # Add stderr redirection for background commands (Windows)
            if background:
                stderr_redirect = " 2>>C:\\adare\\run\\logs\\adarevmstartup.log"
                command = f"{command}{stderr_redirect}"

            # Windows admin elevation
            if admin:
                if use_cmd:
                    shell = ['powershell.exe', '-Command']
                    command = f"Start-Process -Verb RunAs -FilePath cmd.exe -ArgumentList '/c','{command}' -Wait"
                else:
                    shell = ['powershell.exe', '-Command']
                    command = f"Start-Process -Verb RunAs -FilePath powershell.exe -ArgumentList '-NoProfile','-Command','{command}' -Wait"
            else:
                if use_cmd:
                    shell = ['cmd.exe', '/c']
                else:
                    shell = ['powershell.exe', '-Command']
        else:
            # Add stderr redirection for background commands (Linux)
            if background:
                stderr_redirect = " 2>>/adare/run/logs/adarevmstartup.log"
                command = f"{command}{stderr_redirect}"

            # Use bash instead of sh for proper glob expansion (Ubuntu uses dash as /bin/sh)
            shell = ['/bin/bash', '-c']

            # Apply sudo with environment preservation if admin requested
            if admin:
                # Preserve PATH, DISPLAY, XAUTHORITY for pip and GUI automation
                # Match VirtualBox pattern (virtualbox/mixins/commands.py:481, 488)
                escaped_cmd = command.replace("'", "'\"'\"'")
                command = f'sudo env "PATH=$PATH" "DISPLAY=$DISPLAY" "XAUTHORITY=$XAUTHORITY" bash -c \'{escaped_cmd}\''

        # Return shell command that guest agent will execute
        return shell + [command]

    def _build_guest_environment(self) -> List[str]:
        """
        Build environment variables for QEMU Guest Agent command execution.

        Returns:
            List of environment variable strings in "NAME=VALUE" format
        """
        env_vars = []

        # Set HOME directory based on guest OS
        if 'windows' in self.guest_os.lower():
            # Windows: C:\Users\username
            home_path = f"C:\\Users\\{self.username}"
        else:
            # Linux/Unix: /home/username
            home_path = f"/home/{self.username}"

        env_vars.append(f"HOME={home_path}")

        # Set USER for completeness (Linux/Unix only)
        if 'windows' not in self.guest_os.lower():
            env_vars.append(f"USER={self.username}")

        # Set PATH - use discovered PATH from guest if available, otherwise fallback to hardcoded
        if hasattr(self, '_cached_guest_path') and self._cached_guest_path:
            # Use discovered PATH from guest
            path_value = self._cached_guest_path
            log.debug("CLAUDE: Using discovered guest PATH")
        else:
            # Fallback to hardcoded minimal PATH for compatibility
            if 'windows' in self.guest_os.lower():
                path_value = "C:\\Windows\\System32;C:\\Windows;C:\\Windows\\System32\\WindowsPowerShell\\v1.0"
            else:
                path_value = "/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"
            log.debug("CLAUDE: Using hardcoded fallback PATH (discovery not available)")

        env_vars.append(f"PATH={path_value}")

        # Set X11 environment variables for GUI automation (Linux only)
        # Always set DISPLAY for xhost and GUI automation (matches VirtualBox behavior)
        if 'windows' not in self.guest_os.lower():
            # Always set DISPLAY for Linux guests (required for xhost and GUI automation)
            env_vars.append("DISPLAY=:0")

            # Set XAUTHORITY only if detected (X11 will try default locations otherwise)
            if hasattr(self, '_cached_xauthority') and self._cached_xauthority:
                env_vars.append(f"XAUTHORITY={self._cached_xauthority}")
                log.debug(f"CLAUDE: Using DISPLAY=:0 with XAUTHORITY={self._cached_xauthority}")
            else:
                log.debug("CLAUDE: Using DISPLAY=:0 without XAUTHORITY (X11 will try default locations)")

            # Add ADARE_GUI_MODE environment variable if host-based GUI
            if hasattr(self, 'adare_gui_mode'):
                from adare.backend.experiment.execution.base import GUIExecutionMode
                if self.adare_gui_mode == GUIExecutionMode.HOST:
                    env_vars.append("ADARE_GUI_MODE=host")
                    log.info("CLAUDE: Setting ADARE_GUI_MODE=host - PyAutoGUI will be skipped in guest")

        log.debug(f"CLAUDE: Built guest environment: {env_vars}")
        return env_vars

    async def _discover_guest_path(self) -> Optional[str]:
        """
        Discover actual PATH environment variable from guest OS.

        Executes a command in the guest that sources user profile files
        to get the complete PATH including user-local directories like
        ~/.local/bin, ~/.miniforge3/bin, etc.

        This solves the problem where hardcoded PATH doesn't include
        user-installed tools (poetry, conda, etc.) because QEMU guest
        agent executes commands with /bin/sh -c which doesn't source
        user shell configuration files.

        Returns:
            Discovered PATH string if successful, None if discovery fails.
            Failure is non-fatal - caller should fall back to hardcoded PATH.

        Raises:
            Does not raise - all exceptions are caught and logged as warnings.
        """
        try:
            log.debug("CLAUDE: Attempting to discover guest PATH environment")

            # Build discovery command based on guest OS
            if 'windows' in self.guest_os.lower():
                # Windows: Get combined User + Machine PATH from environment
                discovery_cmd = (
                    "powershell.exe -Command "
                    "\"[Environment]::GetEnvironmentVariable('PATH', 'User') + ';' + "
                    "[Environment]::GetEnvironmentVariable('PATH', 'Machine')\""
                )
            else:
                # Linux: Use login shell to source all profile files
                # -l flag activates login mode which sources /etc/profile, ~/.bash_profile, ~/.profile
                discovery_cmd = "/bin/bash -l -c 'echo $PATH'"

            # Execute discovery command with timeout
            # Using low-level guest-exec to avoid circular dependency
            returncode, stdout, stderr = await self._execute_guest_command_via_agent(
                command=discovery_cmd,
                timeout=10
            )

            stdout = stdout.strip()

            if returncode != 0:
                log.warning(
                    f"CLAUDE: PATH discovery command failed with exit code {returncode}. "
                    f"stderr: {stderr[:100]}"
                )
                return None

            if not stdout:
                log.warning("CLAUDE: PATH discovery returned empty output")
                return None

            # Validate discovered PATH
            if 'windows' in self.guest_os.lower():
                # Windows: PATH should contain C:\Windows\System32
                if 'C:\\Windows\\System32' not in stdout and 'c:\\windows\\system32' not in stdout:
                    log.warning(
                        f"CLAUDE: Discovered Windows PATH appears invalid "
                        f"(missing System32): {stdout[:100]}"
                    )
                    return None
            else:
                # Linux: PATH should contain /bin or /usr/bin
                if '/bin' not in stdout and '/usr/bin' not in stdout:
                    log.warning(
                        f"CLAUDE: Discovered Linux PATH appears invalid "
                        f"(missing /bin or /usr/bin): {stdout[:100]}"
                    )
                    return None

            log.info(f"CLAUDE: Successfully discovered guest PATH: {stdout[:150]}...")
            return stdout

        except asyncio.TimeoutError:
            log.warning("CLAUDE: PATH discovery timed out after 10 seconds")
            return None
        except (OSError, ConnectionError) as e:
            log.warning(f"CLAUDE: PATH discovery failed due to connection error: {e}")
            return None
        except json.JSONDecodeError as e:
            log.warning(f"CLAUDE: PATH discovery failed due to JSON parsing error: {e}")
            return None
        except KeyError as e:
            log.warning(f"CLAUDE: PATH discovery failed due to missing expected key: {e}")
            return None

    async def _detect_xauthority(self) -> Optional[str]:
        """
        Detect XAUTHORITY file location in Linux guest VM.

        Searches multiple standard locations where X11 authorization files
        are typically stored by different display managers (GDM, SDDM, LightDM, etc.).

        Returns:
            Path to XAUTHORITY file if found and readable, None otherwise.
            Failure is non-fatal - caller should handle None gracefully.

        Raises:
            Does not raise - all exceptions are caught and logged as warnings.
        """
        try:
            log.debug("CLAUDE: Attempting to detect XAUTHORITY file in guest")

            detect_cmd = (
                'shopt -s nullglob; '
                'for p in '
                '"/run/user/$(id -u)/gdm/Xauthority" '
                '"/run/user/$(id -u)/X11-display" '
                '"/home/adare/.Xauthority" '
                '/tmp/xauth_* '
                '/tmp/serverauth.* '
                '/run/sddm/xauth_* '
                '/run/user/$(id -u)/xauth_*; do '
                '[ -f "$p" ] && [ -r "$p" ] && { echo "$p"; exit 0; }; '
                'done; '
                'exit 1'
            )

            log.debug(f"CLAUDE: Executing XAUTHORITY detection command: {detect_cmd[:100]}...")

            # Execute detection command via guest agent
            returncode, stdout, stderr = await self._execute_guest_command_via_agent(
                detect_cmd,
                timeout=10
            )

            if returncode == 0 and stdout.strip():
                # Successfully found XAUTHORITY file
                xauthority_path = stdout.strip().splitlines()[0]
                log.info(f"CLAUDE: Successfully detected XAUTHORITY at: {xauthority_path}")
                return xauthority_path
            else:
                log.warning(
                    f"CLAUDE: XAUTHORITY detection failed (exit code {returncode}). "
                    f"stdout: {stdout.strip()!r}, stderr: {stderr.strip()!r}"
                )
                log.debug("CLAUDE: Will set DISPLAY without XAUTHORITY (X11 will try defaults)")
                return None

        except asyncio.TimeoutError:
            log.warning("CLAUDE: XAUTHORITY detection timed out after 10 seconds")
            return None
        except (OSError, ConnectionError) as e:
            log.warning(f"CLAUDE: XAUTHORITY detection failed due to connection error: {e}")
            return None
        except (json.JSONDecodeError, KeyError) as e:
            log.warning(f"CLAUDE: XAUTHORITY detection failed due to parsing error: {e}")
            return None

    async def _discover_and_cache_xauthority(self) -> Optional[str]:
        """
        Discover and cache XAUTHORITY file path for X11 authorization.

        This method discovers the XAUTHORITY file location once after boot
        and caches it for subsequent use in all guest commands.

        Returns:
            Cached XAUTHORITY path if successful, None if discovery fails.
            Failure is non-fatal - X11 functionality may be degraded but
            the VM will continue to function.
        """
        # Return cached value if already discovered
        if hasattr(self, '_cached_xauthority'):
            log.debug(f"CLAUDE: Using cached XAUTHORITY: {self._cached_xauthority}")
            return self._cached_xauthority

        # Perform discovery
        xauthority_path = await self._detect_xauthority()

        # Cache the result (even if None)
        self._cached_xauthority = xauthority_path

        if xauthority_path:
            log.info(f"CLAUDE: Cached XAUTHORITY path: {xauthority_path}")
        else:
            log.warning("CLAUDE: XAUTHORITY detection failed, X11 environment will not be configured")

        return xauthority_path

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
        timeout: int = 300,
        admin: bool = False
    ) -> Tuple[int, str, str]:
        """
        Execute command in guest via QEMU Guest Agent.

        Args:
            command: Command to execute
            background: If True, don't wait for command completion
            stop_event: Optional event to signal cancellation
            timeout: Timeout in seconds
            admin: If True, run with elevated privileges

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
            # Build command args with admin support
            cmd_args = self._build_guest_command_args(
                command,
                background=background,
                admin=admin
            )

            # Build environment variables for guest execution
            env_vars = self._build_guest_environment()

            # Execute via QMP using guest-exec with environment variables
            # Format: {"execute": "guest-exec", "arguments": {"path": "/bin/sh", "arg": ["-c", "command"], "env": ["HOME=/home/user"]}}
            qga_cmd = {
                "execute": "guest-exec",
                "arguments": {
                    "path": cmd_args[0],
                    "arg": cmd_args[1:] if len(cmd_args) > 1 else [],
                    "env": env_vars,
                    "capture-output": True
                }
            }

            # Send command via libvirt API (not direct socket access)
            qga_response = await self._send_qga_command_via_libvirt(qga_cmd)

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

                status_response = await self._send_qga_command_via_libvirt(status_cmd)

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

        except asyncio.TimeoutError as e:
            log.error(f"CLAUDE: Timeout executing guest command '{command}': {e}")
            return -1, "", f"Command execution timeout: {e}"
        except json.JSONDecodeError as e:
            log.error(f"CLAUDE: Invalid JSON response from guest agent for command '{command}': {e}")
            return -1, "", f"Invalid JSON response: {e}"
        except ConnectionError as e:
            log.error(f"CLAUDE: Connection error executing guest command '{command}': {e}")
            return -1, "", f"Connection error: {e}"
        except OSError as e:
            log.error(f"CLAUDE: OS error executing guest command '{command}': {e}")
            return -1, "", f"OS error: {e}"

    async def _send_qga_command_direct(self, socket_path: str, command: dict) -> dict:
        """
        Send command to QEMU Guest Agent socket via direct socket connection.

        WARNING: This method does not work with libvirt-managed VMs because
        libvirt owns the socket connection. Use _send_qga_command_via_libvirt()
        instead for libvirt-managed VMs.

        Implements proper QMP protocol handshake:
        1. Read and discard greeting message (if present)
        2. Send command
        3. Read response

        Args:
            socket_path: Path to guest agent Unix socket
            command: QGA command dictionary

        Returns:
            Response dictionary
        """
        try:
            log.debug(f"CLAUDE: Attempting to connect to guest agent socket: {socket_path}")
            reader, writer = await asyncio.open_unix_connection(socket_path)
            log.debug(f"CLAUDE: Successfully connected to guest agent socket")

            # Step 1: Handle QMP greeting (protocol requirement)
            # The guest agent may send a greeting message on first connection
            try:
                greeting_line = await asyncio.wait_for(reader.readline(), timeout=0.5)
                greeting = json.loads(greeting_line.decode('utf-8'))

                # Check if this is a QMP greeting
                if 'QMP' in greeting:
                    log.debug(f"CLAUDE: Received QGA greeting: {greeting}")
                    # Greeting received and discarded - proceed with command
                else:
                    # Not a greeting - this shouldn't happen, but log it
                    log.warning(f"CLAUDE: Unexpected first message from QGA: {greeting}")
                    # Treat it as the actual response (fallback behavior)
                    writer.close()
                    await writer.wait_closed()
                    return greeting

            except asyncio.TimeoutError:
                # No greeting received - this is fine, some QGA versions don't send it
                log.debug("CLAUDE: No QGA greeting received (timeout), proceeding with command")
            except json.JSONDecodeError as e:
                # Invalid JSON in greeting - log but continue
                log.warning(f"CLAUDE: Failed to parse QGA greeting: {e}")

            # Step 2: Send command as JSON
            cmd_json = json.dumps(command) + '\n'
            log.debug(f"CLAUDE: Sending QGA command: {command.get('execute', 'unknown')}")
            log.debug(f"CLAUDE: Command JSON: {cmd_json.strip()}")
            writer.write(cmd_json.encode('utf-8'))
            log.debug(f"CLAUDE: Command written to buffer, flushing...")
            await writer.drain()
            log.debug(f"CLAUDE: Command flushed successfully")

            # Step 3: Read response with timeout to prevent indefinite blocking
            response_line = await asyncio.wait_for(reader.readline(), timeout=5.0)
            response = json.loads(response_line.decode('utf-8'))

            log.debug(f"CLAUDE: QGA response: {response}")

            writer.close()
            await writer.wait_closed()

            return response

        except asyncio.TimeoutError as e:
            log.error(f"CLAUDE: Timeout communicating with guest agent: {e}")
            return {"error": {"desc": f"Communication timeout: {e}"}}
        except json.JSONDecodeError as e:
            log.error(f"CLAUDE: Failed to parse guest agent response: {e}")
            return {"error": {"desc": f"Invalid JSON response: {e}"}}
        except ConnectionRefusedError as e:
            log.error(f"CLAUDE: Guest agent connection refused: {e}")
            return {"error": {"desc": f"Connection refused: {e}"}}
        except FileNotFoundError as e:
            log.error(f"CLAUDE: Guest agent socket not found: {e}")
            return {"error": {"desc": f"Socket not found: {e}"}}
        except OSError as e:
            # Log detailed error information including errno
            errno_num = getattr(e, 'errno', 'unknown')
            log.error(f"CLAUDE: OS error communicating with guest agent: {e} (errno={errno_num})")
            log.error(f"CLAUDE: Socket path: {socket_path}")
            log.error(f"CLAUDE: Command attempted: {command.get('execute', 'unknown')}")
            return {"error": {"desc": f"OS error: {e}"}}

    async def _send_qga_command_via_libvirt(self, command: dict) -> dict:
        """
        Send command to QEMU Guest Agent via libvirt API.

        This is the correct way to communicate with guest agent when using
        libvirt to manage VMs. Direct socket access fails (errno 22) because
        libvirt owns the socket connection.

        Args:
            command: QGA command dictionary

        Returns:
            Response dictionary
        """
        async def _qga_async():
            import libvirt
            try:
                # Get libvirt domain
                if not self._libvirt_domain:
                    return {"error": {"desc": "Domain not defined"}}

                # Send command via libvirt API
                cmd_json = json.dumps(command)
                log.debug(f"CLAUDE: Sending QGA command via libvirt: {command.get('execute', 'unknown')}")

                # Get experiment log file for stderr capture
                log_file = get_experiment_log_file()

                # Suppress libvirt warnings from console, capture to log
                with LibvirtStderrRedirect(log_file=log_file, suppress_console=True):
                    result = libvirt_qemu.qemuAgentCommand(
                        self._libvirt_domain,
                        cmd_json,
                        5,  # timeout in seconds
                        0   # flags
                    )

                response = json.loads(result)
                log.debug(f"CLAUDE: QGA response: {response}")
                return response

            except libvirt.libvirtError as e:
                log.error(f"CLAUDE: Libvirt error sending QGA command: {e}")
                return {"error": {"desc": f"Libvirt error: {e}"}}
            except json.JSONDecodeError as e:
                log.error(f"CLAUDE: Failed to parse QGA response: {e}")
                return {"error": {"desc": f"Invalid JSON: {e}"}}
            except Exception as e:
                log.error(f"CLAUDE: Unexpected error: {e}")
                return {"error": {"desc": f"Error: {e}"}}

        # Run via manager's async executor
        return await self.manager.run_async(_qga_async)

    async def _check_process_status_via_agent(
        self,
        pid: int,
        timeout: int = 5
    ) -> Tuple[bool, Optional[int], str]:
        """
        Check if a process is still running via QEMU Guest Agent.

        Uses guest-exec-status to determine if a background process is alive.

        Args:
            pid: Process ID returned from guest-exec
            timeout: Maximum time to wait for status check

        Returns:
            Tuple of (is_running, exit_code, error_msg)
            - is_running: True if process still running, False if exited
            - exit_code: Exit code if process exited, None if still running
            - error_msg: Error message if check failed, empty string otherwise

        Example:
            >>> is_running, exit_code, error = await vm._check_process_status_via_agent(1234)
            >>> if not is_running and exit_code != 0:
            >>>     print(f"Process died with exit code {exit_code}")
        """
        try:
            status_cmd = {
                "execute": "guest-exec-status",
                "arguments": {"pid": pid}
            }

            status_response = await self._send_qga_command_via_libvirt(status_cmd)

            if 'error' in status_response:
                error_msg = status_response['error'].get('desc', 'Unknown error')
                log.warning(f"CLAUDE: Failed to check process {pid} status: {error_msg}")
                return False, None, error_msg

            status_data = status_response.get('return', {})
            exited = status_data.get('exited', False)

            if exited:
                exit_code = status_data.get('exitcode', -1)
                log.debug(f"CLAUDE: Process {pid} has exited with code {exit_code}")
                return False, exit_code, ""
            else:
                log.debug(f"CLAUDE: Process {pid} is still running")
                return True, None, ""

        except asyncio.TimeoutError:
            error_msg = "Timeout checking process status"
            log.warning(f"CLAUDE: {error_msg} for PID {pid}")
            return False, None, error_msg
        except (OSError, ConnectionError) as e:
            error_msg = f"Connection error: {e}"
            log.warning(f"CLAUDE: {error_msg} while checking PID {pid}")
            return False, None, error_msg
        except (json.JSONDecodeError, KeyError) as e:
            error_msg = f"Parsing error: {e}"
            log.warning(f"CLAUDE: {error_msg} while checking PID {pid}")
            return False, None, error_msg
