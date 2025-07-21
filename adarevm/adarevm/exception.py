import logging

class LoggedException(Exception):
    def __init__(self, log: logging.Logger, message: str, level: str = 'info'):
        self.log = log
        if level == 'critical':
            self.log.critical(message)
        elif level == 'debug':
            self.log.debug(message)
        elif level == 'error':
            self.log.error(message)
        elif level == 'info':
            self.log.info(message)
        elif level == 'warning':
            self.log.warning(message)
        super().__init__(message)


class LoggedErrorException(LoggedException):
    def __init__(self, log: logging.Logger, message: str):
        super().__init__(log, message, level='error')
        self.log = log
        self.message = message

    def __str__(self):
        return f"LoggedErrorException: {self.message}"