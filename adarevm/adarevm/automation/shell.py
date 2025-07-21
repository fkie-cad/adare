from pathlib import Path
from subprocess import Popen, PIPE
import platform

import logging

log = logging.getLogger(__name__)


def execute_on_shell(command: list, cwd: Path = None, shell: bool = False, powershell: bool = True) -> dict:
    """
    Executes a shell command.
    :param command: List of command and arguments.
    :param cwd: Current working directory where the command should be executed.
    :param shell: If True, execute in shell (Cmd.exe on Windows, default shell on Unix).
    :param powershell: If True, execute in powershell instead of cmd.exe. (Windows only)
    :return: Dictionary containing return code, stdout, and stderr.
    """
    is_windows = platform.system().lower() == "windows"

    if shell and is_windows and powershell:
        command_str = " ".join(command)
        command = ["powershell", "-Command", command_str]
    else:
        command_str = " ".join(command)

    if cwd:
        proc = Popen(command, stdout=PIPE, stderr=PIPE, cwd=cwd, shell=shell)
    else:
        proc = Popen(command, stdout=PIPE, stderr=PIPE, shell=shell)

    stdout, stderr = proc.communicate()

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
