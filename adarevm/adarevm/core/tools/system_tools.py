"""
System tool methods for AdareVMServer.

Provides dependency installation, shell execution, system info collection,
timezone handling, screenshot method configuration, and command chaining.
"""

from __future__ import annotations

import asyncio
import logging
import os
import platform
import time
from pathlib import Path
from typing import Any, Dict, List

import websockets

from adarevm.automation.shell import execute_on_shell
from adarelib.websocket.protocol import EventType

log = logging.getLogger(__name__)


class SystemToolsMixin:
    """Mixin providing system-level tool methods."""

    # ------------------------------------------------------------------ #
    # Helper methods (not exposed as tools)
    # ------------------------------------------------------------------ #

    def _is_wheel_installation(self) -> bool:
        """Detect if adarevm was installed from wheel (vs Poetry editable).

        Returns:
            True if installed from wheel, False if editable/development install
        """
        import importlib.metadata

        try:
            # Get adarevm package metadata
            dist = importlib.metadata.distribution('adarevm')

            # Check if direct_url.json exists (indicates editable/VCS install)
            # Wheel installs don't have direct_url.json
            try:
                if dist.read_text('direct_url.json'):
                    log.info("Detected editable installation (direct_url.json found)")
                    return False  # Editable/development install
            except FileNotFoundError:
                # No direct_url.json = wheel install
                log.info("Detected wheel installation (no direct_url.json)")
                return True

        except Exception as e:
            log.warning(f"Could not determine installation mode: {e}, defaulting to wheel mode")

        return True  # Default to wheel mode

    def _get_pip_command(self) -> List[str]:
        """Get the appropriate pip command for current environment.

        Returns:
            List of command components for pip installation
        """
        # Check if running in conda environment
        conda_env = os.environ.get('CONDA_DEFAULT_ENV')
        if conda_env == 'pyadare':
            if platform.system() == 'Windows':
                conda_exe = Path(os.environ.get('USERPROFILE', '')) / '.miniforge3' / 'Scripts' / 'conda.exe'
            else:
                conda_exe = Path.home() / '.miniforge3' / 'bin' / 'conda'

            if conda_exe.exists():
                # Conda: pip install --no-cache-dir
                log.info(f"Using conda environment: {conda_exe}")
                return [str(conda_exe), 'run', '-n', 'pyadare', 'pip', 'install', '--no-cache-dir']

        # Fallback to system pip with  flag
        pip_cmd = 'pip' if platform.system() == 'Windows' else 'pip3'
        cmd = [pip_cmd, 'install', '--no-cache-dir']

        log.info(f"Using system pip: {' '.join(cmd)}")
        return cmd

    def _find_project_directory(self) -> str:
        """Find the adarevm project directory containing pyproject.toml."""
        # Platform-specific base paths
        if platform.system() == "Windows":
            possible_paths = [
                "C:/adare/vm/adarevm",  # Primary Windows deployment path
                "C:/adare/vm",           # VM runtime base path
                "C:/adare",              # Alternative deployment path
                Path(__file__).parent.parent.parent,  # Development path
                Path.cwd(),              # Current working directory
            ]
        else:
            possible_paths = [
                "/adare/vm/adarevm",  # Primary Linux deployment path
                "/adare/vm",          # VM runtime base path
                "/adare",             # Alternative deployment path
                Path(__file__).parent.parent.parent,  # Development path
                Path.cwd(),           # Current working directory
            ]

        for path in possible_paths:
            path = Path(path)
            pyproject_path = path / "pyproject.toml"
            if pyproject_path.exists():
                log.info(f"Found pyproject.toml at: {path}")
                return str(path)

        # Fallback to current directory
        log.warning("Could not find pyproject.toml, falling back to current directory")
        cwd = Path.cwd()
        log.warning(f"Using current working directory: {cwd}")
        return str(cwd)

    # ------------------------------------------------------------------ #
    # Dependency installation
    # ------------------------------------------------------------------ #

    async def _run_install_command(
        self,
        websocket,
        cmd: List[str],
        installer_label: str,
        dep_count: int,
        cwd: str | None = None,
        final_step: str = "2/2",
        install_verb: str = "install",
    ) -> Dict[str, Any]:
        """Run a dependency installation subprocess with heartbeat and error handling.

        Shared logic for both Poetry/uv and pip installers. Handles subprocess
        creation, heartbeat-based waiting, output decoding, and result reporting.

        Args:
            websocket: WebSocket connection
            cmd: Full command list to execute
            installer_label: Human-readable installer name for log messages (e.g. "Poetry", "Pip")
            dep_count: Number of dependencies being installed (for success message)
            cwd: Working directory for the subprocess (None for current directory)
            final_step: Step label for the final progress message (e.g. "4/4", "2/2")
            install_verb: Verb for error messages (e.g. "add" for Poetry, "install" for pip)

        Returns:
            Result dict with status, message, and installer output
        """
        log.info(f"Running command: {' '.join(cmd)}" + (f" in directory: {cwd}" if cwd else ""))
        await self.send_event(websocket, EventType.LOG, {"message": f"Command: {' '.join(cmd)}"})

        await self.send_event(websocket, EventType.LOG, {
            "message": f"Step {final_step}: Installing dependencies (this may take several minutes)..."
        })

        # Use asyncio subprocess to avoid blocking the event loop
        process = await asyncio.create_subprocess_exec(
            *cmd,
            cwd=cwd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )

        # Wait for process with periodic heartbeat to keep WebSocket alive
        stdout_bytes, stderr_bytes = await self._wait_for_process_with_heartbeat(
            websocket, process, timeout=600.0
        )

        # Decode bytes to string
        stdout = stdout_bytes.decode('utf-8') if stdout_bytes else ""
        stderr = stderr_bytes.decode('utf-8') if stderr_bytes else ""

        output_key = f"{installer_label.lower()}_output"

        if process.returncode != 0:
            await self.send_event(websocket, EventType.LOG, {"message": f"Step {final_step}: Installation failed"})
            error_msg = f"{installer_label} {install_verb} failed with exit code {process.returncode}"
            if stderr.strip():
                error_msg += f": {stderr}"
            else:
                error_msg += " (no error output)"
            if stdout.strip():
                error_msg += f"\nStdout: {stdout}"

            log.error(error_msg)
            log.error(f"{installer_label} command details - Exit code: {process.returncode}, Stderr: '{stderr}', Stdout: '{stdout}'")
            await self.send_event(websocket, EventType.ERROR, {"message": error_msg})
            return {"status": "error", "message": error_msg}

        await self.send_event(websocket, EventType.LOG, {"message": f"Step {final_step}: Installation completed successfully"})
        success_msg = f"Successfully installed all {dep_count} dependencies with {installer_label}"
        log.info(success_msg)
        log.debug(f"{installer_label} output: {stdout}")
        await self.send_event(websocket, EventType.LOG, {"message": success_msg})

        return {
            "status": "success",
            "message": success_msg,
            "installed_count": dep_count,
            output_key: stdout
        }

    async def _install_dependencies_poetry(self, websocket, dependencies: List[str], prefer_binary: bool = False):
        """Install Python dependencies using Poetry/uv (for editable/development installs).

        Args:
            websocket: WebSocket connection
            dependencies: List of dependencies to install
            prefer_binary: If True, configure uv for binary-only packages (avoid compilation)
        """
        await self.send_event(websocket, EventType.LOG, {"message": f"Starting dependency installation: {len(dependencies)} packages"})

        try:
            if not dependencies:
                log.info("No dependencies to install")
                return {"status": "success", "message": "No dependencies to install"}

            log.info(f"Installing dependencies with Poetry: {dependencies}")

            # Step 1: Find project directory
            await self.send_event(websocket, EventType.LOG, {"message": "Step 1/4: Locating pyproject.toml..."})
            project_dir = self._find_project_directory()
            await self.send_event(websocket, EventType.LOG, {"message": f"Found project directory: {project_dir}"})

            step_count = "4" if not prefer_binary else "5"
            current_step = 2

            # Step 2: Configure uv for binary-only installation (if requested)
            if prefer_binary:
                await self.send_event(websocket, EventType.LOG, {"message": f"Step {current_step}/{step_count}: Configuring uv for binary-only installation..."})
                # uv handles binary preference via --only-binary flag during add
                log.info("Binary-only preference will be applied during uv add")
                current_step += 1

            # Step 2/3: Prepare uv add command
            await self.send_event(websocket, EventType.LOG, {"message": f"Step {current_step}/{step_count}: Preparing uv command..."})
            cmd = ["uv", "add"] + dependencies
            if prefer_binary:
                cmd.insert(2, "--only-binary")
            current_step += 1

            # Step 3/4: Execute installation via shared method
            final_step = f"{step_count}/{step_count}"
            return await self._run_install_command(
                websocket, cmd, "Poetry", len(dependencies),
                cwd=project_dir, final_step=final_step,
                install_verb="add",
            )

        except asyncio.TimeoutError as e:
            error_msg = f"Poetry dependency installation timed out: {e}"
            log.error(error_msg)
            await self.send_event(websocket, EventType.ERROR, {"message": error_msg})
            return {"status": "error", "message": error_msg}
        except (OSError, FileNotFoundError) as e:
            error_msg = f"Poetry dependency installation failed: {e}"
            log.error(error_msg)
            await self.send_event(websocket, EventType.ERROR, {"message": error_msg})
            return {"status": "error", "message": error_msg}

    async def _install_dependencies_pip(self, websocket, dependencies: List[str], prefer_binary: bool = False):
        """Install Python dependencies using pip (for wheel-based installs).

        Args:
            websocket: WebSocket connection
            dependencies: List of dependencies to install
            prefer_binary: If True, prefer binary packages (passed as --only-binary :all:)
        """
        await self.send_event(websocket, EventType.LOG, {"message": f"Starting dependency installation: {len(dependencies)} packages"})

        try:
            if not dependencies:
                log.info("No dependencies to install")
                return {"status": "success", "message": "No dependencies to install"}

            log.info(f"Installing dependencies with pip: {dependencies}")

            # Step 1: Get pip command
            await self.send_event(websocket, EventType.LOG, {"message": "Step 1/2: Preparing pip command..."})
            pip_cmd = self._get_pip_command()

            # Add prefer_binary flag if requested
            if prefer_binary:
                pip_cmd.append('--only-binary')
                pip_cmd.append(':all:')

            # Add dependencies
            cmd = pip_cmd + dependencies

            # Step 2: Execute installation via shared method
            return await self._run_install_command(
                websocket, cmd, "Pip", len(dependencies),
                final_step="2/2",
            )

        except asyncio.TimeoutError as e:
            error_msg = f"Pip dependency installation timed out: {e}"
            log.error(error_msg)
            await self.send_event(websocket, EventType.ERROR, {"message": error_msg})
            return {"status": "error", "message": error_msg}
        except (OSError, FileNotFoundError) as e:
            error_msg = f"Pip dependency installation failed: {e}"
            log.error(error_msg)
            await self.send_event(websocket, EventType.ERROR, {"message": error_msg})
            return {"status": "error", "message": error_msg}

    async def _install_dependencies(self, websocket, dependencies: List[str], prefer_binary: bool = False):
        """Install Python dependencies using the appropriate package manager.

        Routes to Poetry (editable install) or pip (wheel install) based on configured installation mode.

        Args:
            websocket: WebSocket connection
            dependencies: List of dependencies to install
            prefer_binary: If True, prefer binary packages
        """
        # Use explicit config (with fallback to auto-detection for backward compat)
        if self.installation_mode == "editable":
            log.info("Using Poetry for dependency installation (configured: editable)")
            await self.send_event(websocket, EventType.LOG, {"message": "Installation mode: Poetry (editable)"})
            return await self._install_dependencies_poetry(websocket, dependencies, prefer_binary)
        elif self.installation_mode == "wheel":
            log.info("Using pip for dependency installation (configured: wheel)")
            await self.send_event(websocket, EventType.LOG, {"message": "Installation mode: pip (wheel-based)"})
            return await self._install_dependencies_pip(websocket, dependencies, prefer_binary)
        else:
            # Fallback to auto-detection for unknown/legacy values
            log.warning(f"Unknown installation_mode: {self.installation_mode}, falling back to auto-detection")
            is_wheel_mode = self._is_wheel_installation()
            if is_wheel_mode:
                log.info("Using pip for dependency installation (auto-detected: wheel mode)")
                await self.send_event(websocket, EventType.LOG, {"message": "Installation mode: pip (auto-detected)"})
                return await self._install_dependencies_pip(websocket, dependencies, prefer_binary)
            else:
                log.info("Using Poetry for dependency installation (auto-detected: editable mode)")
                await self.send_event(websocket, EventType.LOG, {"message": "Installation mode: Poetry (auto-detected)"})
                return await self._install_dependencies_poetry(websocket, dependencies, prefer_binary)

    # ------------------------------------------------------------------ #
    # Process management
    # ------------------------------------------------------------------ #

    async def _wait_for_process_with_heartbeat(self, websocket, process, timeout=600.0, heartbeat_interval=30.0):
        """Wait for subprocess with periodic WebSocket heartbeat to prevent disconnection.

        Args:
            websocket: WebSocket connection for heartbeat messages
            process: asyncio subprocess to monitor
            timeout: Maximum time to wait for process completion
            heartbeat_interval: Seconds between heartbeat messages

        Returns:
            Tuple of (stdout, stderr) from process

        Raises:
            asyncio.TimeoutError: If process exceeds timeout
            OSError: If process execution fails
        """
        start_time = time.time()
        heartbeat_task = None
        websocket_alive = True

        async def send_heartbeat():
            """Send periodic heartbeat messages to keep WebSocket alive."""
            nonlocal websocket_alive
            heartbeat_count = 0

            while True:
                try:
                    await asyncio.sleep(heartbeat_interval)
                    if not websocket_alive:
                        break

                    heartbeat_count += 1
                    elapsed = time.time() - start_time
                    await self.send_event(websocket, EventType.LOG, {
                        "message": f"Installation in progress... ({elapsed:.0f}s elapsed)"
                    })
                    log.debug(f"Sent heartbeat {heartbeat_count} after {elapsed:.1f}s")

                except websockets.exceptions.ConnectionClosed:
                    log.warning("WebSocket disconnected during heartbeat, continuing process in background")
                    websocket_alive = False
                    break
                except Exception as e:
                    log.warning(f"Heartbeat failed: {e}, continuing process", exc_info=True)
                    websocket_alive = False
                    break

        try:
            # Start heartbeat task
            heartbeat_task = asyncio.create_task(send_heartbeat())

            # Wait for process with timeout
            stdout, stderr = await asyncio.wait_for(
                process.communicate(),
                timeout=timeout
            )

            return stdout, stderr

        except websockets.exceptions.ConnectionClosed:
            log.warning("WebSocket disconnected during process wait, continuing in background")
            websocket_alive = False
            # Continue waiting for process even if WebSocket is gone
            stdout, stderr = await asyncio.wait_for(
                process.communicate(),
                timeout=timeout
            )
            return stdout, stderr

        finally:
            # Clean up heartbeat task
            if heartbeat_task and not heartbeat_task.done():
                heartbeat_task.cancel()
                try:
                    await heartbeat_task
                except asyncio.CancelledError:
                    pass

    # ------------------------------------------------------------------ #
    # Shell execution
    # ------------------------------------------------------------------ #

    async def _execute_shell(self, websocket, shell_command: str, cwd: str = None, env: dict = None, timeout: float = None, shell: bool = None, inherit_env: bool = True, admin: bool = False, background: bool = False, run_as_user: str = None):
        """Execute a raw shell command with advanced options."""
        import uuid

        # Generate unique command ID for tracking
        command_id = str(uuid.uuid4())[:8]
        start_time = time.time()

        log.info(f"[{command_id}] Executing shell command: {shell_command}")
        log.debug(f"[{command_id}] Command options - cwd: {cwd}, timeout: {timeout}, shell: {shell}, inherit_env: {inherit_env}, admin: {admin}, background: {background}, run_as_user: {run_as_user}")

        try:
            await self.send_event(websocket, EventType.COMMAND_START, {
                "shell_command": shell_command,
                "command_id": command_id,
                "start_time": start_time
            })

            # Prepare options for execute_on_shell
            options = {}
            if cwd:
                options['cwd'] = Path(cwd)

            # Handle environment variables and tools paths
            # Start with provided env or empty dict
            cmd_env = env.copy() if env else {}

            # If inheriting env, we need to know the base path to append to
            # But execute_on_shell handles inheritance internally if we don't pass full env.
            # However, to append to PATH, we need to know the current PATH.
            # If inherit_env is True, we should probably let execute_on_shell handle the base env,
            # but we need to inject our tools paths.
            # The safest way is to construct the full env here if we are modifying it.

            # Determine base environment
            if inherit_env:
                base_env = os.environ.copy()
                base_env.update(cmd_env)
                cmd_env = base_env
                options['inherit_env'] = False # We are manually inheriting

            # Append tools paths to PATH
            if self.tools_paths:
                # Find PATH key (case-insensitive)
                path_key = next((k for k in cmd_env.keys() if k.lower() == 'path'), 'PATH')
                current_path = cmd_env.get(path_key, '')

                # Append tool paths using os.pathsep
                additional_paths = os.pathsep.join(self.tools_paths)
                if current_path:
                    cmd_env[path_key] = f"{current_path}{os.pathsep}{additional_paths}"
                else:
                    cmd_env[path_key] = additional_paths

                log.debug(f"[{command_id}] Appended tool paths to PATH: {additional_paths}")

            log.info(f"command environment: {cmd_env}")

            options['env'] = cmd_env

            if timeout:
                options['timeout'] = timeout
            # options['inherit_env'] is already handled above
            if admin is not None:
                options['admin'] = admin
            if background is not None:
                options['background'] = background
            if run_as_user is not None:
                options['run_as_user'] = run_as_user

            if shell is not None:
                options['shell'] = shell
            else:
                # Auto-detect if shell mode is needed based on special characters
                # Note: On Windows, $ is not a special character in cmd.exe (default shell=True backend if powershell=False)
                # But it IS special in PowerShell. Since execute_on_shell defaults to PowerShell when shell=True,
                # detecting $ triggers PowerShell which then expands it (breaking paths like C:\$Recycle.Bin).
                # We should be conservative: only trigger shell if it's clearly a shell operation like redirection.
                shell_chars = ['>', '<', '>>', '|', '||', '&&', ';', '`', '$', '*', '?', '~']

                if platform.system().lower() == 'windows':
                     # Remove chars that are not special in cmd.exe or shouldn't auto-trigger shell
                     if '$' in shell_chars: shell_chars.remove('$')
                     if '~' in shell_chars: shell_chars.remove('~')

                if any(char in shell_command for char in shell_chars):
                    options['shell'] = True
                    log.info(f"Auto-enabled shell mode for command with special characters: {shell_command}")

            # Execute shell command directly using execute_on_shell
            # When shell=True, pass command as string; otherwise split into list
            # Log command execution start
            log.debug(f"[{command_id}] Starting shell execution with options: {options}")

            if options.get('shell', False):
                result = await asyncio.to_thread(execute_on_shell, shell_command, **options)
            else:
                # Use platform-aware splitting for better argument handling
                split_command = self._split_command_line(shell_command)
                result = await asyncio.to_thread(execute_on_shell, split_command, **options)

            # Log stdout/stderr at debug level with command context
            if not result.get('background'):
                log.info(f"[{command_id}] stdout: {result.get('stdout', '')}")
                log.info(f"[{command_id}] stderr: {result.get('stderr', '')}")

            execution_time = time.time() - start_time

            # Handle background mode response
            if result.get('background'):
                await self.send_event(websocket, EventType.COMMAND_COMPLETE, {
                    "shell_command": shell_command,
                    "command_id": command_id,
                    "background": True,
                    "pid": result.get('pid')
                })
                log.info(f"[{command_id}] Background command started with PID {result.get('pid')}: {shell_command}")
                return {
                    "status": "success",
                    "message": f"Background command started",
                    "background": True,
                    "pid": result.get('pid'),
                    "command_id": command_id
                }

            # Handle normal mode response
            if result['returncode'] == 0:
                await self.send_event(websocket, EventType.COMMAND_COMPLETE, {
                    "shell_command": shell_command,
                    "command_id": command_id,
                    "execution_time": execution_time
                })
                log.info(f"[{command_id}] Shell command completed successfully in {execution_time:.2f}s: {shell_command}")
                return {
                    "status": "success",
                    "message": f"Shell command executed successfully",
                    "returncode": result['returncode'],
                    "stdout": result['stdout'],
                    "command_id": command_id,
                    "execution_time": execution_time
                }
            else:
                await self.send_event(websocket, EventType.ERROR, {
                    "message": f"Shell command failed: {shell_command}",
                    "command_id": command_id,
                    "execution_time": execution_time
                })
                log.error(f"[{command_id}] Shell command failed with return code {result['returncode']} in {execution_time:.2f}s: {shell_command}")
                return {
                    "status": "error",
                    "message": f"Shell command failed with return code {result['returncode']}",
                    "returncode": result['returncode'],
                    "stdout": result['stdout'],
                    "command_id": command_id,
                    "execution_time": execution_time
                }

        except Exception as e:
            execution_time = time.time() - start_time
            log.error(f"[{command_id}] Unexpected shell command error after {execution_time:.2f}s: {shell_command}: {e}")
            await self.send_event(websocket, EventType.ERROR, {
                "message": f"Shell command '{shell_command}' failed: {e}",
                "command_id": command_id,
                "execution_time": execution_time
            })
            return {
                "status": "error",
                "message": str(e),
                "command_id": command_id,
                "execution_time": execution_time
            }

    # ------------------------------------------------------------------ #
    # Status and info
    # ------------------------------------------------------------------ #

    async def _get_status(self, websocket):
        """Get current server status."""
        return {
            "testfunctions_uploaded": self.testfunctions_dir is not None and self.testfunctions_dir.exists(),
            "testfunctions_path": str(self.testfunctions_dir) if self.testfunctions_dir else None,
            "variables_count": len(self.current_variables),
            "variables": self.current_variables,
            "connected_clients": len(self.clients)
        }

    async def _collect_system_info(self, websocket):
        """Collect comprehensive system information from the guest VM."""
        from datetime import datetime, timezone

        collection_start = time.time()
        log.info("Starting system information collection...")

        try:
            system_info = {
                'os_info': {},
                'installed_packages': [],
                'package_manager': 'unknown'
            }

            # Detect platform
            guest_platform = platform.system().lower()
            system_info['guest_platform'] = guest_platform

            if guest_platform == 'windows':
                # Use Windows platform functions
                from adarevm.platforms.windows import get_os_info, get_installed_programs, get_windows_features, get_installed_updates

                # Execute in parallel to avoid blocking for long durations (20s+)
                try:
                    results = await asyncio.gather(
                        asyncio.to_thread(get_os_info),
                        asyncio.to_thread(get_installed_programs),
                        asyncio.to_thread(get_windows_features),
                        asyncio.to_thread(get_installed_updates),
                        return_exceptions=True
                    )

                    # Process results
                    system_info['os_info'] = results[0] if not isinstance(results[0], Exception) else {"error": str(results[0])}
                    system_info['installed_programs'] = results[1] if not isinstance(results[1], Exception) else []
                    system_info['windows_features'] = results[2] if not isinstance(results[2], Exception) else []
                    system_info['installed_updates'] = results[3] if not isinstance(results[3], Exception) else []

                    # Log exceptions if any
                    for i, res in enumerate(results):
                        if isinstance(res, Exception):
                            log.error(f"System info collection task {i} failed: {res}")

                except Exception as e:
                    log.error(f"Parallel system info collection failed: {e}")
                    # Fallback to sequential or partial
                    system_info['os_info'] = get_os_info()

            else:
                # Use Linux platform functions
                from adarevm.platforms.linux import get_os_info, detect_package_manager, get_installed_packages

                system_info['os_info'] = get_os_info()

                # Detect package manager and get packages
                package_manager = detect_package_manager()
                if package_manager:
                    system_info['package_manager'] = package_manager
                    system_info['installed_packages'] = get_installed_packages(package_manager)
                    log.info(f"Found {len(system_info['installed_packages'])} packages using {package_manager}")

            collection_time = time.time() - collection_start
            log.info(f"System information collection completed in {collection_time:.2f} seconds")

            # Send success event
            await self.send_event(websocket, EventType.LOG, {
                "message": f"System information collected successfully in {collection_time:.2f}s",
                "packages_found": len(system_info.get('installed_packages', [])),
                "os_detected": system_info['os_info'].get('name', 'Unknown')
            })

            return {
                "status": "success",
                "system_info": system_info,
                "collection_time": collection_time
            }

        except Exception as e:
            collection_time = time.time() - collection_start
            log.error(f"System information collection failed after {collection_time:.2f}s: {e}", exc_info=True)

            await self.send_event(websocket, EventType.ERROR, {
                "message": f"System information collection failed: {str(e)}",
                "collection_time": collection_time
            })

            return {
                "status": "error",
                "message": str(e),
                "collection_time": collection_time
            }

    async def _set_screenshot_method(self, websocket, use_maim: bool):
        """Set the screenshot method to use (maim or pyautogui)."""
        log.info(f"Setting screenshot method to: {'maim' if use_maim else 'pyautogui'}")
        try:
            from adarevm.automation.gui import set_screenshot_method
            set_screenshot_method(use_maim)

            await self.send_event(websocket, EventType.LOG, {
                "message": f"Screenshot method set to: {'maim' if use_maim else 'pyautogui'}"
            })

            return {
                "status": "success",
                "message": f"Screenshot method set to: {'maim' if use_maim else 'pyautogui'}",
                "use_maim": use_maim
            }
        except Exception as e:
            log.error(f"Failed to set screenshot method: {e}", exc_info=True)
            await self.send_event(websocket, EventType.ERROR, {
                "message": f"Failed to set screenshot method: {e}"
            })
            return {"status": "error", "message": str(e)}

    # ------------------------------------------------------------------ #
    # Command chaining
    # ------------------------------------------------------------------ #

    async def _chain_commands(self, websocket, commands: List[Dict[str, Any]]):
        """Execute multiple commands sequentially in a single request."""
        log.info(f"Chaining {len(commands)} commands")
        results = []

        for i, cmd in enumerate(commands):
            tool_name = cmd.get('tool')
            params = cmd.get('params', {})
            cmd_id = cmd.get('id', f"chain_{i}")

            log.debug(f"Chain[{i}]: {tool_name}")

            if tool_name not in self.tools:
                 results.append({
                     "id": cmd_id,
                     "status": "error",
                     "message": f"Unknown tool: {tool_name}"
                 })
                 continue

            try:
                # Execute tool
                tool_func = self.tools[tool_name]
                # Tools communicate via websocket events which is fine
                result = await tool_func(websocket, **params)

                # Add command ID to result for correlation
                if isinstance(result, dict) and 'id' not in result:
                    result['id'] = cmd_id

                results.append(result)

            except Exception as e:
                log.error(f"Chain command failed: {tool_name}: {e}", exc_info=True)
                results.append({
                    "id": cmd_id,
                    "status": "error",
                    "message": str(e)
                })

        return {
            "status": "success",
            "results": results,
            "count": len(results)
        }

    # ------------------------------------------------------------------ #
    # Timezone helpers
    # ------------------------------------------------------------------ #

    def _get_windows_timezone(self, utc_dt):
        """
        Get Windows timezone information using PowerShell.

        Args:
            utc_dt: datetime object in UTC timezone

        Returns:
            Tuple of (timezone_string, local_datetime) or (None, None) on failure
        """
        try:
            # Use PowerShell to get timezone offset
            import subprocess
            ps_command = "[System.TimeZoneInfo]::Local.GetUtcOffset((Get-Date)).ToString()"
            result = subprocess.run(
                ["powershell", "-Command", ps_command],
                capture_output=True,
                text=True,
                timeout=5.0
            )

            if result.returncode == 0:
                # Parse offset string (format: "HH:MM:SS" or "-HH:MM:SS")
                offset_str = result.stdout.strip()
                # Extract hours and minutes
                parts = offset_str.replace('-', '').split(':')
                if len(parts) >= 2:
                    hours = int(parts[0])
                    minutes = int(parts[1])
                    is_negative = offset_str.startswith('-')

                    # Create timezone offset
                    from datetime import timedelta, timezone
                    if is_negative:
                        tz_offset = timezone(timedelta(hours=-hours, minutes=-minutes))
                        tz_string = f"-{hours:02d}:{minutes:02d}"
                    else:
                        tz_offset = timezone(timedelta(hours=hours, minutes=minutes))
                        tz_string = f"+{hours:02d}:{minutes:02d}"

                    # Convert UTC to local time
                    local_dt = utc_dt.astimezone(tz_offset)
                    return tz_string, local_dt

        except (subprocess.SubprocessError, subprocess.TimeoutExpired, ValueError, OSError) as e:
            log.warning(f"Windows timezone detection failed: {e}")

        return None, None

    def _get_linux_timezone(self, utc_dt):
        """
        Get Linux timezone information using date command.

        Args:
            utc_dt: datetime object in UTC timezone

        Returns:
            Tuple of (timezone_string, local_datetime) or (None, None) on failure
        """
        try:
            # Use date command to get timezone offset
            import subprocess
            result = subprocess.run(
                ["date", "+%z"],
                capture_output=True,
                text=True,
                timeout=5.0
            )

            if result.returncode == 0:
                # Parse offset string (format: "+HHMM" or "-HHMM")
                offset_str = result.stdout.strip()
                if len(offset_str) == 5 and offset_str[0] in ['+', '-']:
                    sign = offset_str[0]
                    hours = int(offset_str[1:3])
                    minutes = int(offset_str[3:5])

                    # Create timezone offset
                    from datetime import timedelta, timezone
                    if sign == '-':
                        tz_offset = timezone(timedelta(hours=-hours, minutes=-minutes))
                        tz_string = f"-{hours:02d}:{minutes:02d}"
                    else:
                        tz_offset = timezone(timedelta(hours=hours, minutes=minutes))
                        tz_string = f"+{hours:02d}:{minutes:02d}"

                    # Convert UTC to local time
                    local_dt = utc_dt.astimezone(tz_offset)
                    return tz_string, local_dt

        except (subprocess.SubprocessError, subprocess.TimeoutExpired, ValueError, OSError) as e:
            log.warning(f"Linux timezone detection failed: {e}")

        return None, None

    # ------------------------------------------------------------------ #
    # Timestamp
    # ------------------------------------------------------------------ #

    async def _get_timestamp(self, websocket, use_local: bool = False):
        """
        Get timezone-aware timestamp from the VM.

        Args:
            websocket: WebSocket connection
            use_local: If True, detect and return VM's local timezone (default: False)

        Returns:
            Dict with timestamp data:
            {
                "timestamp": 1234567890.123456,  # Unix timestamp (UTC)
                "timezone": "UTC" or "+HH:MM",
                "iso_format": "2026-01-17T14:30:45.123456+00:00",
                "local_time": "2026-01-17T18:30:45.123456+04:00"  # only if use_local=True
            }
        """
        from datetime import datetime, timezone

        log.info(f"Getting timestamp (use_local={use_local})")

        try:
            await self.send_event(websocket, EventType.LOG, {
                "message": f"Retrieving VM timestamp (use_local={use_local})"
            })

            # Get current UTC time
            utc_dt = datetime.now(timezone.utc)
            unix_timestamp = utc_dt.timestamp()

            # Prepare response with UTC data
            response = {
                "timestamp": unix_timestamp,
                "timezone": "UTC",
                "iso_format": utc_dt.isoformat()
            }

            # Detect local timezone if requested
            if use_local:
                platform_name = platform.system().lower()
                tz_string = None
                local_dt = None

                if platform_name == 'windows':
                    tz_string, local_dt = self._get_windows_timezone(utc_dt)
                elif platform_name == 'linux':
                    tz_string, local_dt = self._get_linux_timezone(utc_dt)
                else:
                    log.warning(f"Timezone detection not supported on platform: {platform_name}")

                # Add local timezone data if detection succeeded
                if tz_string and local_dt:
                    response["timezone"] = tz_string
                    response["local_time"] = local_dt.isoformat()
                    log.info(f"Detected local timezone: {tz_string}")
                else:
                    # Fallback to UTC if detection failed
                    log.warning("Local timezone detection failed, falling back to UTC")
                    await self.send_event(websocket, EventType.LOG, {
                        "message": "Local timezone detection failed, using UTC"
                    })

            log.info(f"Timestamp retrieved: {response}")

            await self.send_event(websocket, EventType.LOG, {
                "message": f"Timestamp retrieved successfully (timezone: {response['timezone']})"
            })

            return response

        except Exception as e:
            log.error(f"Failed to get timestamp: {e}", exc_info=True)
            await self.send_event(websocket, EventType.ERROR, {
                "message": f"Timestamp retrieval failed: {e}"
            })
            return {"status": "error", "message": str(e)}
