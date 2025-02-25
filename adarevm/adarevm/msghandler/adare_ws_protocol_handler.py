from adarelib.types.ws import LOG, EXEC, EVENT, WsCommand, ECHO, EXPERIMENT
from adarevm.msghandler.strategies.base_handler import MessageStrategy
from adarevm.msghandler.strategies.exec_handler import ExecHandler
from adarevm.msghandler.strategies.echo_handler import EchoHandler
from adarevm.msghandler.strategies.experiment_handler import ExperimentHandler
from adarevm.msghandler.msg_handler import MessageHandler

import logging
log = logging.getLogger(__name__)


class AdareWsProtocolHandler(MessageHandler):
    def __init__(self):
        super().__init__()
        self.handlers = {
            EXEC.command_type: ExecHandler(),
            ECHO.command_type: EchoHandler(),
            EXPERIMENT.command_type: ExperimentHandler()
        }

    def handle_message(self, command_type, message, send_callback):
        log.info(f"Handling message: {message}")
        ws_command = WsCommand.decode(message)
        handler: MessageStrategy = self.handlers.get(ws_command.command_type)

        if handler:
            handler.handle(command_type, ws_command, send_callback)
        else:
            log.warning(f"No handler found for command type: {ws_command.command_type}")

