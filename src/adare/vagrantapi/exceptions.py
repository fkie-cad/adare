# internal imports
from adare.exception_baseclasses import LoggedException, ClassCreationError

# configure logging
import logging
log = logging.getLogger(__name__)


class VagrantFileCreationError(ClassCreationError):
    def __init__(self, reason: str):
        super().__init__(reason)


class VagrantBoxCreationError(ClassCreationError):
    def __init__(self, reason: str):
        super().__init__(reason)


class VagrantFileWriteError(LoggedException):
    def __init__(self, reason: str):
        super().__init__(reason)


class VagrantBoxDestroyError(LoggedException):
    def __init__(self, reason: str = ''):
        super().__init__(reason)
