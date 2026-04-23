from adare.exceptions import LoggedErrorException


class LoginFailedError(LoggedErrorException):
    pass


class AlreadyLoggedIn(LoggedErrorException):
    pass


class NoUserLoggedIn(LoggedErrorException):
    pass
