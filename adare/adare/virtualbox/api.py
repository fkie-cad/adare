import base64
import subprocess
import platform
import logging
import time
import threading
import queue
import os
import signal
from typing import Optional, List, Iterator
import asyncio
from pathlib import Path
import contextlib

from adare.exceptions import LoggedErrorException
from adarelib.constants import StatusEnum

log = logging.getLogger(__name__)


class VMImportException(LoggedErrorException):
    def __init__(self, message: str):
        super().__init__(log, message)

class VMAlreadyRunningException(LoggedErrorException):
    def __init__(self, message: str):
        super().__init__(log, message)

class VMNotFoundException(LoggedErrorException):
    def __init__(self, message: str):
        super().__init__(log, message)


def run_subprocess(cmd, *, check=True, capture_output=True, text=True, log_prefix=""):
    try:
        result = subprocess.run(
            cmd,
            check=check,
            stdout=subprocess.PIPE if capture_output else None,
            stderr=subprocess.PIPE if capture_output else None,
            text=text
        )
        return result
    except subprocess.CalledProcessError as e:
        log.error(f"{log_prefix}Subprocess failed: {e}")
        raise
    except FileNotFoundError as e:
        log.error(f"{log_prefix}Executable not found: {e}")
        raise
    except Exception as e:
        log.error(f"{log_prefix}Unexpected error: {e}")
        raise

def read_file_hash(path, hash_algo="sha256"):
    import hashlib
    try:
        with open(path, "rb") as f:
            data = f.read()
            if hash_algo == "sha256":
                return hashlib.sha256(data).hexdigest()
            raise ValueError("Unsupported hash algorithm")
    except FileNotFoundError as e:
        log.error(f"File not found: {e}")
        raise
    except Exception as e:
        log.error(f"Error reading file hash: {e}")
        raise

class VirtualBoxManager:
    def __init__(self):
        self._cmd_queue = queue.Queue()
        self._worker = threading.Thread(target=self._worker_loop, daemon=True)
        self._worker.start()
        log.debug("VirtualBoxManager initialized and worker thread started.")

    def _worker_loop(self):
        log.debug("VirtualBoxManager worker loop started.")
        while True:
            func, args, kwargs, result_queue = self._cmd_queue.get()
            try:
                log.debug(f"Executing function {func.__name__} with args={args} kwargs={kwargs}")
                result = func(*args, **kwargs)
                result_queue.put((result, None))
            except Exception as e:
                log.error(f"Exception in worker loop for function {func.__name__}: {e}")
                result_queue.put((None, e))

    def run(self, func, *args, **kwargs):
        log.debug(f"Queueing function {func.__name__} for execution.")
        result_queue = queue.Queue()
        self._cmd_queue.put((func, args, kwargs, result_queue))
        result, error = result_queue.get()
        if error:
            log.error(f"Error running function {func.__name__}: {error}")
            raise error
        log.debug(f"Function {func.__name__} executed successfully.")
        return result

    async def run_async(self, func, *args, **kwargs):
        """Run an async function directly without the worker thread."""
        log.debug(f"Executing async function {func.__name__} with args={args} kwargs={kwargs}")
        try:
            result = await func(*args, **kwargs)
            log.debug(f"Async function {func.__name__} executed successfully.")
            return result
        except Exception as e:
            log.error(f"Error running async function {func.__name__}: {e}")
            raise e


class CommandResult:
    def __init__(self, returncode: int, stdout: str, stderr: str, duration: int):
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr
        self.duration = duration


class VirtualBoxVM:
    def __init__(
        self,
        vm_name: str,
        guest_os: str,
        manager: 'VirtualBoxManager',
        username: str = 'vagrant',
        password: str = 'vagrant',
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
        async def _create_async():
            log.info(f"Creating VM '{self.vm_name}' with {self.cpus} CPUs, {self.ram}MB RAM, network: {self.network}")
            commands = [
                ["createvm", "--name", self.vm_name, "--register"],
                ["modifyvm", self.vm_name, "--ostype", self.guest_os],
                ["modifyvm", self.vm_name, "--cpus", str(self.cpus)],
                ["modifyvm", self.vm_name, "--memory", str(self.ram)],
                ["modifyvm", self.vm_name, "--nic1", self.network]
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


    async def wait_until_fully_booted(self, timeout: int = 300, ctx_manager = None, stop_event: Optional[threading.Event] = None):
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
                                log.debug(f"VM readiness check timed out for VM '{self.vm_name}'")
                                proc.kill()
                                await proc.wait()

                        except Exception as e:
                            log.debug(f"Command failed while checking VM boot status: {e}")

                    await asyncio.sleep(0.2)  # Check stop_event often, even if not querying VM yet

                log.error(f"VM '{self.vm_name}' did not become responsive within {timeout} seconds")
                return False

        return await self.manager.run_async(_wait_async)


    async def remove(self, ctx_manager=None, stop_event=None, log_file: Optional[Path] = None, silent: bool = False):
        async def _remove_async():
            state = self._get_state(raise_on_missing=False)
            if state == "not existing":
                log.info(f"VM '{self.vm_name}' does not exist, nothing to remove.")
                return 0
            log.info(f"Attempting to unregister and delete VM '{self.vm_name}'")
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
                log.info(f"VM '{self.vm_name}' unregistered and deleted.")
            return return_value
        
        try:
            return await self.manager.run_async(_remove_async)
        except Exception as e:
            log.error(f"Error removing VM '{self.vm_name}': {e}")
            return 1
    
    async def destroy(self, ctx_manager=None, stop_event=None, log_file: Optional[Path] = None, silent: bool = False):
        """Alias for remove() method for consistency with other VM operations."""
        return await self.remove(ctx_manager=ctx_manager, stop_event=stop_event, log_file=log_file, silent=silent)


    def _stream_vboxmanage_command(self, args: List[str], stop_event: Optional[threading.Event] = None) -> Iterator[str]:
        import time

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

                    byte = proc.stdout.read(1)
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
                        time.sleep(0.01)

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

    async def _stream_vboxmanage_command_async(self, args: List[str], stop_event: Optional[threading.Event] = None) -> List[str]:
        """Async version of _stream_vboxmanage_command with responsive stop_event handling."""
        import time

        command = [self.vboxmanage_exe] + args
        lines = []
        
        # Create process with proper signal handling
        proc = await asyncio.create_subprocess_exec(
            *command,
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
                    # EOF reached
                    if proc.returncode is not None:
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
        operation_name: str = "VBoxManage operation"
    ) -> int:
        """
        Generic method to execute VBoxManage commands with streaming output.
        Handles context manager status updates, logging, and error handling.
        """
        log.info(f"Executing {operation_name} for VM '{self.vm_name}' with streaming output")
        line_queue = queue.Queue()
        return_value = 0
        
        # Update context manager to running status
        if ctx_manager:
            from adarelib.constants import StatusEnum
            ctx_manager.set_status(StatusEnum.RUNNING)
        
        def stream_worker():
            nonlocal return_value
            try:
                for line in self._stream_vboxmanage_command(command_args, stop_event):
                    line_queue.put(line)
            except subprocess.CalledProcessError as e:
                return_value = e.returncode
                line_queue.put(e)
            except OSError as e:
                return_value = 1
                line_queue.put(e)
            finally:
                line_queue.put(None)  # Sentinel
        
        worker = threading.Thread(target=stream_worker)
        worker.start()
        
        log_file_handle = log_file.open('w') if log_file else None
        
        try:
            while True:
                try:
                    item = line_queue.get(timeout=0.1)
                except queue.Empty:
                    if not worker.is_alive() and line_queue.empty():
                        break
                    continue
                
                if item is None:
                    break
                
                if isinstance(item, Exception):
                    if isinstance(item, subprocess.CalledProcessError):
                        return_value = item.returncode
                    else:
                        return_value = 1
                    log.error(f"Error during {operation_name}: {item}")
                    # Update context manager to failed status
                    if ctx_manager:
                        from adarelib.constants import StatusEnum
                        ctx_manager.set_status(StatusEnum.FAILED)
                    break
                
                if not silent:
                    log.debug(item.strip())
                
                if log_file_handle:
                    log_file_handle.write(item)
                    log_file_handle.flush()
            
            worker.join()
            
            # Update context manager to success status if no errors
            if return_value == 0 and ctx_manager:
                from adarelib.constants import StatusEnum
                ctx_manager.set_status(StatusEnum.SUCCESS)
            
        finally:
            if log_file_handle:
                log_file_handle.close()
        
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
        """
        Async version of _execute_streaming_command with responsive stop_event handling.
        Returns tuple of (return_code, stdout, stderr).
        """
        log.info(f"Executing {operation_name} for VM '{self.vm_name}' with async streaming output")
        return_value = 0
        captured_output = []
        
        # Update context manager to running status
        if ctx_manager:
            from adarelib.constants import StatusEnum
            ctx_manager.set_status(StatusEnum.RUNNING)
        
        log_file_handle = log_file.open('w') if log_file else None
        
        try:
            lines, return_value = await self._stream_vboxmanage_command_async(command_args, stop_event)
            
            for line in lines:
                captured_output.append(line)
                if not silent:
                    log.debug(line.strip())
                
                if log_file_handle:
                    log_file_handle.write(line)
                    log_file_handle.flush()
            
            # Update context manager status based on return code
            if ctx_manager:
                from adarelib.constants import StatusEnum
                if return_value == 0:
                    ctx_manager.set_status(StatusEnum.SUCCESS)
                else:
                    ctx_manager.set_status(StatusEnum.FAILED)
                
        except subprocess.CalledProcessError as e:
            return_value = e.returncode
            log.error(f"Error during {operation_name}: {e}")
            # Update context manager to failed status
            if ctx_manager:
                from adarelib.constants import StatusEnum
                ctx_manager.set_status(StatusEnum.FAILED)
        except OSError as e:
            return_value = 1
            log.error(f"OS error during {operation_name}: {e}")
            # Update context manager to failed status
            if ctx_manager:
                from adarelib.constants import StatusEnum
                ctx_manager.set_status(StatusEnum.FAILED)
        finally:
            if log_file_handle:
                log_file_handle.close()
        
        # For VBoxManage, stdout and stderr are combined, so we put all output in stdout
        stdout_content = '\n'.join(captured_output)
        stderr_content = ""
        
        return return_value, stdout_content, stderr_content

    async def run_command(
        self,
        command: str,
        background: bool = False,
        silent: bool = False,
        stop_event: Optional[threading.Event] = None,
        cwd: Optional[str] = None,
        ctx_manager=None,
        log_file: Optional[Path] = None,
        win_noprofile: bool = True,
        use_cmd: bool = False
    ) -> 'CommandResult':
        """
        Run a command in the guest with streaming output.
        If background is True, track the PID for later cleanup.
        """
        async def _run_command_async():
            import time
            start_time = time.time()
            
            try:
                args = self._build_guest_command_args(command, background, cwd, win_noprofile, use_cmd)
                log.debug(f"Running command in VM '{self.vm_name}': {' '.join(args)}")
                
                # Execute command and capture output
                return_code, stdout_content, stderr_content = await self._execute_streaming_command_async(
                    args,
                    log_file=log_file,
                    stop_event=stop_event,
                    silent=silent,
                    ctx_manager=ctx_manager,
                    operation_name=f"guest command: {command[:50]}..."
                )
                
                # If background, extract and store the PID from output
                if background and return_code == 0:
                    pid = None
                    lines = stdout_content.splitlines()
                    if lines:
                        pid_candidate = lines[-1].strip()
                        if pid_candidate.isdigit():
                            pid = pid_candidate
                    
                    if pid:
                        self._background_pids.append(pid)
                        if not silent:
                            log.debug(f"Tracked background PID: {pid}")
                
                duration = time.time() - start_time
                
                # Create CommandResult with actual stdout/stderr
                result = CommandResult(
                    return_code if return_code is not None else -1,
                    stdout_content,
                    stderr_content,
                    duration
                )
                
                # Log successful command completion
                if return_code == 0:
                    log.info(f"Command completed successfully in VM '{self.vm_name}': {command[:50]}...")
                else:
                    log.error(f"Command failed in VM '{self.vm_name}' with exit code {return_code}: {command[:50]}...")
                
                # Raise ExperimentCommandError if command failed
                if return_code != 0:
                    from adare.backend.experiment.exceptions import ExperimentCommandError
                    raise ExperimentCommandError(log, command, return_code, stdout_content, stderr_content)
                
                return result
                
            except subprocess.CalledProcessError as e:
                duration = time.time() - start_time
                return CommandResult(e.returncode, "", str(e), duration)
            except asyncio.TimeoutError:
                duration = time.time() - start_time
                return CommandResult(-1, "", "Command timed out", duration)
            except OSError as e:
                duration = time.time() - start_time
                return CommandResult(-1, "", f"OS error: {e}", duration)
        
        return await self.manager.run_async(_run_command_async)

    def cleanup_background_processes(self):
        """Kill all tracked background processes."""
        if not self._background_pids:
            return
        if 'windows' in self.guest_os.lower():
            for pid in self._background_pids:
                self.run_command(f"Stop-Process -Id {pid} -Force", silent=True)
        else:
            for pid in self._background_pids:
                self.run_command(f"kill -9 {pid}", silent=True)
        self._background_pids.clear()

    async def run_command_async(
        self,
        command: str,
        background: bool = False,
        silent: bool = False,
        timeout: Optional[int] = None,
        win_noprofile: bool = True,
    ) -> CommandResult:
        import asyncio, time
        start_time = time.time()
        try:
            if 'windows' in self.guest_os.lower():
                command_exe = r"C:\Windows\SysWOW64\WindowsPowerShell\v1.0\powershell.exe"
                log.debug(f"Preparing Windows command for VM '{self.vm_name}': {command}")
                command_bytes = command.encode('utf-16le')
                encoded_command = base64.b64encode(command_bytes).decode('ascii')
                if win_noprofile:
                    command_args = "-NoProfile "
                else:
                    command_args = ""
                if background:
                    command_args += f"-ExecutionPolicy Bypass -Command \"Start-Process -WindowStyle Hidden -PassThru -FilePath powershell.exe -ArgumentList '-NoProfile', '-ExecutionPolicy', 'Bypass', '-EncodedCommand', '{encoded_command}'\""
                else:
                    command_args += f"-ExecutionPolicy Bypass -EncodedCommand {encoded_command}"
            else:
                command_exe = "/bin/bash"
                background_addon = " &" if background else ""
                command_args = f"-c '{command}{background_addon}'"
                log.debug(f"Preparing Linux command for VM '{self.vm_name}': {command}")

            vbox_command = [
                self.vboxmanage_exe, "guestcontrol", self.vm_name, "run",
                "--exe", command_exe,
                "--", command_exe, command_args
            ]

            # if hasattr(self, "_guest_session_id") and self._guest_session_id:
            #     vbox_command.insert(3, "--session-id")
            #     vbox_command.insert(4, self._guest_session_id)
            # else:
            vbox_command.insert(3, "--username")
            vbox_command.insert(4, self.username)
            vbox_command.insert(5, "--password")
            vbox_command.insert(6, self.password)

            if not silent:
                log.debug(f"Running async command in VM '{self.vm_name}': {' '.join(vbox_command)}")
            proc = await asyncio.create_subprocess_exec(
                *vbox_command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            try:
                stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)
            except asyncio.TimeoutError:
                proc.kill()
                await proc.wait()
                log.error(f"Async command in VM '{self.vm_name}' timed out after {timeout} seconds")
                return CommandResult(None, "", "Timeout", time.time() - start_time)
            duration = time.time() - start_time
            log.debug(f"Async command in VM '{self.vm_name}' finished with return code {proc.returncode} in {duration:.2f}s")
            return CommandResult(proc.returncode, stdout.decode(), stderr.decode(), duration)
        except asyncio.TimeoutError:
            log.error(f"Async command in VM '{self.vm_name}' timed out")
            return CommandResult(-1, "", "Command timed out", time.time() - start_time)
        except subprocess.CalledProcessError as e:
            log.error(f"Async command in VM '{self.vm_name}' failed: {e}")
            return CommandResult(e.returncode, "", str(e), time.time() - start_time)
        except OSError as e:
            log.error(f"OS error running async command in VM '{self.vm_name}': {e}")
            return CommandResult(-1, "", str(e), time.time() - start_time)

    def is_fully_booted(self, silent: bool = False) -> bool:
        command = "echo Fully booted"
        result = self.run_command(command, silent=silent)
        if result.returncode == 0:
            log.info(f"VM '{self.vm_name}' is fully booted.")
        else:
            log.debug(f"VM '{self.vm_name}' is not fully booted.")
        return result.returncode == 0

    async def is_fully_booted_async(self, silent: bool = False) -> bool:
        command = "echo Fully booted"
        result = await self.run_command_async(command, silent=silent)
        if result.returncode == 0:
            log.info(f"VM '{self.vm_name}' is fully booted (async).")
        else:
            log.debug(f"VM '{self.vm_name}' is not fully booted (async).")
        return result.returncode == 0


    async def get_state_async(self) -> str:
        """Async version of get_state, runs in a thread to avoid blocking the event loop."""
        return await asyncio.to_thread(self.get_state)

    async def wait_until_fully_booted_async(self, timeout: int = 360) -> bool:
        log.info(f"Waiting for VM '{self.vm_name}' to boot (async)...")
        state = await self.get_state_async()
        if state != "running":
            log.error(f"VM '{self.vm_name}' is not running (state: {state}). Cannot wait for boot (async).")
            return False
        time_slept = 0
        while not await self.is_fully_booted_async(silent=True):
            if time_slept > timeout:
                log.error(f"VM '{self.vm_name}' did not boot within {timeout} seconds (async)")
                return False
            if time_slept % 30 == 0 and time_slept != 0:
                log.info(f"Still waiting for VM '{self.vm_name}' to boot... {time_slept} seconds elapsed (async)")
            await asyncio.sleep(2)
            time_slept += 2
        log.info(f"VM '{self.vm_name}' is fully booted after {time_slept} seconds (async)")
        return True

    def _get_state(self, raise_on_missing: bool = True) -> str:
        try:
            result = subprocess.run(
                [self.vboxmanage_exe, "showvminfo", self.vm_name, "--machinereadable"],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=True,
                text=True
            )
            for line in result.stdout.splitlines():
                if line.startswith("VMState="):
                    state = line.split("=", 1)[1].strip().strip('"')
                    log.info(f"VM '{self.vm_name}' state: {state}")
                    return state
            log.error(f"VMState not found in VBoxManage output for VM '{self.vm_name}'.")
            return "unknown"
        except subprocess.CalledProcessError as e:
            if "could not find a registered machine named" in e.stderr.lower():
                if raise_on_missing:
                    log.error(f"VM '{self.vm_name}' not found.")
                    raise VMNotFoundException(f"VM '{self.vm_name}' not found.")
                else:
                    log.info(f"VM '{self.vm_name}' not found, returning 'not existing' state.")
                    return "not existing"
            log.error(f"Error getting state for VM '{self.vm_name}': {e}")
            raise

    def get_state(self) -> str:
        """Thread-safe: gets VM state via manager."""
        return self.manager.run(self._get_state)

    async def start(self, ctx_manager=None, raise_if_running: bool = False, stop_event=None, log_file: Optional[Path] = None, silent: bool = False):
        """
        Start the VM. If raise_if_running is True and the VM is already running, raises VMAlreadyRunningException.
        """
        async def _start_async():
            state = self._get_state()  # Call the private method directly
            if state == "running":
                log.info(f"VM '{self.vm_name}' is already running.")
                if raise_if_running:
                    raise VMAlreadyRunningException(f"VM '{self.vm_name}' is already running.")
                return 0
            
            log.info(f"Starting VM '{self.vm_name}' in headless mode.")
            args = ["startvm", self.vm_name, "--type", "headless"]
            return_value, _, _ = await self._execute_streaming_command_async(
                args,
                log_file=log_file,
                stop_event=stop_event,
                silent=silent,
                ctx_manager=ctx_manager,
                operation_name="VM start"
            )
            
            if return_value == 0:
                log.info(f"VM '{self.vm_name}' started.")
            return return_value
        
        return await self.manager.run_async(_start_async)

    async def stop(self, ctx_manager=None, log_file: Optional[Path] = None, silent: bool = False):
        """
        Gracefully stop the VM using VBoxManage controlvm poweroff.
        Note: VM stop operations are not interruptible to prevent inconsistent VM states.
        """
        async def _stop_async():
            state = self._get_state(raise_on_missing=False)
            if state == "not existing":
                log.info(f"VM '{self.vm_name}' does not exist, nothing to stop")
                return 0
            if state != "running":
                log.info(f"VM '{self.vm_name}' is not running. Current state: {state}")
                return 0

            log.info(f"Stopping VM '{self.vm_name}'...")
            args = ["controlvm", self.vm_name, "poweroff"]
            return_value, _, _ = await self._execute_streaming_command_async(
                args,
                log_file=log_file,
                stop_event=None,  # Don't allow interruption of VM stop operations
                silent=silent,
                ctx_manager=ctx_manager,
                operation_name="VM stop"
            )
            
            if return_value == 0:
                log.info(f"VM '{self.vm_name}' stopped.")
            return return_value
        
        return await self.manager.run_async(_stop_async)

    def _build_guest_command_args(self, command: str, background: bool = False, cwd: Optional[str] = None, win_noprofile: bool = True, use_cmd: bool = False) -> List[str]:
        """
        Build VBoxManage guestcontrol command arguments for running guest commands.
        """
        cmd_to_run = command
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
                noprofile_inner = "'-NoProfile'," if win_noprofile else ""
                ps_cmd = (
                    f"$p=Start-Process -WindowStyle Hidden -PassThru -FilePath powershell.exe "
                    f"-ArgumentList {noprofile_inner}'-ExecutionPolicy','Bypass','-Command','{cmd_to_run}';"
                    f"$p.Id"
                )
                command_bytes = ps_cmd.encode('utf-16le')
                encoded_command = base64.b64encode(command_bytes).decode('ascii')
                command_args = f"{noprofile_arg} -ExecutionPolicy Bypass -EncodedCommand {encoded_command}".strip()
            else:
                command_bytes = cmd_to_run.encode('utf-16le')
                encoded_command = base64.b64encode(command_bytes).decode('ascii')
                command_args = f"{noprofile_arg} -ExecutionPolicy Bypass -EncodedCommand {encoded_command}".strip()
        else:
            command_exe = "/bin/bash"
            if background:
                command_args = f"-c '{cmd_to_run} & echo $!'"
            else:
                command_args = f"-c '{cmd_to_run}'"
        
        args = [
            "guestcontrol", self.vm_name, "run",
            "--exe", command_exe,
            "--", command_exe, command_args
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

    async def __create_from_ova_by_extract(self, file_path: Path):
        """
        Extracts the OVA file and imports the OVF.
        This is a workaround for VirtualBox not supporting OVA import directly.
        Extraction should behave like 'tar -xvf', supporting both Linux and Windows.
        """
        import tarfile
        log.info(f"Extracting OVA file '{file_path}'")
        # Open as tar, auto-detect compression (tarfile.open with mode 'r' does this)
        with tarfile.open(file_path, "r") as tar:
            tar.extractall(path=file_path.parent)
        log.info(f"OVA file '{file_path}' extracted to '{file_path.parent}'")
        ovf_file = next((file for file in file_path.parent.iterdir() if file.suffix.lower() == '.ovf'), None)
        if not ovf_file:
            log.error(f"No OVF file found after extracting '{file_path}'")
            raise VMImportException(f"No OVF file found in extracted OVA '{file_path}'")

        await self.create_from_ovf_or_ova(ovf_file, try_extract=False)
        log.info(f"OVA file '{file_path}' extracted and imported successfully.")
    

    async def create_from_ovf_or_ova(self, file_path: Path, try_extract: bool = True, ctx_manager=None, stop_event=None, log_file: Optional[Path] = None, silent: bool = False):
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
                    return_value, _, _ = await self._execute_streaming_command_async(
                        args,
                        log_file=log_file,
                        stop_event=stop_event,
                        silent=silent,
                        ctx_manager=None,
                        operation_name="VM import"
                    )
                    
                    if return_value == 0:
                        log.info(f"VM '{self.vm_name}' imported from '{file_path}'.")
                        return return_value
                    elif stop_event and stop_event.is_set():
                        log.info(f"VM import for '{self.vm_name}' was interrupted.")
                        if ctx_manager:
                            ctx_manager.set_status(StatusEnum.INTERRUPTED)
                        return 1
                    else:
                        raise subprocess.CalledProcessError(return_value, args)
                        
                except subprocess.CalledProcessError as e:
                    if try_extract and file_path.suffix.lower() == '.ova':
                        log.warning(f"Failed to import OVA directly, trying extraction: {e}")
                        try:
                            return await self.__create_from_ova_by_extract(file_path)
                        except subprocess.CalledProcessError as e:
                            log.error(f"Failed to import VM '{self.vm_name}' from extracted OVF: {e}")
                            raise VMImportException(f"Failed to import VM '{self.vm_name}' from '{file_path}': {e}")
                    else:
                        raise VMImportException(f"Failed to import VM '{self.vm_name}' from '{file_path}': {e}")
                except FileNotFoundError as e:
                    raise VMImportException(f"VBoxManage executable not found: {e}")
        
        return await self.manager.run_async(_import_async)

    async def add_shared_folder(self, name: str, host_path: Path, automount: bool = True, readonly: bool = False, mountpoint: Optional[Path] = None, ctx_manager=None, stop_event=None, log_file: Optional[Path] = None, silent: bool = False):
        """
        Add a shared folder to the VM (VirtualBox configuration only).
        For Windows guests with custom mountpoint, this only adds the shared folder - use mount_shared_folder() after VM startup.
        For other cases, uses VirtualBox's built-in shared folder mechanism with automount.
        
        Args:
            name: Name of the shared folder
            host_path: Path on the host machine
            automount: Whether to automount (ignored for Windows with custom mountpoint)
            readonly: Whether the share is read-only
            mountpoint: Custom mount point (Windows: use mount_shared_folder() after startup)
            ctx_manager: Context manager for status updates
            stop_event: Event to signal stop
            log_file: Log file for output
            silent: Whether to suppress logging
        """
        async def _add_shared_folder_async():
            # For Windows guests with custom mountpoint, use command execution for arbitrary paths
            if 'windows' in self.guest_os.lower() and mountpoint:
                # First add the shared folder using standard VirtualBox method (no automount)
                args = [
                    "sharedfolder", "add", self.vm_name,
                    "--name", name,
                    "--hostpath", host_path.as_posix(),
                ]
                if readonly:
                    args.append("--readonly")
                
                try:
                    log.info(f"Adding shared folder '{name}' (host: {host_path}) to VM '{self.vm_name}'.")
                    return_value, _, _ = await self._execute_streaming_command_async(
                        args,
                        log_file=log_file,
                        stop_event=stop_event,
                        silent=silent,
                        ctx_manager=ctx_manager,
                        operation_name="shared folder addition"
                    )
                    
                    if return_value != 0:
                        log.error(f"Failed to add shared folder '{name}' to VM '{self.vm_name}': return code {return_value}")
                        return return_value
                    
                    # For Windows with custom mountpoint, only add the shared folder here
                    # Mounting will be done after VM startup using mount_shared_folder()
                    log.info(f"Shared folder '{name}' added to VM '{self.vm_name}' (Windows - mount after startup).")
                    return return_value
                        
                except subprocess.CalledProcessError as e:
                    log.error(f"VBoxManage error adding shared folder '{name}' to VM '{self.vm_name}': {e}")
                    return e.returncode
                except OSError as e:
                    log.error(f"OS error adding shared folder '{name}' to VM '{self.vm_name}': {e}")
                    return 1
            else:
                # Use standard VirtualBox shared folder mechanism
                args = [
                    "sharedfolder", "add", self.vm_name,
                    "--name", name,
                    "--hostpath", host_path
                ]
                if automount:
                    args.append("--automount")
                if readonly:
                    args.append("--readonly")
                if mountpoint:
                    args += ["--auto-mount-point", mountpoint]
                
                try:
                    log.info(f"Adding shared folder '{name}' (host: {host_path}) to VM '{self.vm_name}'.")
                    return_value, _, _ = await self._execute_streaming_command_async(
                        args,
                        log_file=log_file,
                        stop_event=stop_event,
                        silent=silent,
                        ctx_manager=ctx_manager,
                        operation_name="shared folder addition"
                    )
                    
                    if return_value == 0:
                        log.info(f"Shared folder '{name}' added to VM '{self.vm_name}'.")
                    else:
                        log.error(f"Failed to add shared folder '{name}' to VM '{self.vm_name}': return code {return_value}")
                    
                    return return_value
                except subprocess.CalledProcessError as e:
                    log.error(f"VBoxManage error adding shared folder '{name}' to VM '{self.vm_name}': {e}")
                    return e.returncode
                except OSError as e:
                    log.error(f"OS error adding shared folder '{name}' to VM '{self.vm_name}': {e}")
                    return 1
        
        return await self.manager.run_async(_add_shared_folder_async)

    async def mount_shared_folder(self, name: str, mountpoint: Path, ctx_manager=None, stop_event=None, log_file: Optional[Path] = None, silent: bool = False):
        """
        Mount a shared folder to a custom path (VM must be running).
        For Windows guests, mounts to drive letters (Z:, X:, Y:, etc.) using persistent net use command,
        or creates symbolic links to UNC paths for directory mounts.
        For Linux guests, uses the mount command.
        
        Args:
            name: Name of the shared folder (must be already added with add_shared_folder)
            mountpoint: Path where to mount in the guest (for Windows: drive letters like Z:, X:, etc. or full paths)
            ctx_manager: Context manager for status updates
            stop_event: Event to signal stop
            log_file: Log file for output
            silent: Whether to suppress logging
        """
        async def _mount_shared_folder_async():
            if 'windows' in self.guest_os.lower():
                from pathlib import PureWindowsPath
                # Windows: Determine if mounting to a drive letter or directory path
                mountpoint_str = str(mountpoint)
                unc_path = f"\\\\vboxsvr\\{name}"
                
                # Check if it's a drive letter (like Z:, X:, Y:, etc.)
                if len(mountpoint_str) == 2 and mountpoint_str[1] == ':' and mountpoint_str[0].isalpha():
                    # Mount to drive letter using net use command (assuming drive is available)
                    drive_letter = mountpoint_str.upper()
                    log.info(f"Mounting shared folder '{name}' to drive letter '{drive_letter}' in Windows VM '{self.vm_name}'")
                    
                    # Mount the network share to the drive letter with persistence
                    mount_cmd = f"net use {drive_letter} \"{unc_path}\" /persistent:yes"
                    mount_result = await self.run_command(
                        mount_cmd,
                        silent=silent,
                        stop_event=stop_event,
                        ctx_manager=ctx_manager,
                        log_file=log_file,
                        use_cmd=True
                    )
                    
                    if mount_result.returncode == 0:
                        log.info(f"Successfully mounted shared folder '{name}' to drive '{drive_letter}' in VM '{self.vm_name}'")
                        return 0
                    else:
                        log.error(f"Failed to mount shared folder '{name}' to drive '{drive_letter}' in VM '{self.vm_name}': return code {mount_result.returncode}")
                        return mount_result.returncode
                
                else:
                    # Mount to directory path using symbolic link (existing behavior)
                    # Convert to Windows path format
                    win_mountpoint = mountpoint_str.replace('/', '\\')
                    parent_dir = PureWindowsPath(win_mountpoint).parent.as_posix()
                    
                    # Create parent directory if it doesn't exist
                    mkdir_cmd = f"New-Item -ItemType Directory -Path '{parent_dir}' -Force -ErrorAction SilentlyContinue"
                    await self.run_command(
                        mkdir_cmd,
                        silent=True,
                        stop_event=stop_event,
                        ctx_manager=ctx_manager,
                        log_file=log_file
                    )
                    
                    # Remove existing link if it exists
                    remove_cmd = f"if (Test-Path '{win_mountpoint}') {{ Remove-Item '{win_mountpoint}' -Force -Recurse -ErrorAction SilentlyContinue }}"
                    await self.run_command(
                        remove_cmd,
                        silent=True,
                        stop_event=stop_event,
                        ctx_manager=ctx_manager,
                        log_file=log_file
                    )
                    
                    # Create symbolic link using mklink /D (run directly without cmd /c)
                    mount_cmd = f'mklink /D "{win_mountpoint}" "{unc_path}"'
                    cmd = f"cmd /c '{mount_cmd}'"
                    
                    log.info(f"Creating directory symbolic link from '{win_mountpoint}' to '{unc_path}' in Windows VM '{self.vm_name}'")
                    mount_result = await self.run_command(
                        cmd,
                        silent=silent,
                        stop_event=stop_event,
                        ctx_manager=ctx_manager,
                        log_file=log_file
                    )
                    
                    if mount_result.returncode == 0:
                        log.info(f"Successfully mounted shared folder '{name}' to '{mountpoint}' in VM '{self.vm_name}'")
                        return 0
                    else:
                        log.error(f"Failed to mount shared folder '{name}' to '{mountpoint}' in VM '{self.vm_name}': return code {mount_result.returncode}")
                        return mount_result.returncode
            else:
                log.info(f"For Linux guests, the shared folder '{name}' should already be mounted automatically since automount was enabled.")
        
        return await self.manager.run_async(_mount_shared_folder_async)

    def queue_command(self, command: str, description: str = None):
        """
        Add a command to the queue for batch execution.
        
        Args:
            command: The command to queue
            description: Optional description for logging
        """
        self._command_queue.append({
            'command': command,
            'description': description or command[:50] + "..." if len(command) > 50 else command
        })
        log.debug(f"Queued command: {description or command[:50]}")

    def queue_mount_shared_folder(self, name: str, mountpoint: Path):
        """
        Queue a shared folder mount command.
        
        Args:
            name: Name of the shared folder
            mountpoint: Path where to mount in the guest (for Windows: drive letters like Z:, X:, etc. or full paths)
        """
        if 'windows' in self.guest_os.lower():
            from pathlib import PureWindowsPath
            unc_path = f"\\\\vboxsvr\\{name}"
            mountpoint_str = str(mountpoint)
            
            # Check if it's a drive letter (like Z:, X:, Y:, etc.)
            if len(mountpoint_str) == 2 and mountpoint_str[1] == ':' and mountpoint_str[0].isalpha():
                # Queue net use command for drive letter mounting
                drive_letter = mountpoint_str.upper()
                mount_cmd = f'net use {drive_letter} "{unc_path}"'

                self.queue_command(
                    mount_cmd,
                    f"Mount shared folder {name} to drive {drive_letter}"
                )
            else:
                # Queue directory path mounting using symbolic link (existing behavior)
                win_mountpoint = mountpoint_str.replace('/', '\\')
                parent_dir = PureWindowsPath(win_mountpoint).parent.as_posix()
                
                # Queue directory creation
                self.queue_command(
                    f'New-Item -ItemType Directory -Path "{parent_dir}" -Force -ErrorAction SilentlyContinue',
                    f"Create parent directory for {name}"
                )
                
                # Queue existing link removal
                self.queue_command(
                    f'if (Test-Path "{win_mountpoint}") {{ Remove-Item "{win_mountpoint}" -Force -Recurse -ErrorAction SilentlyContinue }}',
                    f"Remove existing link for {name}"
                )
                
                # Queue mklink command using same pattern as individual mount
                mount_cmd = f'mklink /D "{win_mountpoint}" "{unc_path}"'
                self.queue_command(
                    f"cmd /c '{mount_cmd}'",
                    f"Create symlink for {name}"
                )
        else:
            # Linux
            unix_mountpoint = str(mountpoint)
            
            # Queue directory creation
            self.queue_command(
                f'sudo mkdir -p {unix_mountpoint}',
                f"Create mount point for {name}"
            )
            
            # Queue mount command
            self.queue_command(
                f'sudo mount -t vboxsf -o uid=1000,gid=1000 {name} {unix_mountpoint}',
                f"Mount shared folder {name}"
            )

    async def execute_queued_commands(self, ctx_manager=None, stop_event=None, log_file: Optional[Path] = None, silent: bool = False, win_noprofile: bool = False):
        """
        Execute all queued commands in a single batch.
        
        Args:
            ctx_manager: Context manager for status updates
            stop_event: Event to signal stop
            log_file: Log file for output
            silent: Whether to suppress logging
        """
        if not self._command_queue:
            log.info("No commands in queue to execute")
            return 0
        
        async def _execute_queued_commands_async():
            # Build the batch command
            if 'windows' in self.guest_os.lower():
                # Windows: Join with semicolons
                commands = [item['command'] for item in self._command_queue]
                batch_cmd = '; '.join(commands)
            else:
                # Linux: Join with &&
                commands = [item['command'] for item in self._command_queue]
                batch_cmd = ' && '.join(commands)
            
            log.info(f"Executing {len(self._command_queue)} queued commands in batch for VM '{self.vm_name}'")
            
            # Execute the batch command
            result = await self.run_command(
                batch_cmd,
                silent=silent,
                stop_event=stop_event,
                ctx_manager=ctx_manager,
                log_file=log_file,
                win_noprofile=win_noprofile
            )
            
            # Clear the queue after execution
            self._command_queue.clear()
            
            if result.returncode == 0:
                log.info(f"Successfully executed all queued commands in VM '{self.vm_name}'")
            else:
                log.error(f"Failed to execute queued commands in VM '{self.vm_name}': return code {result.returncode}")
            
            return result.returncode
        
        return await self.manager.run_async(_execute_queued_commands_async)

    def clear_command_queue(self):
        """Clear all queued commands without executing them."""
        count = len(self._command_queue)
        self._command_queue.clear()
        log.info(f"Cleared {count} queued commands")

    async def mount_multiple_shared_folders(self, folders: dict, ctx_manager=None, stop_event=None, log_file: Optional[Path] = None, silent: bool = False):
        """
        Mount multiple shared folders using the command queue for efficiency.
        
        Args:
            folders: Dict with structure {'name': Path} where Path is the guest mountpoint
            ctx_manager: Context manager for status updates
            stop_event: Event to signal stop
            log_file: Log file for output
            silent: Whether to suppress logging
        """
        # Clear any existing commands
        self.clear_command_queue()
        
        # Queue all mount commands
        for name, mountpoint in folders.items():
            self.queue_mount_shared_folder(name, mountpoint)
        
        # Execute all queued commands
        return await self.execute_queued_commands(ctx_manager, stop_event, log_file, silent, win_noprofile=True)

    async def remove_shared_folder(self, name: str, mountpoint: Optional[str] = None, ctx_manager=None, stop_event=None, log_file: Optional[Path] = None, silent: bool = False):
        """
        Remove a shared folder from the VM.
        For Windows guests with custom mountpoint, unmounts the network drive first.
        Then removes the VirtualBox shared folder.
        
        Args:
            name: Name of the shared folder
            mountpoint: Custom mount point (if it was mounted to a custom path)
            ctx_manager: Context manager for status updates
            stop_event: Event to signal stop
            log_file: Log file for output
            silent: Whether to suppress logging
        """
        async def _remove_shared_folder_async():
            # For Windows guests with custom mountpoint, remove the junction first
            if 'windows' in self.guest_os.lower() and mountpoint:
                try:
                    # Convert forward slashes to backslashes for Windows paths
                    win_mountpoint = mountpoint.replace('/', '\\')
                    # Remove the junction/symbolic link
                    remove_cmd = f"if (Test-Path '{win_mountpoint}') {{ Remove-Item '{win_mountpoint}' -Force -Recurse -ErrorAction SilentlyContinue }}"
                    log.info(f"Removing junction '{win_mountpoint}' for shared folder '{name}' in Windows VM '{self.vm_name}'")
                    unmount_result = await self.run_command(
                        remove_cmd,
                        silent=silent,
                        stop_event=stop_event,
                        ctx_manager=ctx_manager,
                        log_file=log_file
                    )
                    
                    if unmount_result.returncode != 0:
                        log.warning(f"Failed to remove junction '{win_mountpoint}' for shared folder '{name}' in VM '{self.vm_name}': return code {unmount_result.returncode}")
                        
                except Exception as e:
                    log.error(f"Error removing junction '{win_mountpoint}' for shared folder '{name}' in VM '{self.vm_name}': {e}")
            
            # Remove the VirtualBox shared folder
            try:
                args = ["sharedfolder", "remove", self.vm_name, "--name", name]
                log.info(f"Removing shared folder '{name}' from VM '{self.vm_name}'")
                return_value, _, _ = await self._execute_streaming_command_async(
                    args,
                    log_file=log_file,
                    stop_event=stop_event,
                    silent=silent,
                    ctx_manager=ctx_manager,
                    operation_name="shared folder removal"
                )
                
                if return_value == 0:
                    log.info(f"Successfully removed shared folder '{name}' from VM '{self.vm_name}'")
                else:
                    log.error(f"Failed to remove shared folder '{name}' from VM '{self.vm_name}': return code {return_value}")
                
                return return_value
                
            except Exception as e:
                log.error(f"Error removing shared folder '{name}' from VM '{self.vm_name}': {e}")
                return 1
        
        return await self.manager.run_async(_remove_shared_folder_async)

    def create_snapshot(self, snapshot_name: str, description: str = "", ctx_manager=None, stop_event=None, log_file: Optional[Path] = None, silent: bool = False):
        def _create_snapshot():
            args = [
                "snapshot", self.vm_name, "take", snapshot_name
            ]
            if description:
                args += ["--description", description]
            
            try:
                log.info(f"Creating snapshot '{snapshot_name}' for VM '{self.vm_name}'.")
                return_value = self._execute_streaming_command(
                    args,
                    log_file=log_file,
                    stop_event=stop_event,
                    silent=silent,
                    ctx_manager=ctx_manager,
                    operation_name="snapshot creation"
                )
                
                if return_value == 0:
                    log.info(f"Snapshot '{snapshot_name}' created for VM '{self.vm_name}'.")
                else:
                    log.error(f"Failed to create snapshot '{snapshot_name}' for VM '{self.vm_name}': return code {return_value}")
                
                return return_value
            except Exception as e:
                log.error(f"Failed to create snapshot '{snapshot_name}' for VM '{self.vm_name}': {e}")
                return 1
        
        return self.manager.run(_create_snapshot)

    def vm_exists(self) -> bool:
        def _vm_exists():
            try:
                log.debug(f"Checking if VM '{self.vm_name}' exists.")
                result = subprocess.run(
                    [self.vboxmanage_exe, "list", "vms"],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    check=True,
                    text=True
                )
                vms = result.stdout
                exists = f'"{self.vm_name}"' in vms
                log.info(f"VM '{self.vm_name}' exists: {exists}")
                return exists
            except Exception as e:
                log.error(f"Error checking if VM '{self.vm_name}' exists: {e}")
                return False
        return self.manager.run(_vm_exists)

    def ovf_is_identical(self, ovf_path: str) -> bool:
        def _ovf_is_identical():
            try:
                log.debug(f"Checking OVF hash for VM '{self.vm_name}' against '{ovf_path}'")
                ovf_hash = read_file_hash(ovf_path)
                result = run_subprocess(
                    [self.vboxmanage_exe, "getextradata", self.vm_name, "ovf_hash"],
                    log_prefix=f"[{self.vm_name}] "
                )
                if "No value set!" in result.stdout:
                    log.info(f"No OVF hash stored for VM '{self.vm_name}'.")
                    return False
                stored_hash = result.stdout.strip().split(":", 1)[-1].strip()
                identical = ovf_hash == stored_hash
                log.info(f"OVF hash identical for VM '{self.vm_name}': {identical}")
                return identical
            except Exception as e:
                log.error(f"Error checking OVF identity for VM '{self.vm_name}': {e}")
                return False
        return self.manager.run(_ovf_is_identical)

    def store_ovf_hash(self, ovf_path: str):
        def _store_ovf_hash():
            try:
                log.debug(f"Storing OVF hash for VM '{self.vm_name}' from '{ovf_path}'")
                ovf_hash = read_file_hash(ovf_path)
                run_subprocess(
                    [self.vboxmanage_exe, "setextradata", self.vm_name, "ovf_hash", ovf_hash],
                    log_prefix=f"[{self.vm_name}] "
                )
                log.info(f"Stored OVF hash for VM '{self.vm_name}'.")
            except Exception as e:
                log.error(f"Error storing OVF hash for VM '{self.vm_name}': {e}")
        self.manager.run(_store_ovf_hash)

    def snapshot_exists(self, snapshot_name: str) -> bool:
        def _snapshot_exists():
            try:
                log.debug(f"Checking if snapshot '{snapshot_name}' exists for VM '{self.vm_name}'.")
                result = run_subprocess(
                    [self.vboxmanage_exe, "snapshot", self.vm_name, "list", "--machinereadable"],
                    log_prefix=f"[{self.vm_name}] "
                )
                for line in result.stdout.splitlines():
                    if line.startswith("SnapshotName="):
                        name = line.split("=", 1)[1].strip().strip('"')
                        if name == snapshot_name:
                            log.info(f"Snapshot '{snapshot_name}' exists for VM '{self.vm_name}'.")
                            return True
                log.info(f"Snapshot '{snapshot_name}' does not exist for VM '{self.vm_name}'.")
                return False
            except Exception as e:
                log.error(f"Error checking if snapshot '{snapshot_name}' exists for VM '{self.vm_name}': {e}")
                return False
        return self.manager.run(_snapshot_exists)

    def restore_snapshot(self, snapshot_name: str, ctx_manager=None, stop_event=None, log_file: Optional[Path] = None, silent: bool = False) -> bool:
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
                    operation_name="snapshot restoration"
                )
                
                if return_value == 0:
                    log.info(f"VM '{self.vm_name}' restored to snapshot '{snapshot_name}'.")
                    return True
                else:
                    log.error(f"Failed to restore snapshot '{snapshot_name}' for VM '{self.vm_name}': return code {return_value}")
                    return False
            except Exception as e:
                log.error(f"Failed to restore snapshot '{snapshot_name}' for VM '{self.vm_name}': {e}")
                return False
        
        return self.manager.run(_restore_snapshot)

    @classmethod
    def get_vm_by_name(cls, vm_name: str, manager: Optional[VirtualBoxManager] = None):
        vboxmanage_exe = 'VBoxManage.exe' if platform.system().lower() == 'windows' else 'VBoxManage'
        def _get_vm_info():
            try:
                log.debug(f"Retrieving info for VM '{vm_name}'.")
                result = subprocess.run(
                    [vboxmanage_exe, "showvminfo", vm_name, "--machinereadable"],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    check=True,
                    text=True
                )
                info = {}
                for line in result.stdout.splitlines():
                    if "=" in line:
                        k, v = line.split("=", 1)
                        info[k.strip()] = v.strip().strip('"')
                guest_os = info.get("ostype", "")
                cpus = int(info.get("cpus", "1"))
                ram = int(info.get("memory", "1024"))
                network = info.get("nic1", "nat")
                log.info(f"VM '{vm_name}' info retrieved successfully.")
                return cls(
                    vm_name=vm_name,
                    guest_os=guest_os,
                    manager=manager if manager else VirtualBoxManager(),
                    cpus=cpus,
                    ram=ram,
                    network=network
                )
            except Exception as e:
                log.error(f"Error retrieving VM '{vm_name}': {e}")
                return None
        if manager:
            return manager.run(_get_vm_info)
        else:
            return _get_vm_info()

    # def open_guest_session(self):
    #     def _open_guest_session():
    #         cmd = [
    #             self.vboxmanage_exe, "guestcontrol", self.vm_name, "start",
    #             "--username", self.username,
    #             "--password", self.password
    #         ]
    #         try:
    #             log.info(f"Opening guest session for VM '{self.vm_name}'.")
    #             result = subprocess.run(cmd, stdout=subprocess.PIPE, text=True, check=True)
    #             for line in result.stdout.splitlines():
    #                 if "Session ID:" in line:
    #                     session_id = line.split(":", 1)[1].strip()
    #                     self._guest_session_id = session_id
    #                     log.info(f"Guest session opened for VM '{self.vm_name}', session ID: {session_id}")
    #                     return session_id
    #             log.error(f"Session ID not found in VBoxManage output for VM '{self.vm_name}'.")
    #             return None
    #         except Exception as e:
    #             log.error(f"Failed to open guest session for VM '{self.vm_name}': {e}")
    #             return None
    #     return self.manager.run(_open_guest_session)

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
    ):
        """
        Add a port forwarding rule to the VM's NAT adapter.
        
        Args:
            name: Name of the port forwarding rule
            protocol: Protocol (tcp or udp)
            host_ip: Host IP address to bind to (use "" for all interfaces)
            host_port: Host port number
            guest_ip: Guest IP address (usually "" for any)
            guest_port: Guest port number
            ctx_manager: Context manager for status updates
            stop_event: Event to signal stop
            log_file: Log file for output
            silent: Whether to suppress logging
        """
        async def _add_port_forward_async():
            args = [
                "modifyvm", self.vm_name,
                "--natpf1", f"{name},{protocol},{host_ip},{host_port},{guest_ip},{guest_port}"
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

    async def ensure_initial_snapshot(
        self,
        ovf_path: str,
        snapshot_name: str,
        snapshot_description: str = ""
    ):
        """
        Ensure the VM exists and has an initial snapshot.
        If the VM does not exist, import from OVF and create the snapshot.
        If the snapshot exists, restore it. Otherwise, just start the VM as is.
        """
        if not self.vm_exists():
            log.info(f"VM '{self.vm_name}' does not exist. Importing from OVF and creating initial snapshot.")
            await self.create_from_ovf_or_ova(file_path=ovf_path)
            self.create_snapshot(snapshot_name=snapshot_name, description=snapshot_description)
            log.info(f"VM '{self.vm_name}' created and initial snapshot '{snapshot_name}' taken.")
        else:
            if self.snapshot_exists(snapshot_name):
                log.info(f"Restoring VM '{self.vm_name}' to initial snapshot '{snapshot_name}'.")
                self.restore_snapshot(snapshot_name)
                log.info(f"Restored VM '{self.vm_name}' to snapshot '{snapshot_name}'.")
            else:
                log.warning(f"Initial snapshot '{snapshot_name}' not found for VM '{self.vm_name}'. Starting VM as is.")
