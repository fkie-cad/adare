# internal imports
from adare.exceptions import LoggedException, LoggedErrorException
import logging


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


class ExperimentCommandError(LoggedErrorException):
    def __init__(self, log: logging.Logger, command: str, exit_code: int, stdout: str = '', stderr: str = ''):
        msg = f'Command "{command}" failed with exit code {exit_code}.\nstdout: {stdout}\nstderr: {stderr}'
        super().__init__(log, msg)