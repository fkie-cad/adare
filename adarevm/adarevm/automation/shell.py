from pathlib import Path
from subprocess import Popen, PIPE, TimeoutExpired
import subprocess
import platform

import logging

log = logging.getLogger(__name__)


def execute_on_shell(command, cwd: Path = None, shell: bool = False, powershell: bool = True, env: dict = None, timeout: float = None, inherit_env: bool = True, admin: bool = False, background: bool = False) -> dict:
    """
    Executes a shell command.
    :param command: List of command and arguments, or string when shell=True.
    :param cwd: Current working directory where the command should be executed.
    :param shell: If True, execute in shell (Cmd.exe on Windows, default shell on Unix).
    :param powershell: If True, execute in powershell instead of cmd.exe. (Windows only)
    :param env: Dictionary of environment variables to set for the command.
    :param timeout: Timeout in seconds for the command execution.
    :param inherit_env: If True, inherit system environment variables (default: True).
    :param admin: If True, run with elevated privileges (Windows: RunAs, Linux: sudo).
    :param background: If True, don't wait for command completion (returns immediately with PID).
    :return: Dictionary containing return code, stdout, and stderr.
    """
    is_windows = platform.system().lower() == "windows"

    # Warn if background + timeout specified
    if background and timeout:
        log.warning("background=True specified with timeout - timeout will be ignored for background processes")

    # Handle both string and list commands
    if isinstance(command, str):
        command_str = command
    else:
        command_str = " ".join(command)

    # Handle admin mode - prepend sudo on Linux or wrap with Start-Process on Windows
    if admin:
        if is_windows:
            # Use Start-Process with RunAs for elevation
            # Note: -Wait ensures we wait for completion, works with our script block approach
            admin_wrapped = f"Start-Process powershell -ArgumentList '-NoProfile','-ExecutionPolicy','Bypass','-Command',''& {{ {command_str} }}''' -Verb RunAs -Wait -WindowStyle Hidden"
            command_str = admin_wrapped
            log.info(f"Running command with elevated privileges (Windows RunAs)")
        else:
            # Use sudo on Linux
            command_str = f"sudo {command_str}"
            log.info(f"Running command with elevated privileges (sudo)")

    # Handle shell mode - wrap in PowerShell or cmd.exe
    if shell and is_windows and powershell:
        # Wrap in script block for synchronous execution and proper file I/O flushing
        wrapped_cmd = f"& {{ {command_str} }}"
        command = ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", wrapped_cmd]
    elif isinstance(command, list):
        command = command
    else:
        # Keep as string for Unix shell=True
        command = command_str

    # Log command execution details
    log.info(f"Executing command: {command_str}")
    log.debug(f"Command details - cwd: {cwd}, shell: {shell}, timeout: {timeout}, inherit_env: {inherit_env}")
    if env:
        log.debug(f"Custom environment variables: {list(env.keys()) if env else 'None'}")

    # Prepare environment variables
    import os
    process_env = None
    if inherit_env:
        process_env = os.environ.copy()
        if env:
            process_env.update(env)
    elif env:
        process_env = env

    # Start process with detailed logging
    import time
    start_time = time.time()
    log.debug(f"Starting process at {start_time}")
    
    if cwd:
        proc = Popen(command, stdout=PIPE, stderr=PIPE, cwd=cwd, shell=shell, env=process_env)
    else:
        proc = Popen(command, stdout=PIPE, stderr=PIPE, shell=shell, env=process_env)
    
    log.debug(f"Process started with PID: {proc.pid}")

    # Handle background mode - return immediately without waiting
    if background:
        log.info(f"Background mode enabled - checking if process started successfully (PID: {proc.pid})")

        # Quick non-blocking check if process failed immediately (100ms grace period)
        time.sleep(0.1)
        poll_result = proc.poll()

        if poll_result is not None:
            # Process already exited! This means it failed immediately
            stdout, stderr = proc.communicate()
            stdout_str = stdout.decode("utf-8").replace("\r", "") if stdout else ""
            stderr_str = stderr.decode("utf-8").replace("\r", "") if stderr else ""

            log.error(f"Background process {proc.pid} failed immediately with return code {poll_result}")
            log.error(f"stdout: {stdout_str}")
            log.error(f"stderr: {stderr_str}")

            return {
                'returncode': poll_result,
                'stdout': stdout_str,
                'stderr': stderr_str,
                'pid': proc.pid,
                'background': False  # Failed to start, not actually running in background
            }

        # Process still running after grace period - it started successfully
        log.info(f"Background process {proc.pid} started successfully")
        return {
            'returncode': None,  # Process still running
            'stdout': '',
            'stderr': '',
            'pid': proc.pid,
            'background': True
        }

    # Normal mode - wait for completion
    try:
        log.debug(f"Waiting for process {proc.pid} to complete (timeout: {timeout})")
        stdout, stderr = proc.communicate(timeout=timeout)
        execution_time = time.time() - start_time
        log.debug(f"Process {proc.pid} completed in {execution_time:.2f} seconds")
    except TimeoutExpired:
        execution_time = time.time() - start_time
        log.error(f"Command timed out after {timeout} seconds (actual time: {execution_time:.2f}s)")
        log.warning(f"Killing process {proc.pid} due to timeout")
        proc.kill()
        stdout, stderr = proc.communicate()
        log.debug(f"Process {proc.pid} killed and cleaned up")
        return {
            'returncode': -1,
            'stdout': stdout.decode("utf-8").replace("\r", "") if stdout else "",
            'stderr': f"Command timed out after {timeout} seconds (killed at {execution_time:.2f}s)\n" + (stderr.decode("utf-8").replace("\r", "") if stderr else "")
        }

    stdout = stdout.decode("utf-8").replace("\r", "")
    stderr = stderr.decode("utf-8").replace("\r", "")

    # Always log stdout (even if empty)
    log.info(f"stdout: {stdout if stdout else ''}")
    
    # Always log stderr (even if empty)  
    log.info(f"stderr: {stderr if stderr else ''}")

    ret = {
        'returncode': proc.returncode,
        'stdout': stdout,
        'stderr': stderr
    }

    execution_time = time.time() - start_time
    log.info(f"'{command_str}' exited with return code: {ret['returncode']} (execution time: {execution_time:.2f}s)")

    if ret['returncode'] != 0:
        log.error(f"{command_str} exited with an error (return code {ret['returncode']})")

    return ret
