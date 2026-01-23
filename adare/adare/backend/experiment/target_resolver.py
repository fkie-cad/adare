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
import ulid

from fastmcp import Client
from adare.types.playbook import Target, SweepStrategy, BestConfidenceStrategy, ClosestToStrategy, TopLeftStrategy, TopRightStrategy, BottomLeftStrategy, BottomRightStrategy, LargestStrategy, SmallestStrategy
# Stage events are now handled by action events in playbook controller

log = logging.getLogger(__name__)


@dataclass
class TargetMatch:
    """Represents a found target with confidence and location."""
    coordinates: Tuple[int, int]
    confidence: float
    method: str  # 'image', 'text', 'position'
    region: Optional[Tuple[int, int, int, int]] = None  # x, y, width, height
    text: Optional[str] = None  # Original text for text matches


class MCPTargetResolver:
    """
    Target resolver using existing MCP GUI server for CV/OCR.
    
    This class connects to your existing mcp_gui.py server to perform
    image recognition and text detection for target resolution.
    """
    
    def __init__(self, experiment_dir: Path, mcp_gui_url: str = "http://localhost:13109/mcp", experiment_run_ulid: Optional[str] = None):
        """
        Initialize MCP target resolver.
        
        Args:
            experiment_dir: Path to experiment directory (contains images/)
            mcp_gui_url: URL of the MCP GUI server
            experiment_run_ulid: ULID for experiment run (for stage logging)
        """
        self.experiment_dir = experiment_dir
        self.images_dir = experiment_dir / "img" if experiment_dir else None
        self.mcp_gui_url = mcp_gui_url
        self.experiment_run_ulid = experiment_run_ulid
        self._connection_tested = False
        self._connection_available = False
    
    def _select_match_by_strategy(self, matches: List[TargetMatch], strategy) -> Optional[TargetMatch]:
        """
        Select a single match from multiple matches based on strategy.
        
        Args:
            matches: List of found matches
            strategy: Strategy object for selection
            
        Returns:
            Selected match or None if no valid match
        """
        if not matches:
            return None
        
        # If only one match, return it directly without applying strategy
        if len(matches) == 1:
            return matches[0]
        
        if strategy is None:
            # Error when multiple matches found but no strategy provided
            raise ValueError(f"Found {len(matches)} matches but no strategy was provided to select from them. "
                           f"Please specify a strategy (e.g., BestConfidence, TopLeft, etc.) to handle multiple matches.")
        
        elif isinstance(strategy, SweepStrategy):
            # Sort matches spatially: top-to-bottom, left-to-right (reading order)
            sorted_matches = sorted(matches, key=lambda m: (m.coordinates[1], m.coordinates[0]))
            index = strategy.index
            if 1 <= index <= len(sorted_matches):
                return sorted_matches[index - 1]  # Convert to 0-based
            else:
                log.warning(f"Sweep index {index} out of range (1-{len(sorted_matches)}), using first match")
                return sorted_matches[0]
        
        elif isinstance(strategy, BestConfidenceStrategy):
            best_confidence = max(m.confidence for m in matches)
            best_matches = [m for m in matches if m.confidence == best_confidence]
            if len(best_matches) > 1:
                log.warning(f"BestConfidenceStrategy: {len(best_matches)} matches tied with confidence {best_confidence}, using first")
            return best_matches[0]
        
        elif isinstance(strategy, ClosestToStrategy):
            # Check mode: target reference vs coordinates
            if strategy.text or strategy.image:
                # TARGET REFERENCE MODE (new)
                reference_coords = strategy._resolved_reference_coords

                def distance(match):
                    x, y = match.coordinates
                    ref_x, ref_y = reference_coords
                    return ((x - ref_x) ** 2 + (y - ref_y) ** 2) ** 0.5

                # Filter by max_distance if specified
                if strategy.max_distance:
                    matches = [m for m in matches if distance(m) <= strategy.max_distance]
                    if not matches:
                        log.warning(f"ClosestToStrategy: No matches within max_distance {strategy.max_distance}px")
                        return None

                # Find closest
                min_distance = min(distance(m) for m in matches)
                closest_matches = [m for m in matches if distance(m) == min_distance]
                if len(closest_matches) > 1:
                    log.warning(f"ClosestToStrategy: {len(closest_matches)} matches tied at distance {min_distance:.1f}, using first")
                return closest_matches[0]
            else:
                # COORDINATES MODE (existing - unchanged for backwards compatibility)
                def distance(match):
                    x, y = match.coordinates
                    return ((x - strategy.x) ** 2 + (y - strategy.y) ** 2) ** 0.5

                min_distance = min(distance(m) for m in matches)
                closest_matches = [m for m in matches if distance(m) == min_distance]
                if len(closest_matches) > 1:
                    log.warning(f"ClosestToStrategy: {len(closest_matches)} matches tied at distance {min_distance:.1f}, using first")
                return closest_matches[0]
        
        elif isinstance(strategy, TopLeftStrategy):
            # Sort by y (top), then x (left) - deterministic order
            sorted_matches = sorted(matches, key=lambda m: (m.coordinates[1], m.coordinates[0]))
            top_y = sorted_matches[0].coordinates[1]
            top_matches = [m for m in sorted_matches if m.coordinates[1] == top_y]
            if len(top_matches) > 1:
                log.warning(f"TopLeftStrategy: {len(top_matches)} matches at same top row y={top_y}, using leftmost")
            return top_matches[0]
        
        elif isinstance(strategy, TopRightStrategy):
            # Sort by y (top), then -x (right)
            sorted_matches = sorted(matches, key=lambda m: (m.coordinates[1], -m.coordinates[0]))
            top_y = sorted_matches[0].coordinates[1]
            top_matches = [m for m in sorted_matches if m.coordinates[1] == top_y]
            if len(top_matches) > 1:
                log.warning(f"TopRightStrategy: {len(top_matches)} matches at same top row y={top_y}, using rightmost")
            return top_matches[0]
        
        elif isinstance(strategy, BottomLeftStrategy):
            # Sort by -y (bottom), then x (left)
            sorted_matches = sorted(matches, key=lambda m: (-m.coordinates[1], m.coordinates[0]))
            bottom_y = sorted_matches[0].coordinates[1]
            bottom_matches = [m for m in sorted_matches if m.coordinates[1] == bottom_y]
            if len(bottom_matches) > 1:
                log.warning(f"BottomLeftStrategy: {len(bottom_matches)} matches at same bottom row y={bottom_y}, using leftmost")
            return bottom_matches[0]
        
        elif isinstance(strategy, BottomRightStrategy):
            # Sort by -y (bottom), then -x (right)
            sorted_matches = sorted(matches, key=lambda m: (-m.coordinates[1], -m.coordinates[0]))
            bottom_y = sorted_matches[0].coordinates[1]
            bottom_matches = [m for m in sorted_matches if m.coordinates[1] == bottom_y]
            if len(bottom_matches) > 1:
                log.warning(f"BottomRightStrategy: {len(bottom_matches)} matches at same bottom row y={bottom_y}, using rightmost")
            return bottom_matches[0]
        
        elif isinstance(strategy, LargestStrategy):
            def area(match):
                if match.region:
                    return match.region[2] * match.region[3]  # width * height
                return 0  # No region info, treat as zero area
            
            max_area = max(area(m) for m in matches)
            largest_matches = [m for m in matches if area(m) == max_area]
            if len(largest_matches) > 1:
                log.warning(f"LargestStrategy: {len(largest_matches)} matches tied with area {max_area}, using first")
            return largest_matches[0]
        
        elif isinstance(strategy, SmallestStrategy):
            def area(match):
                if match.region:
                    return match.region[2] * match.region[3]  # width * height
                return float('inf')  # No region info, treat as infinite
            
            min_area = min(area(m) for m in matches)
            smallest_matches = [m for m in matches if area(m) == min_area]
            if len(smallest_matches) > 1:
                log.warning(f"SmallestStrategy: {len(smallest_matches)} matches tied with area {min_area}, using first")
            return smallest_matches[0]
        
        else:
            log.warning(f"Unknown strategy type: {type(strategy)}, using first match")
            return matches[0]
    
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
            # Handle ClosestToStrategy with target reference
            if isinstance(target.strategy, ClosestToStrategy):
                if target.strategy.text or target.strategy.image:
                    # Reference-based mode - resolve reference target first
                    log.info(f"ClosestToStrategy using reference: text='{target.strategy.text}', image='{target.strategy.image}'")

                    # Create reference target
                    reference_target = Target(
                        text=target.strategy.text,
                        image=target.strategy.image,
                        strategy=None  # Use default strategy for reference
                    )

                    # Resolve reference target
                    reference_match = await self.resolve_target(
                        reference_target, screenshot_base64, offset_x, offset_y
                    )

                    if not reference_match:
                        # Reference target not found - fail immediately
                        ref_desc = target.strategy.text or target.strategy.image
                        log.error(f"ClosestToStrategy: Reference target '{ref_desc}' not found")
                        return None

                    reference_coords = reference_match.coordinates
                    log.info(f"Reference target found at {reference_coords}")

                    # Store reference coordinates in strategy for _select_match_by_strategy
                    target.strategy._resolved_reference_coords = reference_coords

                    # Optionally crop screenshot for performance optimization
                    if target.strategy.max_distance:
                        # OPTIMIZATION: Crop screenshot to region around reference
                        screenshot_base64, offset_x, offset_y = await self._crop_screenshot_region(
                            screenshot_base64,
                            reference_coords,
                            target.strategy.max_distance,
                            offset_x,
                            offset_y
                        )
                        log.debug(f"Cropped screenshot to region around {reference_coords} ±{target.strategy.max_distance}px")

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
                        
                        # Find substage is now handled by action events in playbook controller
                        
                        result = await client.call_tool("find_icon", {
                            "icon_base64": icon_base64,
                            "screenshot_base64": screenshot_base64,
                            "offset_x": offset_x,
                            "offset_y": offset_y
                        })
                        
                        # Parse response
                        if result.data is not None:
                            locations_data = result.data
                        elif result.content and len(result.content) > 0:
                            data = result.content[0].text
                            locations_data = json.loads(data)
                        else:
                            log.error("No data found in MCP result")
                            return None
                        locations = locations_data.get("locations", [])
                        similarities = locations_data.get("similarities", [])
                        
                        if locations:
                            # Create matches for all found locations using actual similarities
                            matches = []
                            for i, (x, y) in enumerate(locations):
                                # Use actual similarity score from MCP server, fallback to 0.8 if not available
                                confidence = similarities[i] if i < len(similarities) else 0.8
                                matches.append(TargetMatch(
                                    coordinates=(x, y),
                                    confidence=confidence,  # Use actual similarity from CV matching
                                    method='image'
                                ))
                            
                            # Log all found matches with their actual confidences
                            log.info(f"Found {len(matches)} matches for image '{target.image}':")
                            for i, match in enumerate(matches):
                                log.info(f"  Match {i+1}: at {match.coordinates} (confidence: {match.confidence:.3f})")
                            
                            # Set default strategy if none provided
                            if target.strategy is None:
                                from adare.types.playbook import BestConfidenceStrategy
                                target.strategy = BestConfidenceStrategy()
                                log.info(f"No strategy specified for image target, using default BestConfidenceStrategy")
                            
                            # Apply strategy to select from multiple matches
                            strategy_name = target.strategy.__class__.__name__ if target.strategy else "default"
                            strategy_params = ""
                            if target.strategy and hasattr(target.strategy, '__dict__'):
                                import attrs
                                if attrs.has(target.strategy):
                                    params = attrs.asdict(target.strategy)
                                    if params:
                                        strategy_params = f" with params {params}"
                            log.info(f"Applying {strategy_name} strategy{strategy_params} to select from {len(matches)} matches")
                            
                            try:
                                selected_match = self._select_match_by_strategy(matches, target.strategy)
                                if selected_match:
                                    selected_index = matches.index(selected_match) + 1
                                    log.info(f"Selected match {selected_index}: image '{target.image}' at {selected_match.coordinates} via MCP")
                                    # Mark substage as successful
                                    return selected_match
                                else:
                                    log.error(f"Strategy selection returned None for image '{target.image}' with {len(matches)} matches")
                                    return None
                            except ValueError as strategy_error:
                                log.error(f"Strategy selection failed for image '{target.image}': {strategy_error}")
                                log.error(f"Target strategy: {target.strategy}, Matches: {len(matches)}")
                                return None
                        else:
                            log.warning(f"Image '{target.image}' not found via MCP")
                            # Mark substage as failed when no matches found
                            return None
                    
                    # Text-based targeting using find_text
                    if target.text:
                        log.debug(f"Using MCP find_text for text: {target.text}")
                        
                        # Find substage is now handled by action events in playbook controller
                        
                        result = await client.call_tool("find_text", {
                            "text": target.text,
                            "screenshot_base64": screenshot_base64,
                            "offset_x": offset_x,
                            "offset_y": offset_y
                        })
                        
                        # Parse response
                        if result.data is not None:
                            locations_data = result.data
                        elif result.content and len(result.content) > 0:
                            data = result.content[0].text
                            locations_data = json.loads(data)
                        else:
                            log.error("No data found in MCP result")
                            return None
                        locations = locations_data.get("locations", [])
                        confidences = locations_data.get("confidences", [])
                        
                        if locations:
                            # Create matches for all found text locations using actual OCR confidences
                            matches = []
                            for i, location_info in enumerate(locations):
                                x = location_info["location"]["x"]
                                y = location_info["location"]["y"]
                                found_text = location_info["text"]
                                # Use actual OCR confidence score from MCP server, fallback to 0.8 if not available
                                confidence = confidences[i] if i < len(confidences) else 0.8
                                matches.append(TargetMatch(
                                    coordinates=(x, y),
                                    confidence=confidence,  # Use actual OCR confidence from PaddleOCR
                                    method='text',
                                    text=found_text
                                ))
                            
                            # Log all found matches with their actual confidences
                            log.info(f"Found {len(matches)} matches for text '{target.text}':")
                            for i, match in enumerate(matches):
                                log.info(f"  Match {i+1}: '{match.text}' at {match.coordinates} (confidence: {match.confidence:.3f})")
                            
                            # Set default strategy if none provided
                            if target.strategy is None:
                                from adare.types.playbook import TopLeftStrategy
                                target.strategy = TopLeftStrategy()  # Text: natural reading order (top-left first)
                                log.info(f"No strategy specified for text target, using default TopLeftStrategy")
                            
                            # Apply strategy to select from multiple matches
                            strategy_name = target.strategy.__class__.__name__ if target.strategy else "default"
                            strategy_params = ""
                            if target.strategy and hasattr(target.strategy, '__dict__'):
                                import attrs
                                if attrs.has(target.strategy):
                                    params = attrs.asdict(target.strategy)
                                    if params:
                                        strategy_params = f" with params {params}"
                            log.info(f"Applying {strategy_name} strategy{strategy_params} to select from {len(matches)} matches")
                            
                            try:
                                selected_match = self._select_match_by_strategy(matches, target.strategy)
                                if selected_match:
                                    selected_index = matches.index(selected_match) + 1
                                    log.info(f"Selected match {selected_index}: '{selected_match.text}' at {selected_match.coordinates} via MCP")
                                    # Mark substage as successful
                                    return selected_match
                                else:
                                    log.error(f"Strategy selection returned None for text '{target.text}' with {len(matches)} matches")
                                    return None
                            except ValueError as strategy_error:
                                log.error(f"Strategy selection failed for text '{target.text}': {strategy_error}")
                                log.error(f"Target strategy: {target.strategy}, Matches: {len(matches)}")
                                return None
                        else:
                            log.warning(f"Text '{target.text}' not found via MCP")
                            # Mark substage as failed when no matches found
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

    async def _crop_screenshot_region(
        self,
        screenshot_base64: str,
        center_coords: Tuple[int, int],
        padding: int,
        offset_x: int = 0,
        offset_y: int = 0
    ) -> Tuple[str, int, int]:
        """Crop screenshot to region around reference coordinates for optimization.

        Args:
            screenshot_base64: Full screenshot (base64)
            center_coords: Center point (x, y)
            padding: Distance in pixels to extend from center
            offset_x: Current X offset
            offset_y: Current Y offset

        Returns:
            Tuple of (cropped_screenshot_base64, new_offset_x, new_offset_y)
        """
        import cv2
        import numpy as np
        import base64

        try:
            # Decode screenshot
            img_bytes = base64.b64decode(screenshot_base64)
            img_array = np.frombuffer(img_bytes, dtype=np.uint8)
            img = cv2.imdecode(img_array, cv2.IMREAD_COLOR)

            if img is None:
                log.warning("Failed to decode screenshot for cropping, using full screenshot")
                return screenshot_base64, offset_x, offset_y

            h, w = img.shape[:2]
            cx, cy = center_coords

            # Calculate crop region with bounds checking
            x1 = max(0, cx - padding)
            y1 = max(0, cy - padding)
            x2 = min(w, cx + padding)
            y2 = min(h, cy + padding)

            # Crop image
            cropped_img = img[y1:y2, x1:x2]

            # Encode back to base64
            _, buffer = cv2.imencode('.png', cropped_img)
            cropped_base64 = base64.b64encode(buffer).decode('utf-8')

            # Calculate new offsets (coordinates in cropped image need adjustment)
            new_offset_x = offset_x + x1
            new_offset_y = offset_y + y1

            log.debug(f"Cropped region: ({x1},{y1}) to ({x2},{y2}), new offsets: ({new_offset_x},{new_offset_y})")

            return cropped_base64, new_offset_x, new_offset_y

        except Exception as e:
            log.warning(f"Screenshot cropping failed: {e}, using full screenshot")
            return screenshot_base64, offset_x, offset_y


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