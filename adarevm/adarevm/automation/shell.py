from pathlib import Path
from subprocess import Popen, PIPE, TimeoutExpired
import subprocess
import platform

import logging

log = logging.getLogger(__name__)


def execute_on_shell(command: list, cwd: Path = None, shell: bool = False, powershell: bool = True, env: dict = None, timeout: float = None) -> dict:
    """
    Executes a shell command.
    :param command: List of command and arguments.
    :param cwd: Current working directory where the command should be executed.
    :param shell: If True, execute in shell (Cmd.exe on Windows, default shell on Unix).
    :param powershell: If True, execute in powershell instead of cmd.exe. (Windows only)
    :param env: Dictionary of environment variables to set for the command.
    :param timeout: Timeout in seconds for the command execution.
    :return: Dictionary containing return code, stdout, and stderr.
    """
    is_windows = platform.system().lower() == "windows"

    if shell and is_windows and powershell:
        command_str = " ".join(command)
        command = ["powershell", "-Command", command_str]
    else:
        command_str = " ".join(command)

    # Prepare environment variables
    process_env = None
    if env:
        import os
        process_env = os.environ.copy()
        process_env.update(env)

    if cwd:
        proc = Popen(command, stdout=PIPE, stderr=PIPE, cwd=cwd, shell=shell, env=process_env)
    else:
        proc = Popen(command, stdout=PIPE, stderr=PIPE, shell=shell, env=process_env)

    try:
        stdout, stderr = proc.communicate(timeout=timeout)
    except TimeoutExpired:
        proc.kill()
        stdout, stderr = proc.communicate()
        return {
            'returncode': -1,
            'stdout': stdout.decode("utf-8").replace("\r", "") if stdout else "",
            'stderr': f"Command timed out after {timeout} seconds\n" + (stderr.decode("utf-8").replace("\r", "") if stderr else "")
        }

    stdout = stdout.decode("utf-8").replace("\r", "")
    stderr = stderr.decode("utf-8").replace("\r", "")

    for line in stdout.split("\n"):
        log.debug(line)

    ret = {
        'returncode': proc.returncode,
        'stdout': stdout,
        'stderr': stderr
    }

    log.debug(f"'{command_str}' exited with return code: {ret['returncode']}")

    if ret['returncode'] != 0:
        log.error(f"{command_str} exited with an error (return code {ret['returncode']})")
        for line in stderr.split("\n"):
            log.error(line)

    return ret
