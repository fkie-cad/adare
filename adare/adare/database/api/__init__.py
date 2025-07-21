"""
Enhanced Database API module for ADARE.

This module provides comprehensive database access with improved error handling,
validation, and ULID support. It includes specialized APIs for different
domain areas and a unified base class.
"""

from .base import EnhancedDatabaseApi
from .sync_metadata import SyncMetadataApi
from .tag import TagApi

# Import existing APIs for backward compatibility
from .database import DatabaseApi
from .project import ProjectDbApi
from .environment import EnvironmentDbApi
from .experiment import ExperimentApi
from .event import EventDbApi
from .stage import StageDbApi
from .usersession import UserSessionApi
from .frontend import DataRetrievalApi
from .testfunction import TestfunctionDbApi

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