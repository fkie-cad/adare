from adarelib.exceptions import LoggedErrorException, LoggedException

# configure logging
import logging
log = logging.getLogger(__name__)


class VagrantFileCreationError(Exception):
    def __init__(self, reason: str):
        super().__init__(reason)


class VagrantBoxCreationError(Exception):
    def __init__(self, reason: str):
        super().__init__(reason)


class VagrantFileWriteError(Exception):
    def __init__(self, reason: str):
        super().__init__(reason)


class VagrantBoxDestroyError(LoggedErrorException):
    pass


class VagrantBoxRunError(LoggedErrorException):
    pass
