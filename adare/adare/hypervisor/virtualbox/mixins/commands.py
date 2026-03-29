"""
VirtualBox VM command execution operations mixin.

Implements AbstractCommandMixin for VirtualBox-specific command execution.
"""
import asyncio
import base64
import logging
import os
import platform
import queue
import signal
import subprocess
import threading
import time
from pathlib import Path
from typing import Iterator, List, Optional

from adare.hypervisor.base.mixins.commands import AbstractCommandMixin

log = logging.getLogger(__name__)


class CommandExecutionMixin(AbstractCommandMixin):
    """Mixin class providing command execution operations for VirtualBox VMs."""
    
    def _stream_vboxmanage_command(self, args: List[str], stop_event: Optional[threading.Event] = None) -> Iterator[str]:
        """Stream output from a VBoxManage command."""
        command = [self.vboxmanage_exe] + args
        sp_args = {
            "args": command,
            "stdout": subprocess.PIPE,
            "stderr": subprocess.STDOUT,
            "bufsize": 0,
            "preexec_fn": os.setsid if os.name != 'windows' else None
        }

        with subprocess.Popen(**sp_args) as proc:
            try:
                buffer = b""
                last_yield_time = time.time()
                flush_interval = 1

                while True:
                    if stop_event and stop_event.is_set():
                        log.info("Stop event detected; terminating VBoxManage process...")
                        if os.name != 'windows':
                            os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
                        else:
                            proc.terminate()
                        try:
                            proc.wait(timeout=5)
                        except subprocess.TimeoutExpired:
                            log.info("VBoxManage process did not exit in time; killing it.")
                            if os.name != 'windows':
                                os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
                            else:
                                proc.kill()
                            proc.wait()
                        break

                    # Cross-platform non-blocking read approach
                    if os.name != 'windows':
                        # Use select on Unix-like systems
                        import select
                        ready, _, _ = select.select([proc.stdout], [], [], 0.1)  # 100ms timeout

                        if ready:
                            byte = proc.stdout.read(1)
                            now = time.time()
                        else:
                            byte = None
                            now = time.time()
                    else:
                        # Windows doesn't support select on pipes, use polling approach
                        if proc.poll() is None:  # Process still running
                            try:
                                # Try to read with very short timeout simulation
                                byte = proc.stdout.read(1)
                                now = time.time()
                            except:
                                # No data available, small sleep to avoid busy waiting
                                time.sleep(0.01)
                                byte = None
                                now = time.time()
                        else:
                            # Process finished, try to read remaining data
                            try:
                                byte = proc.stdout.read(1)
                                now = time.time()
                            except:
                                byte = None
                                now = time.time()

                    if byte:
                        buffer += byte

                        if byte in (b'\n', b'\r'):
                            line = buffer.decode('utf-8', errors='replace')
                            if '\r' in line:
                                line = line.strip().split('\r')[-1]
                            yield line
                            buffer = b""
                            last_yield_time = now
                    else:
                        if proc.poll() is not None:
                            break
                        # Check for interruption more frequently
                        if stop_event and stop_event.is_set():
                            continue  # Go back to top of loop for clean interruption handling

                    now = time.time()

                    # Flush buffer every 1 seconds even if no newline
                    if buffer and (now - last_yield_time >= flush_interval):
                        line = buffer.decode('utf-8', errors='replace')
                        yield line
                        buffer = b""
                        last_yield_time = now

                if buffer:
                    yield buffer.decode('utf-8', errors='replace')

                proc.wait()
                if proc.returncode != 0:
                    raise subprocess.CalledProcessError(proc.returncode, command)

            except Exception as e:
                if proc.poll() is None:
                    if os.name != 'windows':
                        os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
                    else:
                        proc.terminate()
                    proc.wait()
                raise e

    async def _stream_vboxmanage_command_async(self, args: List[str], stop_event: Optional[threading.Event] = None):
        """Async version of _stream_vboxmanage_command with responsive stop_event handling."""
        command = [self.vboxmanage_exe] + args
        lines = []
        
        # Create process with proper signal handling
        proc = await asyncio.create_subprocess_exec(
            *command,
            stdin=asyncio.subprocess.DEVNULL,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
            preexec_fn=os.setsid if os.name != 'windows' else None
        )

        try:
            buffer = b""
            last_yield_time = time.time()
            flush_interval = 1

            while True:
                if stop_event and stop_event.is_set():
                    log.info("Stop event detected; terminating VBoxManage process...")
                    if os.name != 'windows':
                        os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
                    else:
                        proc.terminate()
                    try:
                        await asyncio.wait_for(proc.wait(), timeout=5)
                    except asyncio.TimeoutError:
                        log.info("VBoxManage process did not exit in time; killing it.")
                        if os.name != 'windows':
                            os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
                        else:
                            proc.kill()
                        await proc.wait()
                    break

                try:
                    # Key improvement: timeout on read for responsive stop_event handling
                    byte = await asyncio.wait_for(proc.stdout.read(1), timeout=0.1)
                except asyncio.TimeoutError:
                    # No output for 0.1 seconds, check stop_event again
                    now = time.time()
                    # Still flush buffer if needed during timeout
                    if buffer and (now - last_yield_time >= flush_interval):
                        line = buffer.decode('utf-8', errors='replace')
                        lines.append(line)
                        buffer = b""
                        last_yield_time = now
                    continue

                now = time.time()

                if byte:
                    buffer += byte

                    if byte in (b'\n', b'\r'):
                        line = buffer.decode('utf-8', errors='replace')
                        if '\r' in line:
                            line = line.strip().split('\r')[-1]
                        lines.append(line)
                        buffer = b""
                        last_yield_time = now
                else:
                    # EOF reached - break immediately regardless of returncode
                    break

                # Flush buffer every 1 seconds even if no newline
                if buffer and (now - last_yield_time >= flush_interval):
                    line = buffer.decode('utf-8', errors='replace')
                    lines.append(line)
                    buffer = b""
                    last_yield_time = now

            # Process any remaining buffer
            if buffer:
                lines.append(buffer.decode('utf-8', errors='replace'))

            await proc.wait()
            
            # Return lines regardless of return code - let caller handle the error
            # This ensures we don't lose captured output when commands fail
            return lines, proc.returncode

        except Exception as e:
            if proc.returncode is None:
                if os.name != 'windows':
                    os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
                else:
                    proc.terminate()
                await proc.wait()
            raise e

    def _execute_streaming_command(
        self,
        command_args: List[str],
        log_file: Optional[Path] = None,
        stop_event: Optional[threading.Event] = None,
        silent: bool = False,
        ctx_manager=None,
        operation_name: str = "VBoxManage operation",
        timeout: int = 300  # 5 minute default timeout
    ) -> int:
        """Generic method to execute VBoxManage commands with streaming output."""
        import time
        start_time = time.time()

        log.info(f"Executing {operation_name} for VM '{self.vm_name}' with streaming output (timeout: {timeout}s)")
        log.info(f"VBoxManage command: {' '.join([self.vboxmanage_exe] + command_args)}")

        line_queue = queue.Queue()
        return_value = 0

        # Update context manager to running status
        if ctx_manager:
            from adarelib.constants import StatusEnum
            ctx_manager.set_status(StatusEnum.RUNNING)

        def stream_worker():
            nonlocal return_value
            try:
                for line in self._stream_vboxmanage_command(command_args, stop_event=stop_event):
                    line_queue.put(line)
            except subprocess.CalledProcessError as e:
                return_value = e.returncode
                log.warning(f"{operation_name} command failed with return code {e.returncode}")
            except Exception as e:
                log.error(f"Error during {operation_name}: {e}")
                return_value = 1
            finally:
                line_queue.put(None)  # Signal end of stream

        stream_thread = threading.Thread(target=stream_worker, daemon=True)
        stream_thread.start()

        # Process streamed output with timeout handling
        try:
            with open(log_file, 'w', encoding='utf-8') if log_file else open(os.devnull, 'w') as f:
                while True:
                    try:
                        line = line_queue.get(timeout=1)
                    except queue.Empty:
                        # Check for timeout
                        elapsed = time.time() - start_time
                        if elapsed > timeout:
                            log.error(f"{operation_name} timed out after {timeout}s for VM '{self.vm_name}'")
                            if ctx_manager:
                                from adarelib.constants import StatusEnum
                                ctx_manager.set_status(StatusEnum.FAILED)
                            return_value = 1
                            break

                        # Check for interruption
                        if stop_event and stop_event.is_set():
                            log.info(f"Stop event detected during {operation_name}")
                            if ctx_manager:
                                from adarelib.constants import StatusEnum
                                ctx_manager.set_status(StatusEnum.INTERRUPTED)
                            break
                        continue

                    if line is None:
                        break

                    if not silent:
                        log.info(f"[{self.vm_name}] {line.rstrip()}")

                    if log_file:
                        f.write(line)
                        f.flush()

        except Exception as e:
            log.error(f"Error processing output during {operation_name}: {e}")
            return_value = 1

        # Wait for stream thread to complete
        stream_thread.join()
        
        return return_value

    async def _execute_streaming_command_async(
        self, 
        command_args: List[str], 
        log_file: Optional[Path] = None,
        stop_event: Optional[threading.Event] = None,
        silent: bool = False,
        ctx_manager=None,
        operation_name: str = "VBoxManage operation"
    ) -> tuple[int, str, str]:
        """Async version of _execute_streaming_command with responsive stop_event handling."""
        log.info(f"Executing {operation_name} for VM '{self.vm_name}' with async streaming output")
        return_value = 0
        captured_output = []
        
        # Update context manager to running status
        if ctx_manager:
            from adarelib.constants import StatusEnum
            ctx_manager.set_status(StatusEnum.RUNNING)

        try:
            lines, return_code = await self._stream_vboxmanage_command_async(command_args, stop_event=stop_event)
            return_value = return_code
            
            # Process output
            try:
                with open(log_file, 'w', encoding='utf-8') if log_file else open(os.devnull, 'w') as f:
                    for line in lines:
                        if stop_event and stop_event.is_set():
                            log.info(f"Stop event detected during {operation_name}")
                            if ctx_manager:
                                ctx_manager.set_status(StatusEnum.INTERRUPTED)
                            break

                        captured_output.append(line)
                        if not silent and line.strip():
                            log.info(f"[{self.vm_name}] {line.rstrip()}")
                        
                        if log_file:
                            f.write(line + '\n')
                            f.flush()

            except Exception as e:
                log.error(f"Error processing output during {operation_name}: {e}")
                return_value = 1

        except Exception as e:
            log.error(f"Error during async {operation_name}: {e}")
            return_value = 1

        stdout = ''.join(captured_output)
        return return_value, stdout, ""

    def _detect_xauthority(self) -> Optional[str]:
        """Detect XAUTHORITY file location in Linux guest VM."""
        detect_cmd = r'''
            shopt -s nullglob
            for p in "$XAUTHORITY" \
                    "/run/user/$(id -u)/gdm/Xauthority" \
                    "/run/user/$(id -u)/X11-display" \
                    "$HOME/.Xauthority" \
                    "/home/adare/.Xauthority" \
                    /tmp/xauth_* \
                    /tmp/serverauth.* \
                    /run/sddm/xauth_* \
                    /run/user/$(id -u)/xauth_*; do
                [ -f "$p" ] && [ -r "$p" ] && { echo "$p"; exit 0; }
            done
            exit 1
        '''.strip()

        args = [
            "guestcontrol", self.vm_name, "run",
            "--exe", "/bin/bash",
            "--wait-stdout", "--wait-stderr",
            "--timeout", "10000",
            "--", "-c", detect_cmd
        ]

        if hasattr(self, "_guest_session_id") and self._guest_session_id:
            args.insert(2, "--session-id")
            args.insert(3, self._guest_session_id)
        else:
            args.insert(2, "--username")
            args.insert(3, self.username)
            args.insert(4, "--password")
            args.insert(5, self.password)

        from adare.hypervisor.virtualbox.utils import run_subprocess
        result = run_subprocess([self.vboxmanage_exe] + args, check=False)

        if result.returncode == 0 and result.stdout.strip():
            path = result.stdout.strip().splitlines()[0]
            log.info(f"Detected XAUTHORITY at: {path}")
            return path

        log.error(
            f"Failed to detect XAUTHORITY (exit code {result.returncode}). "
            f"stdout: {result.stdout.strip()!r}, stderr: {result.stderr.strip()!r}"
        )
        return None   # better than returning a hardcoded, possibly wrong path

    async def _discover_guest_path(self) -> Optional[str]:
        """
        Stub for guest PATH discovery.

        VirtualBox guestcontrol executes commands with the user's full
        environment, so explicit PATH discovery is not needed.
        For Windows, the command builder falls back to 'python' which
        works if Python is in the system PATH.
        """
        return None

    def _build_guest_command_args(
        self,
        command: str,
        background: bool = False,
        cwd: Optional[str] = None,
        admin: bool = False,
        # VirtualBox-specific (implemented)
        win_noprofile: bool = True,
        use_cmd: bool = False,
        run_as_user: bool = False,
        # QEMU-specific (not supported)
        binary_is_filepath: bool = False,
        redirect_stderr: str = "",
        redirect_stdout: str = "",
        hidden_window: bool = True,
    ) -> List[str]:
        """
        Build VBoxManage guestcontrol command arguments for running guest commands.

        Args:
            command: The command to run
            background: Whether to run in background
            cwd: Current working directory
            admin: Run with admin privileges
            win_noprofile: PowerShell -NoProfile flag (VirtualBox-specific)
            use_cmd: Wrap in cmd /c (VirtualBox-specific)
            run_as_user: Included for API compatibility. VirtualBox execution via guestcontrol
                         is always performed as the authenticated user (Session 0 escape is handled naturally).
            binary_is_filepath: QEMU-specific, not supported in VirtualBox
            redirect_stderr: QEMU-specific, not supported in VirtualBox (uses hardcoded path)
            redirect_stdout: QEMU-specific, not supported in VirtualBox
            hidden_window: QEMU-specific, silently ignored (Windows always uses Hidden)

        Raises:
            NotImplementedError: If QEMU-specific parameters are used
        """
        # Guard for unsupported QEMU params
        if binary_is_filepath:
            raise NotImplementedError("binary_is_filepath not supported in VirtualBox")
        if redirect_stderr:
            raise NotImplementedError("redirect_stderr not supported in VirtualBox (uses hardcoded path)")
        if redirect_stdout:
            raise NotImplementedError("redirect_stdout not supported in VirtualBox")
        # hidden_window has no effect - silently ignore (Windows always uses Hidden)

        cmd_to_run = command

        # Handle working directory change
        if cwd:
            if 'windows' in self.guest_os.lower():
                cmd_to_run = f'cd {cwd}; {command}'
            else:
                cmd_to_run = f'cd {cwd} && {command}'

        if 'windows' in self.guest_os.lower():
            command_exe = r"C:\Windows\SysWOW64\WindowsPowerShell\v1.0\powershell.exe"
            noprofile_arg = "-NoProfile" if win_noprofile else ""

            # If use_cmd is True, wrap the command in cmd /c from within PowerShell
            if use_cmd:
                cmd_to_run = f"cmd /c '{cmd_to_run}'"

            if background:
                if use_cmd:
                    # For background commands with cmd, use cmd.exe directly in Start-Process
                    # Redirect stderr to startup log for debugging
                    noprofile_inner = "'-NoProfile'," if win_noprofile else ""
                    # Remove the cmd /c wrapper since we'll use cmd.exe directly
                    original_cmd = cmd_to_run.replace("cmd /c '", "").rstrip("'")
                    # Add stderr redirection to the command
                    original_cmd_with_redirect = f"{original_cmd} 2>>C:\\adare\\run\\logs\\adarevmstartup.log"
                    verb_arg = "-Verb RunAs " if admin else ""
                    ps_cmd = (
                        f"$p=Start-Process -WindowStyle Hidden -PassThru {verb_arg}-FilePath cmd.exe "
                        f"-ArgumentList @('/c','{original_cmd_with_redirect}');"
                        f"$p.Id"
                    )
                else:
                    # For PowerShell commands, redirect stderr to startup log
                    noprofile_inner = "'-NoProfile'," if win_noprofile else ""
                    verb_arg = "-Verb RunAs " if admin else ""
                    # Wrap command to redirect stderr
                    cmd_with_redirect = f"{cmd_to_run} 2>>C:\\adare\\run\\logs\\adarevmstartup.log"
                    ps_cmd = (
                        f"$p=Start-Process -WindowStyle Hidden -PassThru {verb_arg}-FilePath powershell.exe "
                        f"-ArgumentList @({noprofile_inner}'-ExecutionPolicy','Bypass','-Command','{cmd_with_redirect}');"
                        f"$p.Id"
                    )
                command_bytes = ps_cmd.encode('utf-16le')
                encoded_command = base64.b64encode(command_bytes).decode('ascii')
                command_args = [arg for arg in [noprofile_arg, "-ExecutionPolicy Bypass", "-EncodedCommand", encoded_command] if arg]
            else:
                # Foreground command - handle admin elevation
                if admin:
                    # Escape single quotes for PowerShell ArgumentList
                    escaped_cmd = cmd_to_run.replace("'", "''")
                    # Use Start-Process with -Verb RunAs and -Wait for synchronous admin execution
                    cmd_to_run = f"Start-Process -Verb RunAs -FilePath powershell.exe -ArgumentList @('-NoProfile','-ExecutionPolicy','Bypass','-Command','{escaped_cmd}') -Wait"

                command_bytes = cmd_to_run.encode('utf-16le')
                encoded_command = base64.b64encode(command_bytes).decode('ascii')
                command_args = [arg for arg in [noprofile_arg, "-ExecutionPolicy Bypass", "-EncodedCommand", encoded_command] if arg]
        else:
            # Linux/Unix guest
            command_exe = "/bin/bash"

            if background:
                # Use nohup with bash -c to handle shell builtins and complex commands
                # This ensures the background process survives when the parent shell exits
                # Log stdout and stderr to startup log file for debugging and background the nohup process
                # Escape single quotes for bash -c
                escaped_cmd = cmd_to_run.replace("'", "'\"'\"'")
                # Apply sudo before nohup if admin privileges requested
                sudo_prefix = 'sudo env "PATH=$PATH" "DISPLAY=$DISPLAY" "XAUTHORITY=$XAUTHORITY" ' if admin else ""
                linux_command = f"nohup {sudo_prefix}bash -c '{escaped_cmd}' >>/adare/run/logs/adarevmstartup.log 2>&1 & echo $!"
            else:
                # Apply sudo if admin privileges requested (foreground commands)
                if admin:
                    # Escape single quotes in the command for bash -c
                    escaped_cmd = cmd_to_run.replace("'", "'\"'\"'")
                    linux_command = f'sudo env "PATH=$PATH" "DISPLAY=$DISPLAY" "XAUTHORITY=$XAUTHORITY" bash -c \'{escaped_cmd}\''
                else:
                    # Wrap in bash -c for glob expansion and shell features
                    escaped_cmd = cmd_to_run.replace("'", "'\"'\"'")
                    linux_command = f'bash -c \'{escaped_cmd}\''

        # Build the full VBoxManage guestcontrol command
        if 'windows' in self.guest_os.lower():
            args = [
                "guestcontrol", self.vm_name, "run",
                "--exe", command_exe,
                "--", command_exe
            ]
            # Add PowerShell arguments as separate list items
            args.extend(command_args)
        else:
            # Detect XAUTHORITY for Linux guests
            xauthority_path = self._detect_xauthority()
            args = [
                "guestcontrol", self.vm_name, "run",
                "--exe", command_exe,
                "--putenv", "DISPLAY=:0",
                "--putenv", f"XAUTHORITY={xauthority_path}",
                "--", "-c", linux_command
            ]

        # Add authentication
        if hasattr(self, "_guest_session_id") and self._guest_session_id:
            args.insert(2, "--session-id")
            args.insert(3, self._guest_session_id)
        else:
            args.insert(2, "--username")
            args.insert(3, self.username)
            args.insert(4, "--password")
            args.insert(5, self.password)
        
        return args

    async def copy_from_guest(self, guest_path: str, host_path: str, recursive: bool = True) -> bool:
        """
        Copy files/directories from guest to host using VBoxManage guestcontrol copyfrom.
        
        Args:
            guest_path: Path on the guest VM to copy from
            host_path: Path on the host to copy to
            recursive: Whether to copy directories recursively
            
        Returns:
            True if copy was successful
        """
        args = [
            "guestcontrol", self.vm_name, "copyfrom",
            "--username", self.username,
            "--password", self.password
        ]
        
        if recursive:
            args.append("--recursive")
            
        args.extend([guest_path, host_path])
        
        try:
            lines, return_code = await self._stream_vboxmanage_command_async(args)
            if return_code == 0:
                log.info(f"Successfully copied {guest_path} from guest to {host_path}")
                return True
            else:
                error_output = '\n'.join(lines) if lines else "No error output"
                log.error(f"Failed to copy {guest_path} from guest (return code {return_code}): {error_output}")
                return False
        except Exception as e:
            log.error(f"Exception during copy from guest {guest_path}: {e}")
            return False