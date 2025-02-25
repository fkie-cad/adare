class MessageHandler:

    def handle_message(self, command_type, message, send_callback):
        """Handles incoming messages."""
        raise NotImplementedError