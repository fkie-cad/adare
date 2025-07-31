"""
Target Resolution Module using existing MCP GUI Server.

This module provides target resolution by leveraging the existing MCP GUI server
for CV/OCR capabilities (find_icon and find_text tools).
"""

import logging
from pathlib import Path
from typing import Tuple, Optional, List
from dataclasses import dataclass
import json
import base64

from fastmcp import Client
from adare.types.playbook import Target

log = logging.getLogger(__name__)


@dataclass
class TargetMatch:
    """Represents a found target with confidence and location."""
    coordinates: Tuple[int, int]
    confidence: float
    method: str  # 'image', 'text', 'position'
    region: Optional[Tuple[int, int, int, int]] = None  # x, y, width, height


class MCPTargetResolver:
    """
    Target resolver using existing MCP GUI server for CV/OCR.
    
    This class connects to your existing mcp_gui.py server to perform
    image recognition and text detection for target resolution.
    """
    
    def __init__(self, experiment_dir: Path, mcp_gui_url: str = "http://localhost:13109/mcp"):
        """
        Initialize MCP target resolver.
        
        Args:
            experiment_dir: Path to experiment directory (contains images/)
            mcp_gui_url: URL of the MCP GUI server
        """
        self.experiment_dir = experiment_dir
        self.images_dir = experiment_dir / "img"
        self.mcp_gui_url = mcp_gui_url
        self._connection_tested = False
        self._connection_available = False
    
    async def test_mcp_connection(self) -> bool:
        """
        Test if MCP GUI server is available.
        
        Returns:
            True if MCP server is reachable, False otherwise
        """
        if self._connection_tested:
            return self._connection_available
            
        try:
            async with Client(self.mcp_gui_url) as client:
                # Try to call a simple tool to test connection
                await client.list_tools()
                self._connection_available = True
                log.info(f"MCP GUI server connection successful at {self.mcp_gui_url}")
        except Exception as e:
            self._connection_available = False
            log.warning(f"MCP GUI server not available at {self.mcp_gui_url}: {e}")
            log.warning("Target resolution will fail for image/text targets. Consider:")
            log.warning("1. Starting the MCP GUI server")
            log.warning("2. Using position-based targets instead")
        
        self._connection_tested = True
        return self._connection_available
        
    async def resolve_target(self, target: Target, screenshot_base64: str = None, offset_x: int = 0, offset_y: int = 0) -> Optional[TargetMatch]:
        """
        Resolve a playbook target to screen coordinates using MCP GUI server.
        
        Args:
            target: Target to resolve (image, text, or position)
            screenshot_base64: Base64 encoded screenshot data (required for image/text targets)
            offset_x: X offset for coordinates
            offset_y: Y offset for coordinates
            
        Returns:
            TargetMatch if found, None otherwise
        """
        try:
            # Direct position coordinates
            if target.position:
                return TargetMatch(
                    coordinates=tuple(target.position),
                    confidence=1.0,
                    method='position'
                )
            
            # Require screenshot data for image/text targets
            if (target.image or target.text) and not screenshot_base64:
                log.error("Screenshot data required for image/text targets")
                return None
            
            # Connect to MCP GUI server with proper error handling
            try:
                log.debug(f"Connecting to MCP GUI server at {self.mcp_gui_url}")
                
                # Create client with longer timeout for PaddleOCR operations
                timeout = 120.0  # 2 minute timeout
                async with Client(self.mcp_gui_url, timeout=timeout) as client:
                    
                    # Image-based targeting using find_icon
                    if target.image:
                        log.debug(f"Using MCP find_icon for image: {target.image}")
                        image_path = self.images_dir / target.image
                        log.debug(f"Looking for image at: {image_path}")
                        
                        # Read and encode icon file as base64
                        try:
                            with open(image_path, "rb") as f:
                                icon_bytes = f.read()
                            icon_base64 = base64.b64encode(icon_bytes).decode('utf-8')
                            log.debug(f"Encoded icon to base64, size: {len(icon_base64)} chars")
                        except FileNotFoundError:
                            log.error(f"Icon file not found: {image_path}")
                            return None
                        except Exception as e:
                            log.error(f"Failed to read icon file: {e}")
                            return None
                        
                        result = await client.call_tool("find_icon", {
                            "icon_base64": icon_base64,
                            "screenshot_base64": screenshot_base64,
                            "offset_x": offset_x,
                            "offset_y": offset_y
                        })
                        
                        # Parse response
                        data = result[0].text
                        locations_data = json.loads(data)
                        locations = locations_data.get("locations", [])
                        
                        if locations:
                            x, y = locations[0]
                            log.info(f"Found image '{target.image}' at ({x}, {y}) via MCP")
                            return TargetMatch(
                                coordinates=(x, y),
                                confidence=0.8,
                                method='image'
                            )
                        else:
                            log.warning(f"Image '{target.image}' not found via MCP")
                            return None
                    
                    # Text-based targeting using find_text
                    if target.text:
                        log.debug(f"Using MCP find_text for text: {target.text}")
                        
                        result = await client.call_tool("find_text", {
                            "text": target.text,
                            "screenshot_base64": screenshot_base64,
                            "offset_x": offset_x,
                            "offset_y": offset_y
                        })
                        
                        # Parse response
                        data = result[0].text
                        locations_data = json.loads(data)
                        locations = locations_data.get("locations", [])
                        
                        if locations:
                            location_info = locations[0]
                            x = location_info["location"]["x"]
                            y = location_info["location"]["y"]
                            found_text = location_info["text"]
                            
                            log.info(f"Found text '{target.text}' (matched: '{found_text}') at ({x}, {y}) via MCP")
                            return TargetMatch(
                                coordinates=(x, y),
                                confidence=0.8,
                                method='text'
                            )
                        else:
                            log.warning(f"Text '{target.text}' not found via MCP")
                            return None
                        
            except Exception as mcp_error:
                log.error(f"MCP connection failed: {mcp_error}", exc_info=True)
                log.error(f"Ensure MCP GUI server is running at {self.mcp_gui_url}")
                return None
            
            log.warning(f"Target has no valid resolution method: {target}")
            return None
            
        except Exception as e:
            log.error(f"Error resolving target via MCP: {e}")
            return None
    


class MCPConditionChecker:
    """
    Helper class for checking playbook conditions using MCP GUI server.
    
    Used by BlockAction to evaluate 'when' conditions.
    """
    
    def __init__(self, target_resolver: MCPTargetResolver):
        """
        Initialize condition checker.
        
        Args:
            target_resolver: MCPTargetResolver instance
        """
        self.resolver = target_resolver
    
    async def check_conditions(self, conditions: List, screenshot_base64: str = None) -> bool:
        """
        Check if all conditions are met using MCP GUI server.
        
        Args:
            conditions: List of ExistsCondition/NotExistsCondition objects
            screenshot_base64: Base64 encoded screenshot data
            
        Returns:
            True if all conditions are met, False otherwise
        """
        from adare.types.playbook import ExistsCondition, NotExistsCondition
        
        for condition in conditions:
            if isinstance(condition, ExistsCondition):
                # Check if target exists
                target = Target(
                    image=condition.image,
                    text=condition.text
                )
                match = await self.resolver.resolve_target(target, screenshot_base64)
                if not match:
                    log.debug(f"Exists condition failed: target not found")
                    return False
                    
            elif isinstance(condition, NotExistsCondition):
                # Check if target does NOT exist
                target = Target(
                    image=condition.image,
                    text=condition.text
                )
                match = await self.resolver.resolve_target(target, screenshot_base64)
                if match:
                    log.debug(f"NotExists condition failed: target found")
                    return False
        
        log.debug("All conditions met")
        return True