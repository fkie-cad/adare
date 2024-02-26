# internal imports
from adarelib.exceptions import LoggedException, LoggedErrorException


class EnvironmentLoadFailed(LoggedErrorException):
    pass


class EnvironmentFileAlreadyExists(LoggedErrorException):
    pass