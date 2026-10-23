"""
Enhanced Database API module for ADARE.

This module provides comprehensive database access with improved error handling,
validation, and ULID support. It includes specialized APIs for different
domain areas and a unified base class.
"""

from typing import TYPE_CHECKING

from .base import EnhancedDatabaseApi

# Import existing APIs for backward compatibility
from .environment import EnvironmentDbApi
from .event import EventDbApi
from .experiment import ExperimentApi
from .project import ProjectDbApi
from .stage import StageDbApi
from .sync_metadata import SyncMetadataApi
from .tag import TagApi
from .testfunction import TestfunctionDbApi
from .usersession import UserSessionApi

if TYPE_CHECKING:
    from .frontend import DataRetrievalApi

__all__ = [
    # Enhanced APIs
    'EnhancedDatabaseApi',
    'SyncMetadataApi',
    'TagApi',
    # Existing APIs
    'ProjectDbApi',
    'EnvironmentDbApi',
    'ExperimentApi',
    'EventDbApi',
    'StageDbApi',
    'UserSessionApi',
    'DataRetrievalApi',
    'TestfunctionDbApi',
]


def __getattr__(name: str):
    # DataRetrievalApi pulls in pandas (~130 ms); load it only when asked for so
    # every other DB-touching command doesn't pay for it at import time.
    if name == 'DataRetrievalApi':
        from .frontend import DataRetrievalApi

        return DataRetrievalApi
    raise AttributeError(f'module {__name__!r} has no attribute {name!r}')
