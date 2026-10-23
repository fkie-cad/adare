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


class EnvironmentDiskChanged(LoggedErrorException):
    """The registered disk no longer has the bytes this environment version was loaded with."""
