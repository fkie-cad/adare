from adarelib.types.ws import EXEC, DONE
from adarevm.msghandler.strategies.base_handler import MessageStrategy
from adarevm.shell import execute_on_shell
from subprocess import CalledProcessError
from typing import Callable, Awaitable

from pathlib import Path

import logging
log = logging.getLogger(__name__)

class ExecHandler(MessageStrategy):

    def handle(self, command_type, command: EXEC, send_callback: Callable[[str], Awaitable[None]]):
        log.info(f"Handling EXEC command: {command.command}")
        try:
            if command.cwd:
                ret = execute_on_shell(command.command.split(' '), shell=command.shell, cwd=Path(command.cwd))
            else:
                ret = execute_on_shell(command.command.split(' '), shell=command.shell)
            error = True if ret['returncode'] != 0 else False
            err_msg = ret['stderr']
            out_msg = ret['stdout']
        except (CalledProcessError, WindowsError, FileNotFoundError) as e:
            error = True
            err_msg = f'Command failed to execute with error: {e}'
            out_msg = ''

        done_msg = DONE(name=command.command, error=error, out_msg=out_msg, err_msg=err_msg)
        send_callback(done_msg.encode())
        log.info(f"EXEC command handled: {command.command}")








