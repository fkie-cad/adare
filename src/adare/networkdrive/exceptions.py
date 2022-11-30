# internal imports
from adare.exception_baseclasses import ClassCreationError

# configure logging
import logging
log = logging.getLogger(__name__)


class NetworkdriveCreationError(ClassCreationError):
    def __init__(self):
        self.message = 'the network drive vm could not be created successfully'
        super().__init__(self.message)
