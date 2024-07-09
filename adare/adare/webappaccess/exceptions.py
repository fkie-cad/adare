from adarelib.exceptions import LoggedErrorException


class NotLoggedInError(LoggedErrorException):
    """
    Exception for not being logged in
    """
    def __init__(self, log, message: str, possible_solutions: list = None):
        super().__init__(log, message, possible_solutions)
