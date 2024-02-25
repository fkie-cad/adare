# internal imports
from adarelib.exceptions import LoggedException, LoggedErrorException


class ExperimentFileCreationError(LoggedErrorException):
    pass


class ExperimentDirectoryCreationError(LoggedErrorException):
    pass


class ExperimentRemovalError(LoggedErrorException):
    pass


class ExperimentDirectoryAlreadyExistsError(LoggedErrorException):
    pass


class ExperimentDirectoryDoesNotExistError(LoggedErrorException):
    pass
