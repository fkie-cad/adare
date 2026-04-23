"""
Enhanced Database API module for ADARE.

This module provides comprehensive database access with improved error handling,
validation, and ULID support. It includes specialized APIs for different
domain areas and a unified base class.
"""

from .base import EnhancedDatabaseApi

# Import existing APIs for backward compatibility
from .database import DatabaseApi
from .environment import EnvironmentDbApi
from .event import EventDbApi
from .experiment import ExperimentApi
from .frontend import DataRetrievalApi
from .project import ProjectDbApi
from .stage import StageDbApi
from .sync_metadata import SyncMetadataApi
from .tag import TagApi
from .testfunction import TestfunctionDbApi
from .usersession import UserSessionApi

__all__ = [
    # Enhanced APIs
    'EnhancedDatabaseApi',
    'SyncMetadataApi',
    'TagApi',

    # Existing APIs
    'DatabaseApi',
    'ProjectDbApi',
    'EnvironmentDbApi',
    'ExperimentApi',
    'EventDbApi',
    'StageDbApi',
    'UserSessionApi',
    'DataRetrievalApi',
    'TestfunctionDbApi',
]
