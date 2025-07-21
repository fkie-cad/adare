from adarelib.types.ws import WsCommand

class MessageStrategy:
    def handle(self, command_type, command: WsCommand, send_callback):
        raise NotImplementedError