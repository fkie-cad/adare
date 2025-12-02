from adare.exceptions import LoggedErrorException


class NotLoggedInError(LoggedErrorException):
    """
    Exception for not being logged in
    """
    def __init__(self, log, message: str, possible_solutions: list = None):
        super().__init__(log, message, possible_solutions)


class ExperimentWithNameAlreadyExistsError(LoggedErrorException):
    """
    Exception for an experiment with the same name already existing
    """
    def __init__(self, log, message: str, possible_solutions: list = None):
        super().__init__(log, message, possible_solutions)


class DownloadError(LoggedErrorException):
    """
    Exception for an error during download
    """
    def __init__(self, log, message: str, possible_solutions: list = None):
        super().__init__(log, message, possible_solutions)


class MissingDataError(LoggedErrorException):
    """
    Exception for missing data
    """
    def __init__(self, log, message: str, possible_solutions: list = None):
        super().__init__(log, message, possible_solutions)


class ExperimentPublishFailedError(LoggedErrorException):
    def __init__(self, log, message: str, possible_solutions: list = None):
        super().__init__(log, message, possible_solutions)


class ExperimentNotFoundError(LoggedErrorException):
    """
    Exception for experiment not found on server
    """
    def __init__(self, log, message: str, possible_solutions: list = None):
        super().__init__(log, message, possible_solutions)


class RunAlreadyExistsError(LoggedErrorException):
    """
    Exception for experiment run already existing on server
    """
    def __init__(self, log, message: str, possible_solutions: list = None):
        super().__init__(log, message, possible_solutions)


class PublishPermissionError(LoggedErrorException):
    """
    Exception for lacking permission to publish
    """
    def __init__(self, log, message: str, possible_solutions: list = None):
        super().__init__(log, message, possible_solutions)


class ApiValidationError(LoggedErrorException):
    """
    Exception for server-side validation failures
    """
    def __init__(self, log, message: str, possible_solutions: list = None):
        super().__init__(log, message, possible_solutions)


class ApiConnectionError(LoggedErrorException):
    """
    Exception for network/server connectivity issues
    """
    def __init__(self, log, message: str, possible_solutions: list = None):
        super().__init__(log, message, possible_solutions)
