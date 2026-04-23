# internal imports
from adare.exceptions import LoggedErrorException


class TestfunctionDirectoryCreationError(LoggedErrorException):
    pass


class TestfunctionCreationError(LoggedErrorException):
    pass


class TestfunctionRemovalError(LoggedErrorException):
    pass


class TestfunctionMissingFileError(LoggedErrorException):
    pass


class TestfunctionUpdatedError(LoggedErrorException):
    pass
