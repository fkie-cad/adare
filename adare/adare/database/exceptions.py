# internal imports
from adarelib.exceptions import LoggedException, LoggedErrorException


class DatabaseProjectCreationError(LoggedErrorException):
    pass


class TokenExpired(LoggedErrorException):
    pass


class DatabaseTestfunctionCreationError(LoggedErrorException):
    pass


class DatabaseTestfunctionRemovalError(LoggedErrorException):
    pass


class DatabaseTestfunctionUpdateError(LoggedErrorException):
    pass


class DatabaseTestValidationError(LoggedErrorException):
    pass