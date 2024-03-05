# internal imports
from adarelib.exceptions import LoggedException, LoggedErrorException


class EnvironmentLoadFailed(LoggedErrorException):
    pass


class EnvironmentFileAlreadyExists(LoggedErrorException):
    pass


class EnvironmentDeletionError(LoggedErrorException):
    pass


class EnvironmentUpdateError(LoggedErrorException):
    pass


class EnvironmentDoesNotExistInDatabase(LoggedErrorException):
    pass


class EnvironmentAlreadyExists(LoggedErrorException):
    pass
