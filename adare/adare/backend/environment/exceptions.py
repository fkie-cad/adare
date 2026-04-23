# internal imports
from adare.exceptions import LoggedErrorException


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


