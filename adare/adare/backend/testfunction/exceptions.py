# internal imports
from adarelib.exceptions import LoggedException, LoggedErrorException


class TestfunctionDirectoryCreationError(LoggedErrorException):
    pass


class TestfunctionCreationError(LoggedErrorException):
    pass