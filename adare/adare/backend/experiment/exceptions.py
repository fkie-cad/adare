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


class ExperimentFileMissingError(LoggedErrorException):
    pass


class VagrantBoxMissingError(LoggedErrorException):
    pass


class ExperimentIntegrityError(LoggedErrorException):
    pass


class EnvironmentIntegrityError(LoggedErrorException):
    pass


class TestfunctionIntegrityError(LoggedErrorException):
    pass


class NoEnvironmentError(LoggedErrorException):
    pass


class MultipleEnvironmentsError(LoggedErrorException):
    pass


class ExperimentAlreadyExistsError(LoggedErrorException):
    pass


class ExperimentNotChanged(LoggedException):
    pass
