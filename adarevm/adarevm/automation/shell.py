from pathlib import Path
from subprocess import Popen, PIPE, TimeoutExpired
import subprocess
import platform

import logging

log = logging.getLogger(__name__)


def execute_on_shell(command, cwd: Path = None, shell: bool = False, powershell: bool = True, env: dict = None, timeout: float = None, inherit_env: bool = True) -> dict:
    """
    Executes a shell command.
    :param command: List of command and arguments, or string when shell=True.
    :param cwd: Current working directory where the command should be executed.
    :param shell: If True, execute in shell (Cmd.exe on Windows, default shell on Unix).
    :param powershell: If True, execute in powershell instead of cmd.exe. (Windows only)
    :param env: Dictionary of environment variables to set for the command.
    :param timeout: Timeout in seconds for the command execution.
    :param inherit_env: If True, inherit system environment variables (default: True).
    :return: Dictionary containing return code, stdout, and stderr.
    """
    is_windows = platform.system().lower() == "windows"

    # Handle both string and list commands
    if isinstance(command, str):
        command_str = command
        if shell and is_windows and powershell:
            command = ["powershell", "-Command", command_str]
        # For shell=True on Unix or when not using powershell, keep as string
    else:
        command_str = " ".join(command)
        if shell and is_windows and powershell:
            command = ["powershell", "-Command", command_str]

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
