from adarelib.types.ws import ECHO, ECHOREPLY
from adarevm.msghandler.strategies.base_handler import MessageStrategy


import logging
log = logging.getLogger(__name__)

class EchoHandler(MessageStrategy):

 def handle(self, command_type, command: ECHO, send_callback):
        log.info(f"Handling ECHO")
        reply = ECHOREPLY(data=command.data)
        send_callback(reply)
        log.info(f"Sending ECHOREPLY")