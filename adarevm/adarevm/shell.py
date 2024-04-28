from pathlib import Path
from subprocess import Popen, PIPE

from adarelib.types.event import CommandEvent
from adarelib.event import EventSystem

import logging
log = logging.getLogger(__name__)


def execute_on_shell(command: list, cwd: Path = None, event_system: EventSystem = None) -> dict:
    """
    executes a shell command
    :param command: list of command and arguments
    :param cwd: current working directory where the command should be executed
    :param event_system: event system to log the command execution
    :return:
    """
    command_str = " ".join(command)
    if event_system:
        event_system.log(
            CommandEvent(
                name=command[0], command=command_str, status="running"
            )
        )
    if cwd:
        proc = Popen(command, stdout=PIPE, stderr=PIPE, cwd=cwd)
    else:
        proc = Popen(command, stdout=PIPE, stderr=PIPE)
    stdout, stderr = proc.communicate()

    stdout = stdout.decode("utf-8")
    stdout = stdout.replace("\r", "")
    stdout = stdout.split("\n")
    for line in stdout:
        log.debug(line)
    stderr = stderr.decode("utf-8")
    stderr = stderr.replace("\r", "")
    stderr = stderr.split("\n")
    ret = {
        'returncode': proc.returncode,
        'stdout': stdout,
        'stderr': stderr
    }
    log.debug(
        f"'{command_str}' exited with return code: " + str(ret['returncode'])
    )
    if ret['returncode'] != 0:
        log.error(
            f"{command_str} exited with an error (return code "
            + str(ret['returncode'])
            + ")"
        )
        for line in stderr:
            log.error(line)
    if event_system:
        status = 'success' if ret['returncode'] == 0 else 'failed'
        event_system.log(
            CommandEvent(
                name=command[0], command=command_str, status=status, returncode=ret['returncode'], stdout=" ".join(ret['stdout']),
                error=" ".join(ret['stderr'])
            )
        )
    return ret
