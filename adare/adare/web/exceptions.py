from adare.exceptions import LoggedException, LoggedErrorException


class LoginFailedError(LoggedErrorException):
    pass


class AlreadyLoggedIn(LoggedErrorException):
    pass


class NoUserLoggedIn(LoggedErrorException):
    pass
