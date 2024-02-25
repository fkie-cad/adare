# internal imports
from adarelib.exceptions import LoggedException, LoggedErrorException


class DatabaseProjectCreationError(LoggedErrorException):
    pass



class TokenExpired(LoggedErrorException):
    pass