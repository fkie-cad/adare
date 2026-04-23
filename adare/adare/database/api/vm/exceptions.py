"""
VM database API exceptions.

Custom exceptions for VM-related database operations.
"""

from adare.exceptions import LoggedErrorException


class VMNotFoundError(LoggedErrorException):
    """VM not found in database or filesystem."""
    pass


class VMValidationError(LoggedErrorException):
    """VM validation failed."""
    pass


class VMLoadError(LoggedErrorException):
    """Failed to load VM into database."""
    pass


class VMNameConflictError(LoggedErrorException):
    """VM name already exists in database."""
    pass
