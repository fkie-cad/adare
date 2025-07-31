"""
ADARE types module.

This module contains all type definitions for ADARE application-specific functionality.
Types that were previously in adarelib.types have been moved here.
"""

# Environment types
from .environment import (
    EnvironmentMetadata,
    OsInfo, 
    PostsetupInstallations,
    parse_environment_file
)

# Backend/Infrastructure types
from .backend import (
    UsbDevice,
    CopyData,
    DownloadData,
    Disk,
    Share,
    NetworkdriveVMConfiguration,
    NFSShare,
    NFSConfiguration,
    SMBUser,
    SMBShare,
    SMBConfiguration,
    NetworkdriveMountData,
)

# Experiment types
from .experiment import (
    ExperimentMetadata,
)

# Playbook/Action types
from .playbook import (
    Config,
    Settings,
    Target,
    ActionType,
    ClickAction,
    RightClickAction,
    DoubleClickAction,
    DragAction,
    KeyboardAction,
    IdleAction,
    ScrollAction,
    GotoAction,
    ActionTestAction,
    CommandAction,
    BlockAction,
    ExistsCondition,
    NotExistsCondition,
    parse_playbook,
)

from .stages import *

__all__ = [
    # Environment types
    'EnvironmentMetadata',
    'OsInfo',
    'PostsetupInstallations', 
    'parse_environment_file',
    
    # Backend types
    'UsbDevice',
    'CopyData',
    'DownloadData', 
    'Disk',
    'Share',
    'NetworkdriveVMConfiguration',
    'NFSShare',
    'NFSConfiguration',
    'SMBUser',
    'SMBShare',
    'SMBConfiguration',
    'NetworkdriveMountData',
    
    # Experiment types
    'ExperimentMetadata',
    
    # Playbook types
    'Config',
    'Settings',
    'Target',
    'ActionType',
    'ClickAction',
    'RightClickAction',
    'DoubleClickAction',
    'DragAction',
    'KeyboardAction',
    'IdleAction', 
    'ScrollAction',
    'GotoAction',
    'ActionTestAction',
    'CommandAction',
    'BlockAction',
    'ExistsCondition',
    'NotExistsCondition',
    'parse_playbook',
]