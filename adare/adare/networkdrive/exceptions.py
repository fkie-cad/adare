# internal imports
# configure logging
import logging

from adare.exception_baseclasses import ClassCreationError

log = logging.getLogger(__name__)


class NetworkdriveCreationError(ClassCreationError):
    def __init__(self):
        self.message = 'the network drive vm could not be created successfully'
        super().__init__(self.message)
