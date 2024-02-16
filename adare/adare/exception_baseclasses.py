# configure logging
import logging
log = logging.getLogger(__name__)


class LoggedException(Exception):
    def __init__(self, message, critical=False):
        self.message = message
        if critical:
            log.critical(self.message)
        else:
            log.error(self.message)
        super().__init__(self.message)


class ClassCreationError(LoggedException):
    def __init__(self, message):
        self.message = message
        super().__init__(self.message)
