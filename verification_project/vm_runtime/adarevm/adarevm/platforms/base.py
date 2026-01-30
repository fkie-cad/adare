"""
Base interface for platform-specific operations.
"""

from abc import ABC, abstractmethod
from typing import List, Dict, Any, Optional


class Window:
    """Represents a window with position and metadata."""
    def __init__(self, id: str, name: str, rect: tuple, pid: int = None):
        self.id = id
        self.name = name 
        self.rect = rect  # (x, y, width, height)
        self.pid = pid


class BasePlatform(ABC):
    """Base class for platform-specific window and GUI operations."""
    
    @abstractmethod
    def get_windows_by_search_string(self, search_string: str) -> List[Window]:
        """Get windows matching the search string."""
        pass
    
    @abstractmethod
    def get_window_info(self, window_id: str) -> Optional[Dict[str, Any]]:
        """Get detailed information about a specific window."""
        pass
    
    @abstractmethod
    def is_window_visible(self, window: Window) -> bool:
        """Check if a window is visible/not occluded."""
        pass