"""
QEMU VM command execution operations mixin.

Implements AbstractCommandMixin for QEMU-specific command execution using:
- QEMU Guest Agent for runtime commands
- libguestfs for file operations when VM is stopped
"""
import asyncio
import json

try:
    import libvirt_qemu
except ImportError:
    libvirt_qemu = None
import base64
import logging
import os
import subprocess
import threading
import time
from pathlib import Path

from adare.hypervisor.base.mixins.commands import AbstractCommandMixin
from adare.hypervisor.exceptions import HypervisorException
from adare.hypervisor.qemu.libvirt_stderr_redirect import LibvirtStderrRedirect, get_experiment_log_file

log = logging.getLogger(__name__)


class CommandExecutionMixin(AbstractCommandMixin):
    """Mixin class providing command execution operations for QEMU VMs."""

    async def _execute_streaming_command_async(
        self,
        args: list[str],
        log_file: Path | None = None,
        stop_event: threading.Event | None = None,
        silent: bool = False,
        ctx_manager=None,
        operation_name: str = "command execution"
    ) -> tuple[int, str, str]:
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
            log.info(f"Executing {operation_name}: {' '.join(args)}")

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
                    log.info(f"Stop event detected during {operation_name}")
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
                except TimeoutError:
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
                log.debug(f"{operation_name} completed with return code {proc.returncode}")

            return proc.returncode, stdout, stderr

        except (OSError, subprocess.SubprocessError) as e:
            log.error(f"Error executing {operation_name}: {e}")
            raise HypervisorException(f"Command execution failed: {e}") from e

    def _execute_streaming_command(
        self,
        args: list[str],
        log_file: Path | None = None,
        stop_event: threading.Event | None = None,
        silent: bool = False,
        ctx_manager=None,
        operation_name: str = "command execution",
        timeout: int | None = None
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
            log.info(f"Executing {operation_name}: {' '.join(args)}")

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
                    log.info(f"Stop event detected during {operation_name}")
                    proc.terminate()
                    proc.wait(timeout=5)
                    break

                line = proc.stdout.readline()
                if not line:
                    break

                line_str = line.decode('utf-8', errors='replace').rstrip()
                output_lines.append(line_str)

                if not silent:
                    log.debug(f"{line_str}")

                if log_file:
                    with open(log_file, 'a') as f:
                        f.write(line_str + '\n')

            proc.wait()

            if not silent:
                log.debug(f"{operation_name} completed with return code {proc.returncode}")

            return proc.returncode

        except (OSError, subprocess.SubprocessError) as e:
            log.error(f"Error executing {operation_name}: {e}")
            raise HypervisorException(f"Command execution failed: {e}") from e


    def _build_guest_command_args(
        self,
        command: str,
        background: bool = False,
        cwd: str | None = None,
        admin: bool = False,
        run_as_user: bool = False,
        # VirtualBox-specific (limited support)
        win_noprofile: bool = True,
        use_cmd: bool = False,
        # QEMU-specific (implemented)
        binary_is_filepath: bool = False,
        redirect_stderr: str = "",
        redirect_stdout: str = "",
        hidden_window: bool = True,
        inject_user_path: bool = False,
    ) -> list[str]:
        """
        Build guest command arguments for QEMU guest agent execution.

        Args:
            command: Command to execute in guest
            background: If True, run command in background
            cwd: Optional working directory for command execution
            admin: If True, run with elevated privileges (sudo on Linux)
            win_noprofile: VirtualBox-specific, silently ignored (different PowerShell invocation)
            use_cmd: VirtualBox-specific, not supported in QEMU
            run_as_user: VirtualBox-specific, not supported in QEMU (QGA handles session differently)
            binary_is_filepath: QEMU-specific, treat command as filepath in Start-Process
            redirect_stderr: Path to redirect stderr output
            redirect_stdout: Path to redirect stdout output
            hidden_window: Use hidden window style (Windows)

        Returns:
            List of command arguments for guest agent execution

        Raises:
            NotImplementedError: If VirtualBox-specific parameters are used
        """
        # Guard for unsupported VBox params
        if use_cmd:
            raise NotImplementedError("use_cmd not supported in QEMU")
        # win_noprofile - silently ignore (different PowerShell invocation)

        # Add cwd support
        if cwd:
            command = f'cd {cwd}; {command}' if 'windows' in self.guest_os.lower() else f'cd {cwd} && {command}'

        if 'windows' in self.guest_os.lower():
            if run_as_user:
                rl = "LIMITED" if not admin else "HIGHEST"
                delay = 30
                task_name = f"adare_task_{int(time.time())}"
                user = self.username
                pw = self.password
                script_path = "C:\\Windows\\Temp\\adare.ps1"
                if redirect_stderr:
                    command = f"{command} 2>>\"{redirect_stderr}\""
                if redirect_stdout:
                    command = f"{command} 1>>\"{redirect_stdout}\""

                command = (
                    f"& {{ "
                    f"$u = '{user}'; $p = '{pw}'; $t = '{task_name}'; "
                    f"$script = '{script_path}'; "
                    f"$st = (Get-Date).AddMinutes(2).ToString('HH:mm'); "
                    f"'{command}' | Out-File -FilePath $script -Encoding ascii; "
                    f"$c = \"powershell.exe -NoProfile -ExecutionPolicy Bypass -File $script\"; "
                    f"schtasks /Create /TN $t /TR \"$c\" /SC ONCE /ST $st /RU $u /RP $p /RL {rl} /IT /F; "
                    f"schtasks /Run /TN $t; "
                    f"Start-Sleep -Seconds {delay}; "
                    f"$info = schtasks /Query /TN $t /V /FO CSV | ConvertFrom-Csv; "
                    f"$status = $info.Status; "
                    f"$rc = $info.'Last Result'; "
                    f"$msg = \"Task_Status: $status | Last_Result: $rc\"; "
                    f"[Console]::Error.WriteLine($msg); "
                    f"if (Test-Path $script) {{ try {{ Remove-Item $script -Force -ErrorAction SilentlyContinue }} catch {{ }} }}; "
                    f"$portCheck = netstat -ano | Select-String ':18765.*LISTENING'; "
                    f"if (-not $portCheck -and $status -ne 'Running') {{ "
                    f"  [Console]::Error.WriteLine('FATAL: adarevm exited (task_status=$status, rc=$rc) and port 18765 is not listening'); "
                    f"  if (Test-Path 'C:\\Windows\\Temp\\adarevm_stderr.log') {{ "
                    f"    [Console]::Error.WriteLine('=== adarevm_stderr.log ==='); "
                    f"    Get-Content 'C:\\Windows\\Temp\\adarevm_stderr.log' -Tail 50 | ForEach-Object {{ [Console]::Error.WriteLine($_) }} "
                    f"  }}; "
                    f"  if (Test-Path 'C:\\Windows\\Temp\\adarevm_stdout.log') {{ "
                    f"    [Console]::Error.WriteLine('=== adarevm_stdout.log ==='); "
                    f"    Get-Content 'C:\\Windows\\Temp\\adarevm_stdout.log' -Tail 20 | ForEach-Object {{ [Console]::Error.WriteLine($_) }} "
                    f"  }}; "
                    f"  exit 1 "
                    f"}}; "
                    f"if ($status -eq 'Running' -or $rc -eq '0' -or $rc -eq '0x00041301' -or $rc -eq '267009') {{ exit 0 }} "
                    f"else {{ [Console]::Error.WriteLine(\"Scheduled task failed: status=$status result=$rc\"); exit 1 }}; "
                    f"}} "
                )
                log.debug(f"CLAUDE DEBUG: Full Windows guest command (Scheduled Task): {command}")
            if background and not run_as_user:
                import shlex
                command_components = shlex.split(command, posix=False)
                log.info(f"XXX: {command}")
                log.info(f"XXX: {command_components}")
                command = ["Start-Process"]
                if binary_is_filepath:
                    binary_path = command_components[0]
                    command += [f' -FilePath {binary_path}']
                else:
                    command += [f" {command_components[0]}"]
                arguments_string = " ".join(command_components[1:])
                if arguments_string:
                    command += [f' -ArgumentList "{arguments_string}"']
                if redirect_stderr:
                    command += [f" -RedirectStandardError {redirect_stderr}"]
                if redirect_stdout:
                    command += [f" -RedirectStandardOutput {redirect_stdout}"]
                if hidden_window:
                    command += [" -WindowStyle Hidden"]
                command = " ".join(command)

            if inject_user_path and not run_as_user:
                # Attempt lazy PATH discovery if not yet attempted
                if not self._cached_guest_path and not self._path_discovery_attempted:
                    log.debug("PATH not yet discovered, will use fallback for inject_user_path")

                if self._path_discovery_attempted and not self._cached_guest_path:
                    log.warning(
                        "PATH discovery was attempted but failed - "
                        "inject_user_path will use fallback paths only"
                    )

                base_path = self._cached_guest_path or ""

                custom_path_dirs = [
                    r'C:\adare\project_shared\tools',
                    r'C:\adare\shared\tools'
                ]

                # Join only the items that aren't empty
                paths = base_path + ";".join(custom_path_dirs)
                log.debug(f"Injecting user PATH dirs: {paths}")
                #command = f'$env:Path = "{path_dirs_str};$env:Path"; {command}'
                if background:
                    command = f'$env:Path += ";{paths}"; {command}'
                else:
                    command = f'$env:Path += ";{paths}"; & {command}'

            command_base64 = base64.b64encode(command.encode('utf-16le')).decode('utf-8')
            log.info(f"CLAUDE DEBUG: Full Windows guest command: {command}")
            return ["powershell.exe", "-EncodedCommand", command_base64]
        if redirect_stderr:
            stderr_redirect = f" 2>>{redirect_stderr}"
            command = f"{command}{stderr_redirect}"
        if redirect_stdout:
            stdout_redirect = f" 1>>{redirect_stdout}"
            command = f"{command}{stdout_redirect}"

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

    def _build_guest_environment(self) -> list[str]:
        """
        Build environment variables for QEMU Guest Agent command execution.

        Returns:
            List of environment variable strings in "NAME=VALUE" format
        """
        env_vars = []

        # Set HOME directory based on guest OS
        home_path = f"C:\\Users\\{self.username}" if 'windows' in self.guest_os.lower() else f"/home/{self.username}"

        env_vars.append(f"HOME={home_path}")

        # Set USER for completeness (Linux/Unix only)
        if 'windows' not in self.guest_os.lower():
            env_vars.append(f"USER={self.username}")

        # Set PATH - use discovered PATH from guest if available, otherwise fallback to hardcoded
        if self._cached_guest_path:
            # Combine discovered PATH with essential system paths
            if 'windows' in self.guest_os.lower():
                system_essentials = "C:\\Windows\\System32;C:\\Windows;C:\\Windows\\System32\\WindowsPowerShell\\v1.0"
                path_value = f"{self._cached_guest_path};{system_essentials}"
            else:
                path_value = self._cached_guest_path
            log.debug("Using discovered guest PATH")
        else:
            # Fallback to hardcoded minimal PATH for compatibility
            if 'windows' in self.guest_os.lower():
                path_value = "C:\\Windows\\System32;C:\\Windows;C:\\Windows\\System32\\WindowsPowerShell\\v1.0"
            else:
                path_value = "/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"

            if self._path_discovery_attempted:
                log.warning(
                    "Using hardcoded fallback PATH (discovery was attempted but failed). "
                    "Some user-installed tools may not be available."
                )
            else:
                log.debug("Using hardcoded fallback PATH (discovery not yet attempted)")

        env_vars.append(f"PATH={path_value}")

        # Set X11 environment variables for GUI automation (Linux only)
        # Always set DISPLAY for xhost and GUI automation (matches VirtualBox behavior)
        if 'windows' not in self.guest_os.lower():
            # Always set DISPLAY for Linux guests (required for xhost and GUI automation)
            env_vars.append("DISPLAY=:0")

            # Set XAUTHORITY only if detected (X11 will try default locations otherwise)
            if hasattr(self, '_cached_xauthority') and self._cached_xauthority:
                env_vars.append(f"XAUTHORITY={self._cached_xauthority}")
                log.debug(f"Using DISPLAY=:0 with XAUTHORITY={self._cached_xauthority}")
            else:
                log.debug("Using DISPLAY=:0 without XAUTHORITY (X11 will try default locations)")

            # Add ADARE_GUI_MODE environment variable if host-based GUI
            if hasattr(self, 'adare_gui_mode'):
                from adare.backend.experiment.execution.base import GUIExecutionMode
                if self.adare_gui_mode == GUIExecutionMode.HOST:
                    env_vars.append("ADARE_GUI_MODE=host")
                    log.info("Setting ADARE_GUI_MODE=host - PyAutoGUI will be skipped in guest")

        log.debug(f"Built guest environment: {env_vars}")
        return env_vars

    async def _wait_for_user_session(self, timeout: int = 90) -> bool:
        """
        Wait for user session to be fully initialized (Windows only).

        Checks for:
        1. explorer.exe running as the target user (indicates login)
        2. User's registry hive (HKEY_USERS\\<SID>\\Environment) is loaded

        Args:
            timeout: Maximum seconds to wait (default 90s)

        Returns:
            True if session is ready, False if timed out or check failed
        """
        if 'windows' not in self.guest_os.lower():
            return True

        try:
            log.debug(f"Waiting for user '{self.username}' session and registry hive...")

            # PowerShell command to check for explorer.exe AND registry hive
            # We need the SID to check the registry key
            check_cmd = (
                f'try {{ '
                f'$sid = (New-Object System.Security.Principal.NTAccount("{self.username}")).Translate([System.Security.Principal.SecurityIdentifier]).Value; '
                f'$regPath = "Registry::HKEY_USERS\\$sid\\Environment"; '
                f'$proc = Get-WmiObject Win32_Process -Filter "Name=\'explorer.exe\'" | '
                f'Where-Object {{ $_.GetOwner().User -eq \'{self.username}\' }}; '
                f'$hiveLoaded = Test-Path $regPath; '
                f'if ($proc -and $hiveLoaded) {{ "ready" }} else {{ "waiting: proc=" + [bool]$proc + ", hive=" + $hiveLoaded }} '
                f'}} catch {{ "error: " + $_ }}'
            )

            start_time = time.time()
            while time.time() - start_time < timeout:
                # Use short timeout for the check itself
                returncode, stdout, _ = await self._execute_guest_command_via_agent(
                    check_cmd,
                    timeout=10
                )

                stdout_str = stdout.strip().lower()
                if returncode == 0 and 'ready' in stdout_str:
                    log.info(f"User session and registry hive for '{self.username}' are ready")
                    return True

                # Log status every few seconds (throttled by the sleep)
                if 'waiting' in stdout_str or 'error' in stdout_str:
                    log.debug(f"Session wait status: {stdout.strip()}")

                await asyncio.sleep(2)

            log.warning(f"Timed out waiting for user session after {timeout}s")
            return False

        except (TimeoutError, HypervisorException, OSError) as e:
            log.warning(f"Error waiting for user session: {e}")
            return False

    async def _discover_guest_path(self) -> str | None:
        """
        Discover actual PATH environment variable from guest OS.

        Executes a command in the guest that sources user profile files
        to get the complete PATH including user-local directories like
        ~/.local/bin, ~/.miniforge3/bin, etc.

        This solves the problem where hardcoded PATH doesn't include
        user-installed tools (uv, conda, etc.) because QEMU guest
        agent executes commands with /bin/sh -c which doesn't source
        user shell configuration files.

        Returns:
            Discovered PATH string if successful, None if discovery fails.
            Failure is non-fatal - caller should fall back to hardcoded PATH.

        Raises:
            Does not raise - all exceptions are caught and logged as warnings.
        """
        if hasattr(self, '_cached_guest_path') and self._cached_guest_path:
            return self._cached_guest_path

        try:
            log.debug("Attempting to discover guest PATH environment")

            # Wait for user session on Windows to ensure registry is loaded
            if 'windows' in self.guest_os.lower():
                await self._wait_for_user_session()

            # Build discovery command based on guest OS
                # Windows: Get PATH from registry only (more robust than file search)
                # We prioritize user PATH over machine PATH
                discovery_cmd = (
                    f'$env:Path = [Environment]::GetEnvironmentVariable("PATH", "Machine"); '
                    f'try {{ '
                    f'$sid = (New-Object System.Security.Principal.NTAccount("{self.username}")).Translate([System.Security.Principal.SecurityIdentifier]).Value; '
                    f'$regPath = "Registry::HKEY_USERS\\" + $sid + "\\Environment"; '
                    f'$userPath = (Get-ItemProperty $regPath -ErrorAction SilentlyContinue).Path; '
                    f'if ($userPath) {{ $env:Path = $userPath + ";" + $env:Path }} '
                    f'}} catch {{}}; '
                    f'Write-Output $env:Path'
                )
            else:
                # Linux: Use login shell to source all profile files
                # -l flag activates login mode which sources /etc/profile, ~/.bash_profile, ~/.profile
                discovery_cmd = "/bin/bash -l -c 'echo $PATH'"

            # Execute discovery command with timeout
            # Using low-level guest-exec to avoid circular dependency
            # Windows PowerShell startup can be slow, especially on first run
            discovery_timeout = 120 if 'windows' in self.guest_os.lower() else 10
            returncode, stdout, stderr = await self._execute_guest_command_via_agent(
                command=discovery_cmd,
                timeout=discovery_timeout
            )

            stdout = stdout.strip()

            if returncode != 0:
                log.warning(
                    f"PATH discovery command failed with exit code {returncode}. "
                    f"stderr: {stderr[:100]}"
                )
                return None

            if not stdout:
                log.warning("PATH discovery returned empty output")
                return None

            # Validate discovered PATH
            if 'windows' in self.guest_os.lower():
                # Windows: PATH should contain at least one drive path (e.g., C:\)
                if ':\\' not in stdout:
                    log.warning(
                        f"Discovered Windows PATH appears invalid "
                        f"(no drive paths found): {stdout[:100]}"
                    )
                    return None
            else:
                # Linux: PATH should contain /bin or /usr/bin
                if '/bin' not in stdout and '/usr/bin' not in stdout:
                    log.warning(
                        f"Discovered Linux PATH appears invalid "
                        f"(missing /bin or /usr/bin): {stdout[:100]}"
                    )
                    return None

            log.info(f"Successfully discovered guest PATH: {stdout[:150]}...")
            self._cached_guest_path = stdout
            return stdout

        except TimeoutError:
            log.warning("PATH discovery timed out after 10 seconds")
            return None
        except (OSError, ConnectionError) as e:
            log.warning(f"PATH discovery failed due to connection error: {e}")
            return None
        except json.JSONDecodeError as e:
            log.warning(f"PATH discovery failed due to JSON parsing error: {e}")
            return None
        except KeyError as e:
            log.warning(f"PATH discovery failed due to missing expected key: {e}")
            return None

    async def _discover_python_scripts_path(self) -> str | None:
        """
        Discover the Scripts directory for the Python installation in the guest.
        This is where tools like adarevm, pip, uv are located.
        """
        if hasattr(self, '_cached_python_scripts_path') and self._cached_python_scripts_path:
            return self._cached_python_scripts_path

        try:
            log.debug("Attempting to discover Python Scripts path")

            # Wait for user session on Windows
            if 'windows' in self.guest_os.lower():
                await self._wait_for_user_session()

                # Check for Python in standard AppData location
                # We prioritize the User installation
                check_cmd = (
                    f'Get-ChildItem -Path "C:\\Users\\{self.username}\\AppData\\Local\\Programs\\Python" '
                    f'-Filter "Python*" -Directory -ErrorAction SilentlyContinue | '
                    f'Select-Object -First 1 -ExpandProperty FullName'
                )

                returncode, stdout, _ = await self._execute_guest_command_via_agent(
                    command=check_cmd,
                    timeout=30
                )

                if returncode == 0 and stdout.strip():
                    python_base = stdout.strip()
                    scripts_path = f"{python_base}\\Scripts"
                    log.info(f"Found Python Scripts path: {scripts_path}")
                    self._cached_python_scripts_path = scripts_path
                    return scripts_path

            return None

        except (TimeoutError, HypervisorException, OSError) as e:
            log.warning(f"Error discovering Python scripts path: {e}")
            return None

    async def _resolve_guest_executable_path(self, executable: str) -> str | None:
        """
        Resolve the absolute path for a guest executable (like adarevm).
        """
        # Cache key for this specific executable
        cache_attr = f'_cached_path_{executable}'
        if hasattr(self, cache_attr):
            return getattr(self, cache_attr)

        scripts_path = await self._discover_python_scripts_path()
        if scripts_path:
            # Construct candidate path
            candidate = f"{scripts_path}\\{executable}.exe"

            # Verify it exists
            check_cmd = f'Test-Path "{candidate}"'
            returncode, stdout, _ = await self._execute_guest_command_via_agent(
                command=check_cmd,
                timeout=10
            )

            if returncode == 0 and 'True' in stdout:
                log.info(f"Resolved {executable} to {candidate}")
                setattr(self, cache_attr, candidate)
                return candidate

        return None

    async def _detect_xauthority(self) -> str | None:
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
            log.debug("Attempting to detect XAUTHORITY file in guest")

            # Optimized detection: check most common locations first (fast path)
            detect_cmd = (
                # Fast path: Check most common locations first
                '[ -f "/run/user/$(id -u)/gdm/Xauthority" ] && echo "/run/user/$(id -u)/gdm/Xauthority" && exit 0; '
                '[ -f "/home/adare/.Xauthority" ] && echo "/home/adare/.Xauthority" && exit 0; '
                # Fallback: Full search if common locations fail
                'shopt -s nullglob; '
                'for p in '
                '"/run/user/$(id -u)/X11-display" '
                '/tmp/xauth_* '
                '/tmp/serverauth.* '
                '/run/sddm/xauth_* '
                '/run/user/$(id -u)/xauth_*; do '
                '[ -f "$p" ] && [ -r "$p" ] && { echo "$p"; exit 0; }; '
                'done; '
                'exit 1'
            )

            log.debug(f"Executing XAUTHORITY detection command: {detect_cmd[:100]}...")

            # Execute detection command via guest agent
            returncode, stdout, stderr = await self._execute_guest_command_via_agent(
                detect_cmd,
                timeout=10
            )

            if returncode == 0 and stdout.strip():
                # Successfully found XAUTHORITY file
                xauthority_path = stdout.strip().splitlines()[0]
                log.info(f"Successfully detected XAUTHORITY at: {xauthority_path}")
                return xauthority_path
            log.warning(
                f"XAUTHORITY detection failed (exit code {returncode}). "
                f"stdout: {stdout.strip()!r}, stderr: {stderr.strip()!r}"
            )
            log.debug("Will set DISPLAY without XAUTHORITY (X11 will try defaults)")
            return None

        except TimeoutError:
            log.warning("XAUTHORITY detection timed out after 10 seconds")
            return None
        except (OSError, ConnectionError) as e:
            log.warning(f"XAUTHORITY detection failed due to connection error: {e}")
            return None
        except (json.JSONDecodeError, KeyError) as e:
            log.warning(f"XAUTHORITY detection failed due to parsing error: {e}")
            return None

    async def _discover_and_cache_xauthority(self) -> str | None:
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
            log.debug(f"Using cached XAUTHORITY: {self._cached_xauthority}")
            return self._cached_xauthority

        # Perform discovery
        xauthority_path = await self._detect_xauthority()

        # Cache the result (even if None)
        self._cached_xauthority = xauthority_path

        if xauthority_path:
            log.info(f"Cached XAUTHORITY path: {xauthority_path}")
        else:
            log.warning("XAUTHORITY detection failed, X11 environment will not be configured")

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
        log.info(f"Copying '{guest_path}' from guest to '{host_path}' on host")

        # Check if VM is stopped
        if self.get_state() != "poweroff":
            log.error("VM must be stopped to use libguestfs file operations")
            return False

        try:
            import guestfs
        except ImportError:
            log.error("libguestfs Python bindings not available. Install python3-guestfs.")
            return False

        try:
            g = guestfs.GuestFS(python_return_dict=True)

            # Add the VM disk
            if not hasattr(self, 'config') or not hasattr(self.config, 'disk_path'):
                log.error("VM config or disk_path not available")
                return False

            disk_path = self.config.disk_path
            if not os.path.exists(disk_path):
                log.error(f"VM disk not found at {disk_path}")
                return False

            log.debug(f"Adding disk {disk_path} to libguestfs")
            g.add_drive_opts(disk_path, readonly=1)

            # Launch and mount
            log.debug("Launching libguestfs")
            g.launch()

            # Inspect and mount filesystems
            roots = g.inspect_os()
            if not roots:
                log.error("No operating system found in VM disk")
                g.close()
                return False

            root = roots[0]
            log.debug(f"Detected OS root: {root}")

            # Mount filesystems
            mps = g.inspect_get_mountpoints(root)

            # Sort mountpoints by length (mount / before /usr, etc.)
            for mountpoint, device in sorted(mps.items(), key=lambda x: len(x[0])):
                try:
                    log.debug(f"Mounting {device} on {mountpoint}")
                    g.mount_ro(device, mountpoint)
                except RuntimeError as e:
                    log.warning(f"Could not mount {device}: {e}")

            # Copy file or directory
            host_path_obj = Path(host_path)
            host_path_obj.parent.mkdir(parents=True, exist_ok=True)

            if recursive:
                # Check if it's a directory
                try:
                    is_dir = g.is_dir(guest_path)
                except RuntimeError:
                    log.error(f"Guest path '{guest_path}' not found")
                    g.close()
                    return False

                if is_dir:
                    log.debug(f"Copying directory '{guest_path}' recursively")
                    g.copy_out(guest_path, str(host_path_obj.parent))
                else:
                    log.debug(f"Copying file '{guest_path}'")
                    g.download(guest_path, host_path)
            else:
                log.debug(f"Copying file '{guest_path}'")
                g.download(guest_path, host_path)

            g.close()
            log.info(f"Successfully copied '{guest_path}' to '{host_path}'")
            return True

        except (RuntimeError, OSError) as e:
            log.error(f"Failed to copy from guest: {e}")
            return False

    async def _execute_guest_command_via_agent(
        self,
        command: str,
        background: bool = False,
        stop_event: threading.Event | None = None,
        timeout: int = 300,
        admin: bool = False,
        cwd: str | None = None,
        redirect_stderr: str = "",
        redirect_stdout: str = "",
        binary_is_filepath: bool = False,
        run_as_user: bool = False,
        inject_user_path: bool = False,
    ) -> tuple[int, str, str]:
        """
        Execute command in guest via QEMU Guest Agent.

        Args:
            command: Command to execute
            background: If True, don't wait for command completion
            stop_event: Optional event to signal cancellation
            timeout: Timeout in seconds
            admin: If True, run with elevated privileges
            cwd: Optional working directory for command execution
            redirect_stderr: Path to redirect stderr output (QEMU-specific)
            redirect_stdout: Path to redirect stdout output (QEMU-specific)
            binary_is_filepath: If True, treat command as filepath in Start-Process (QEMU-specific)
            run_as_user: If True, use scheduled task for user session execution (QEMU-specific)

        Returns:
            Tuple of (returncode, stdout, stderr)
        """
        if self.get_state() != "running":
            log.error("VM must be running to execute guest commands")
            return -1, "", "VM not running"

        if not hasattr(self, 'config') or not self.config.guest_agent_socket_path:
            log.error("Guest agent socket not configured")
            return -1, "", "Guest agent not configured"

        socket_path = self.config.guest_agent_socket_path
        if not os.path.exists(socket_path):
            log.error(f"Guest agent socket not found at {socket_path}")
            return -1, "", "Guest agent socket not found"

        try:
            # Build command args - PATH injection in _build_guest_command_args() handles
            # making tools like adarevm, pip, python accessible (no need for path resolution)
            cmd_args = self._build_guest_command_args(
                command,
                background=background,
                admin=admin,
                cwd=cwd,
                redirect_stderr=redirect_stderr,
                redirect_stdout=redirect_stdout,
                binary_is_filepath=binary_is_filepath,
                run_as_user=run_as_user,
                inject_user_path=inject_user_path,
            )

            # Build environment variables for guest execution
            env_vars = self._build_guest_environment()

            # Execute via QMP using guest-exec with environment variables
            # Format: {"execute": "guest-exec", "arguments": {"path": "/bin/sh", "arg": ["-c", "command"], "env": ["HOME=/home/user"]}}
            qga_args = {
                "path": cmd_args[0],
                "arg": cmd_args[1:] if len(cmd_args) > 1 else [],
                "capture-output": True
            }

            # Only provide 'env' for non-Windows guests.
            # On Windows, providing 'env' replaces the entire environment block, stripping critical
            # variables like SystemRoot, ComSpec, and machine PATH, causing PowerShell to fail.
            # By omitting 'env', QGA inherits the default system environment (NT AUTHORITY\SYSTEM),
            # which we then augment with our user PATH injection script.
            if 'windows' not in self.guest_os.lower() and env_vars:
                qga_args["env"] = env_vars

            qga_cmd = {
                "execute": "guest-exec",
                "arguments": qga_args
            }

            # CLAUDE DEBUG: Log the EXACT JSON payload being sent to libvirt to verify 'env' is missing
            import json
            log.debug(f"CLAUDE DEBUG: QGA JSON payload: {json.dumps(qga_cmd)}")

            # Send command via libvirt API (not direct socket access)
            qga_response = await self._send_qga_command_via_libvirt(qga_cmd)

            if 'error' in qga_response:
                error_msg = qga_response['error'].get('desc', 'Unknown error')
                log.error(f"Guest agent error: {error_msg}")
                return -1, "", error_msg

            # Get PID from response
            pid = qga_response.get('return', {}).get('pid')
            if not pid:
                log.error("No PID returned from guest-exec")
                return -1, "", "No PID returned"

            if background:
                log.debug(f"Command started in background with PID {pid}")
                return 0, f"Started with PID {pid}", ""

            # Wait for command to complete and get status
            start_time = time.time()
            while time.time() - start_time < timeout:
                if stop_event and stop_event.is_set():
                    log.info("Stop event detected, abandoning guest command wait")
                    return -1, "", "Cancelled"

                status_cmd = {
                    "execute": "guest-exec-status",
                    "arguments": {"pid": pid}
                }

                status_response = await self._send_qga_command_via_libvirt(status_cmd)

                if 'error' in status_response:
                    error_msg = status_response['error'].get('desc', 'Unknown error')
                    log.error(f"Guest agent status error: {error_msg}")
                    return -1, "", error_msg

                status_data = status_response.get('return', {})
                if status_data.get('exited', False):
                    returncode = status_data.get('exitcode', -1)
                    stdout_b64 = status_data.get('out-data', '')
                    stderr_b64 = status_data.get('err-data', '')

                    # Decode base64 output
                    stdout = base64.b64decode(stdout_b64).decode('utf-8', errors='replace') if stdout_b64 else ""
                    stderr = base64.b64decode(stderr_b64).decode('utf-8', errors='replace') if stderr_b64 else ""

                    log.debug(f"Guest command completed with return code {returncode}")
                    return returncode, stdout, stderr

                # Sleep briefly before checking again
                await asyncio.sleep(0.5)

            log.error("Timeout waiting for guest command to complete")
            return -1, "", "Timeout"

        except TimeoutError as e:
            log.error(f"Timeout executing guest command '{command}': {e}")
            return -1, "", f"Command execution timeout: {e}"
        except json.JSONDecodeError as e:
            log.error(f"Invalid JSON response from guest agent for command '{command}': {e}")
            return -1, "", f"Invalid JSON response: {e}"
        except ConnectionError as e:
            log.error(f"Connection error executing guest command '{command}': {e}")
            return -1, "", f"Connection error: {e}"
        except OSError as e:
            log.error(f"OS error executing guest command '{command}': {e}")
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
            log.debug(f"Attempting to connect to guest agent socket: {socket_path}")
            reader, writer = await asyncio.open_unix_connection(socket_path)
            log.debug("Successfully connected to guest agent socket")

            # Step 1: Handle QMP greeting (protocol requirement)
            # The guest agent may send a greeting message on first connection
            try:
                greeting_line = await asyncio.wait_for(reader.readline(), timeout=0.5)
                greeting = json.loads(greeting_line.decode('utf-8'))

                # Check if this is a QMP greeting
                if 'QMP' in greeting:
                    log.debug(f"Received QGA greeting: {greeting}")
                    # Greeting received and discarded - proceed with command
                else:
                    # Not a greeting - this shouldn't happen, but log it
                    log.warning(f"Unexpected first message from QGA: {greeting}")
                    # Treat it as the actual response (fallback behavior)
                    writer.close()
                    await writer.wait_closed()
                    return greeting

            except TimeoutError:
                # No greeting received - this is fine, some QGA versions don't send it
                log.debug("No QGA greeting received (timeout), proceeding with command")
            except json.JSONDecodeError as e:
                # Invalid JSON in greeting - log but continue
                log.warning(f"Failed to parse QGA greeting: {e}")

            # Step 2: Send command as JSON
            cmd_json = json.dumps(command) + '\n'
            log.debug(f"Sending QGA command: {command.get('execute', 'unknown')}")
            log.debug(f"Command JSON: {cmd_json.strip()}")
            writer.write(cmd_json.encode('utf-8'))
            log.debug("Command written to buffer, flushing...")
            await writer.drain()
            log.debug("Command flushed successfully")

            # Step 3: Read response with timeout to prevent indefinite blocking
            response_line = await asyncio.wait_for(reader.readline(), timeout=5.0)
            response = json.loads(response_line.decode('utf-8'))

            log.debug(f"QGA response: {response}")

            writer.close()
            await writer.wait_closed()

            return response

        except TimeoutError as e:
            log.error(f"Timeout communicating with guest agent: {e}")
            return {"error": {"desc": f"Communication timeout: {e}"}}
        except json.JSONDecodeError as e:
            log.error(f"Failed to parse guest agent response: {e}")
            return {"error": {"desc": f"Invalid JSON response: {e}"}}
        except ConnectionRefusedError as e:
            log.error(f"Guest agent connection refused: {e}")
            return {"error": {"desc": f"Connection refused: {e}"}}
        except FileNotFoundError as e:
            log.error(f"Guest agent socket not found: {e}")
            return {"error": {"desc": f"Socket not found: {e}"}}
        except OSError as e:
            # Log detailed error information including errno
            errno_num = getattr(e, 'errno', 'unknown')
            log.error(f"OS error communicating with guest agent: {e} (errno={errno_num})")
            log.error(f"Socket path: {socket_path}")
            log.error(f"Command attempted: {command.get('execute', 'unknown')}")
            return {"error": {"desc": f"OS error: {e}"}}

    async def _send_qga_command_via_libvirt(self, command: dict, timeout: int = 5) -> dict:
        """
        Send command to QEMU Guest Agent via libvirt API.

        This is the correct way to communicate with guest agent when using
        libvirt to manage VMs. Direct socket access fails (errno 22) because
        libvirt owns the socket connection.

        Args:
            command: QGA command dictionary
            timeout: Seconds to wait for guest agent response (default 5)

        Returns:
            Response dictionary
        """
        async def _qga_async():
            import libvirt
            try:
                # Ensure libvirt domain is available
                try:
                    self._ensure_libvirt_domain()
                except HypervisorException as e:
                    return {"error": {"desc": f"Domain not available: {e}"}}

                # Send command via libvirt API
                cmd_json = json.dumps(command)
                execute_name = command.get('execute', 'unknown')
                if execute_name == 'guest-exec':
                    args = command.get('arguments', {})
                    path = args.get('path', '')
                    cmd_args = args.get('arg', [])
                    full_cmd = " ".join([path] + cmd_args)
                    log.debug(f"Sending QGA command via libvirt: guest-exec ({full_cmd})")
                else:
                    log.debug(f"Sending QGA command via libvirt: {execute_name}")

                # Get experiment log file for stderr capture
                log_file = get_experiment_log_file()

                # Suppress libvirt warnings from console, capture to log
                with LibvirtStderrRedirect(log_file=log_file, suppress_console=True):
                    result = libvirt_qemu.qemuAgentCommand(
                        self._libvirt_domain,
                        cmd_json,
                        timeout,  # seconds; callers pass higher values for file I/O
                        0   # flags
                    )

                return json.loads(result)

            except libvirt.libvirtError as e:
                log.error(f"Libvirt error sending QGA command: {e}")
                return {"error": {"desc": f"Libvirt error: {e}"}}
            except json.JSONDecodeError as e:
                log.error(f"Failed to parse QGA response: {e}")
                return {"error": {"desc": f"Invalid JSON: {e}"}}
            except (OSError, AttributeError, TypeError) as e:
                log.error(f"Unexpected error: {e}")
                return {"error": {"desc": f"Error: {e}"}}

        # Run via manager's async executor
        return await self.manager.run_async(_qga_async)

    async def _check_process_status_via_agent(
        self,
        pid: int,
        timeout: int = 5
    ) -> tuple[bool, int | None, str]:
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
                log.warning(f"Failed to check process {pid} status: {error_msg}")
                return False, None, error_msg

            status_data = status_response.get('return', {})
            exited = status_data.get('exited', False)

            if exited:
                exit_code = status_data.get('exitcode', -1)
                log.debug(f"Process {pid} has exited with code {exit_code}")
                return False, exit_code, ""
            log.debug(f"Process {pid} is still running")
            return True, None, ""

        except TimeoutError:
            error_msg = "Timeout checking process status"
            log.warning(f"{error_msg} for PID {pid}")
            return False, None, error_msg
        except (OSError, ConnectionError) as e:
            error_msg = f"Connection error: {e}"
            log.warning(f"{error_msg} while checking PID {pid}")
            return False, None, error_msg
        except (json.JSONDecodeError, KeyError) as e:
            error_msg = f"Parsing error: {e}"
            log.warning(f"{error_msg} while checking PID {pid}")
            return False, None, error_msg
