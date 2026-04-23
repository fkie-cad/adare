# internal imports
from adare.exceptions import LoggedErrorException


class DatabaseProjectCreationError(LoggedErrorException):
    pass


class TokenExpired(LoggedErrorException):
    pass


class DatabaseTestfunctionCreationError(LoggedErrorException):
    pass


class DatabaseTestfunctionRemovalError(LoggedErrorException):
    pass


class DatabaseTestfunctionUpdateError(LoggedErrorException):
    pass


class DatabaseTestValidationError(LoggedErrorException):
    pass


class DatabaseProjectNotFoundError(LoggedErrorException):
    pass


class EnvironmentMissingError(LoggedErrorException):
    pass


# New enhanced exception classes for improved database API
class DatabaseError(LoggedErrorException):
    """Base class for database-related errors."""
    pass


class DatabaseConnectionError(DatabaseError):
    """Error connecting to or initializing database."""
    pass


class EntityNotFoundError(DatabaseError):
    """Entity not found in database."""
    pass


class ValidationError(DatabaseError):
    """Input validation error."""
    pass


class SyncError(DatabaseError):
    """Synchronization-related error."""
    pass
