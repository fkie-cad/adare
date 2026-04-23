# internal imports
from adare.exceptions import LoggedErrorException, LoggedException


class ProjectMissingInDatabaseError(LoggedErrorException):
    pass


class ProjectDirectoryCreationError(LoggedErrorException):
    pass


class ProjectDirectoryRemovalError(LoggedErrorException):
    pass


class ProjectDirectoryCopyError(LoggedErrorException):
    pass


class ProjectDirectoryMissingError(LoggedErrorException):
    pass


class NoProjectsFoundMessage(LoggedException):
    pass
