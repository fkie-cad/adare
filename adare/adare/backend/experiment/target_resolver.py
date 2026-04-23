"""
Target Resolution Module using existing MCP GUI Server.

This module provides target resolution by leveraging the existing MCP GUI server
for CV/OCR capabilities (find_icon and find_text tools).
"""

import base64
import json
import logging
from dataclasses import dataclass
from pathlib import Path

from fastmcp import Client

from adare.types.playbook import (
    BestConfidenceStrategy,
    BottomLeftStrategy,
    BottomRightStrategy,
    ClosestToStrategy,
    LargestStrategy,
    SmallestStrategy,
    SweepStrategy,
    Target,
    TextMatchConfig,
    TopLeftStrategy,
    TopRightStrategy,
)

# Stage events are now handled by action events in playbook controller

log = logging.getLogger(__name__)


@dataclass
class TargetMatch:
    """Represents a found target with confidence and location."""
    coordinates: tuple[int, int]
    confidence: float
    method: str  # 'image', 'text', 'position'
    region: tuple[int, int, int, int] | None = None  # x, y, width, height
    text: str | None = None  # Original text for text matches


class MCPTargetResolver:
    """
    Target resolver using existing MCP GUI server for CV/OCR.

    This class connects to your existing mcp_gui.py server to perform
    image recognition and text detection for target resolution.
    """

    def __init__(self, experiment_dir: Path, mcp_gui_url: str = "http://localhost:13109/mcp", experiment_run_ulid: str | None = None):
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

    def _select_match_by_strategy(self, matches: list[TargetMatch], strategy, reference_coords: tuple[int, int] | None = None) -> TargetMatch | None:
        """
        Select a single match from multiple matches based on strategy.

        Args:
            matches: List of found matches
            strategy: Strategy object for selection
            reference_coords: Optional reference coordinates for ClosestToStrategy

        Returns:
            Selected match or None if no valid match
        """
        if not matches:
            return None

        # If only one match, return it directly without applying strategy
        if len(matches) == 1:
            return matches[0]

        if strategy is None:
            raise ValueError(f"Found {len(matches)} matches but no strategy was provided to select from them. "
                           f"Please specify a strategy (e.g., BestConfidence, TopLeft, etc.) to handle multiple matches.")

        # Dispatch to strategy-specific handler
        handler = self._get_strategy_handler(strategy)
        if handler is not None:
            return handler(matches, strategy, reference_coords)

        log.warning(f"Unknown strategy type: {type(strategy)}, using first match")
        return matches[0]

    def _get_strategy_handler(self, strategy):
        """Return the handler method for the given strategy, or None if unknown."""
        dispatch = [
            (SweepStrategy, self._select_by_sweep),
            (BestConfidenceStrategy, self._select_by_best_confidence),
            (ClosestToStrategy, self._select_by_closest_to),
            ((TopLeftStrategy, TopRightStrategy, BottomLeftStrategy, BottomRightStrategy),
             self._select_by_corner),
            (LargestStrategy, self._select_by_largest),
            (SmallestStrategy, self._select_by_smallest),
        ]
        for strategy_type, handler in dispatch:
            if isinstance(strategy, strategy_type):
                return handler
        return None

    @staticmethod
    def _select_by_sweep(matches, strategy, _reference_coords):
        """Select match by sweep index (spatial reading order)."""
        sorted_matches = sorted(matches, key=lambda m: (m.coordinates[1], m.coordinates[0]))
        index = strategy.index
        if 1 <= index <= len(sorted_matches):
            return sorted_matches[index - 1]
        log.warning(f"Sweep index {index} out of range (1-{len(sorted_matches)}), using first match")
        return sorted_matches[0]

    @staticmethod
    def _select_by_best_confidence(matches, _strategy, _reference_coords):
        """Select match with highest confidence score."""
        best_confidence = max(m.confidence for m in matches)
        best_matches = [m for m in matches if m.confidence == best_confidence]
        if len(best_matches) > 1:
            log.warning(f"BestConfidenceStrategy: {len(best_matches)} matches tied with confidence {best_confidence}, using first")
        return best_matches[0]

    @staticmethod
    def _select_by_closest_to(matches, strategy, reference_coords):
        """Select match closest to reference point (target reference or coordinate mode)."""
        if strategy.text or strategy.image:
            return MCPTargetResolver._select_closest_to_reference(matches, strategy, reference_coords)
        return MCPTargetResolver._select_closest_to_coords(matches, strategy)

    @staticmethod
    def _select_closest_to_reference(matches, strategy, reference_coords):
        """Select match closest to a resolved reference target."""
        if reference_coords is None:
            if hasattr(strategy, '_resolved_reference_coords'):
                reference_coords = strategy._resolved_reference_coords
            else:
                log.error("ClosestToStrategy: Reference coordinates missing for text/image reference mode")
                return None

        def distance(match):
            x, y = match.coordinates
            ref_x, ref_y = reference_coords
            return ((x - ref_x) ** 2 + (y - ref_y) ** 2) ** 0.5

        if strategy.max_distance:
            matches = [m for m in matches if distance(m) <= strategy.max_distance]
            if not matches:
                log.warning(f"ClosestToStrategy: No matches within max_distance {strategy.max_distance}px")
                return None

        min_dist = min(distance(m) for m in matches)
        closest_matches = [m for m in matches if distance(m) == min_dist]
        if len(closest_matches) > 1:
            log.warning(f"ClosestToStrategy: {len(closest_matches)} matches tied at distance {min_dist:.1f}, using first")
        return closest_matches[0]

    @staticmethod
    def _select_closest_to_coords(matches, strategy):
        """Select match closest to explicit (x, y) coordinates."""
        def distance(match):
            x, y = match.coordinates
            return ((x - strategy.x) ** 2 + (y - strategy.y) ** 2) ** 0.5

        min_dist = min(distance(m) for m in matches)
        closest_matches = [m for m in matches if distance(m) == min_dist]
        if len(closest_matches) > 1:
            log.warning(f"ClosestToStrategy: {len(closest_matches)} matches tied at distance {min_dist:.1f}, using first")
        return closest_matches[0]

    @staticmethod
    def _select_by_corner(matches, strategy, _reference_coords):
        """Select match by corner position (TopLeft, TopRight, BottomLeft, BottomRight)."""
        # Determine sort key based on strategy type
        strategy_name = type(strategy).__name__
        y_sign = 1 if isinstance(strategy, (TopLeftStrategy, TopRightStrategy)) else -1
        x_sign = 1 if isinstance(strategy, (TopLeftStrategy, BottomLeftStrategy)) else -1
        sorted_matches = sorted(matches, key=lambda m: (y_sign * m.coordinates[1], x_sign * m.coordinates[0]))
        edge_y = sorted_matches[0].coordinates[1]
        edge_matches = [m for m in sorted_matches if m.coordinates[1] == edge_y]
        if len(edge_matches) > 1:
            edge_label = "top" if y_sign == 1 else "bottom"
            side_label = "leftmost" if x_sign == 1 else "rightmost"
            log.warning(f"{strategy_name}: {len(edge_matches)} matches at same {edge_label} row y={edge_y}, using {side_label}")
        return edge_matches[0]

    @staticmethod
    def _select_by_largest(matches, _strategy, _reference_coords):
        """Select match with largest bounding region area."""
        def area(match):
            if match.region:
                return match.region[2] * match.region[3]
            return 0

        max_area = max(area(m) for m in matches)
        largest_matches = [m for m in matches if area(m) == max_area]
        if len(largest_matches) > 1:
            log.warning(f"LargestStrategy: {len(largest_matches)} matches tied with area {max_area}, using first")
        return largest_matches[0]

    @staticmethod
    def _select_by_smallest(matches, _strategy, _reference_coords):
        """Select match with smallest bounding region area."""
        def area(match):
            if match.region:
                return match.region[2] * match.region[3]
            return float('inf')

        min_area = min(area(m) for m in matches)
        smallest_matches = [m for m in matches if area(m) == min_area]
        if len(smallest_matches) > 1:
            log.warning(f"SmallestStrategy: {len(smallest_matches)} matches tied with area {min_area}, using first")
        return smallest_matches[0]

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
        except (OSError, ConnectionError, TimeoutError, RuntimeError) as e:
            self._connection_available = False
            log.warning(f"MCP GUI server not available at {self.mcp_gui_url}: {e}")
            log.warning("Target resolution will fail for image/text targets. Consider:")
            log.warning("1. Starting the MCP GUI server")
            log.warning("2. Using position-based targets instead")

        self._connection_tested = True
        return self._connection_available

    async def resolve_target(self, target: Target, screenshot_base64: str = None, offset_x: int = 0, offset_y: int = 0) -> TargetMatch | None:
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
            reference_coords = None

            # Handle ClosestToStrategy with target reference
            if isinstance(target.strategy, ClosestToStrategy) and (target.strategy.text or target.strategy.image):
                result = await self._resolve_closest_to_reference(
                    target, screenshot_base64, offset_x, offset_y
                )
                if result is None:
                    return None
                reference_coords, screenshot_base64, offset_x, offset_y = result

            # Direct position coordinates
            if target.position:
                return TargetMatch(coordinates=tuple(target.position), confidence=1.0, method='position')

            # Require screenshot data for image/text targets
            if (target.image or target.text) and not screenshot_base64:
                log.error("Screenshot data required for image/text targets")
                return None

            # Connect to MCP GUI server and resolve image or text target
            try:
                log.debug(f"Connecting to MCP GUI server at {self.mcp_gui_url}")
                timeout = 120.0  # 2 minute timeout for PaddleOCR operations
                async with Client(self.mcp_gui_url, timeout=timeout) as client:
                    if target.image:
                        return await self._resolve_image_target(
                            client, target, screenshot_base64, offset_x, offset_y, reference_coords
                        )
                    if target.text:
                        return await self._resolve_text_target(
                            client, target, screenshot_base64, offset_x, offset_y, reference_coords
                        )

            except FileNotFoundError:
                raise
            except (OSError, ConnectionError, TimeoutError, RuntimeError, json.JSONDecodeError, ValueError, KeyError) as mcp_error:
                log.error(f"MCP connection failed: {mcp_error}", exc_info=True)
                log.error(f"Ensure MCP GUI server is running at {self.mcp_gui_url}")
                return None

            log.warning(f"Target has no valid resolution method: {target}")
            return None

        except FileNotFoundError:
            raise
        except (OSError, ConnectionError, TimeoutError, RuntimeError, json.JSONDecodeError, ValueError, KeyError) as e:
            log.error(f"Error resolving target via MCP: {e}")
            return None

    async def _resolve_closest_to_reference(self, target, screenshot_base64, offset_x, offset_y):
        """Resolve the ClosestToStrategy reference target and optionally crop the screenshot.

        Returns:
            Tuple of (reference_coords, screenshot_base64, offset_x, offset_y) on success,
            None if reference target was not found.
        """
        strategy = target.strategy
        log.info(f"ClosestToStrategy using reference: text='{strategy.text}', image='{strategy.image}'")

        reference_target = Target(text=strategy.text, image=strategy.image, strategy=None)
        reference_match = await self.resolve_target(reference_target, screenshot_base64, offset_x, offset_y)

        if not reference_match:
            ref_desc = strategy.text or strategy.image
            log.error(f"ClosestToStrategy: Reference target '{ref_desc}' not found")
            return None

        reference_coords = reference_match.coordinates
        log.info(f"Reference target found at {reference_coords}")

        if strategy.max_distance:
            screenshot_base64, offset_x, offset_y = await self._crop_screenshot_region(
                screenshot_base64, reference_coords, strategy.max_distance, offset_x, offset_y
            )
            log.debug(f"Cropped screenshot to region around {reference_coords} +/-{strategy.max_distance}px")

        return reference_coords, screenshot_base64, offset_x, offset_y

    async def _resolve_image_target(self, client, target, screenshot_base64, offset_x, offset_y, reference_coords):
        """Resolve an image-based target using MCP find_icon."""
        log.debug(f"Using MCP find_icon for image: {target.image}")
        image_path = self.images_dir / target.image
        log.debug(f"Looking for image at: {image_path}")

        icon_base64 = self._read_icon_file(image_path)
        if icon_base64 is None:
            return None

        result = await client.call_tool("find_icon", {
            "icon_base64": icon_base64,
            "screenshot_base64": screenshot_base64,
            "offset_x": offset_x,
            "offset_y": offset_y
        })

        locations_data = self._parse_mcp_result(result)
        if locations_data is None:
            return None

        locations = locations_data.get("locations", [])
        similarities = locations_data.get("similarities", [])

        if not locations:
            log.warning(f"Image '{target.image}' not found via MCP")
            return None

        # Create matches for all found locations using actual similarities
        matches = []
        for i, (x, y) in enumerate(locations):
            confidence = similarities[i] if i < len(similarities) else 0.8
            matches.append(TargetMatch(coordinates=(x, y), confidence=confidence, method='image'))

        # Set default strategy if none provided
        if target.strategy is None:
            target.strategy = BestConfidenceStrategy()
            log.info("No strategy specified for image target, using default BestConfidenceStrategy")

        target_desc = f"image '{target.image}'"
        return self._apply_strategy_and_select(matches, target, reference_coords, target_desc)

    def _read_icon_file(self, image_path: Path) -> str | None:
        """Read and base64-encode an icon file. Returns None on non-fatal read errors."""
        try:
            with open(image_path, "rb") as f:
                icon_bytes = f.read()
            icon_base64 = base64.b64encode(icon_bytes).decode('utf-8')
            log.debug(f"Encoded icon to base64, size: {len(icon_base64)} chars")
            return icon_base64
        except FileNotFoundError:
            log.error(f"Icon file not found: {image_path}")
            raise
        except OSError as e:
            log.error(f"Failed to read icon file: {e}")
            return None

    async def _resolve_text_target(self, client, target, screenshot_base64, offset_x, offset_y, reference_coords):
        """Resolve a text-based target using MCP find_text."""
        log.debug(f"Using MCP find_text for text: {target.text}")

        text_match = target.text_match or TextMatchConfig()
        mcp_params = self._build_text_mcp_params(target, screenshot_base64, offset_x, offset_y, text_match)

        log.debug(f"Text matching mode: {text_match.mode}")

        result = await client.call_tool("find_text", mcp_params)

        locations_data = self._parse_mcp_result(result)
        if locations_data is None:
            return None

        locations = locations_data.get("locations", [])
        confidences = locations_data.get("confidences", [])

        if not locations:
            log.warning(f"Text '{target.text}' not found via MCP")
            return None

        matches = self._build_text_matches(locations, confidences)

        # Set default strategy if none provided
        if target.strategy is None:
            target.strategy = TopLeftStrategy()
            log.info("No strategy specified for text target, using default TopLeftStrategy")

        target_desc = f"text '{target.text}'"
        return self._apply_strategy_and_select(matches, target, reference_coords, target_desc)

    @staticmethod
    def _build_text_mcp_params(target, screenshot_base64, offset_x, offset_y, text_match):
        """Build the MCP call parameters for find_text."""
        mcp_params = {
            "text": target.text,
            "screenshot_base64": screenshot_base64,
            "offset_x": offset_x,
            "offset_y": offset_y,
            "match_mode": text_match.mode,
        }
        if text_match.flags:
            mcp_params["regex_flags"] = text_match.flags
        if text_match.allow_missing_chars is not None:
            mcp_params["allow_missing_chars"] = text_match.allow_missing_chars
        if text_match.max_missing is not None:
            mcp_params["max_missing"] = text_match.max_missing
        if text_match.min_similarity is not None:
            mcp_params["min_similarity"] = text_match.min_similarity
        if text_match.case_sensitive:
            mcp_params["case_sensitive"] = text_match.case_sensitive
        return mcp_params

    @staticmethod
    def _build_text_matches(locations, confidences):
        """Build TargetMatch list from text location results."""
        matches = []
        for i, location_info in enumerate(locations):
            x = location_info["location"]["x"]
            y = location_info["location"]["y"]
            found_text = location_info["text"]
            confidence = confidences[i] if i < len(confidences) else 0.8
            match = TargetMatch(coordinates=(x, y), confidence=confidence, method='text', text=found_text)

            loc = location_info["location"]
            if "width" in loc and "height" in loc:
                w, h = loc["width"], loc["height"]
                log.info(f"DEBUG: location_info['location'] keys: {loc.keys()}")
                rx = int(x - w / 2)
                ry = int(y - h / 2)
                match.region = (rx, ry, w, h)
                log.info(f"DEBUG: Calculated Region: {match.region} from x={x}, y={y}, w={w}, h={h}")

            matches.append(match)
        return matches

    @staticmethod
    def _parse_mcp_result(result):
        """Parse the MCP tool result into a locations data dict."""
        if result.data is not None:
            return result.data
        if result.content and len(result.content) > 0:
            return json.loads(result.content[0].text)
        log.error("No data found in MCP result")
        return None

    def _apply_strategy_and_select(self, matches, target, reference_coords, target_desc):
        """Log matches, apply strategy, and return the selected match or None."""
        # Log all found matches
        log.info(f"Found {len(matches)} matches for {target_desc}:")
        for i, match in enumerate(matches):
            if match.text:
                log.info(f"  Match {i+1}: '{match.text}' at {match.coordinates} (confidence: {match.confidence:.3f})")
            else:
                log.info(f"  Match {i+1}: at {match.coordinates} (confidence: {match.confidence:.3f})")

        # Log strategy info
        self._log_strategy_info(target.strategy, len(matches))

        try:
            selected_match = self._select_match_by_strategy(matches, target.strategy, reference_coords)
            if selected_match:
                selected_index = matches.index(selected_match) + 1
                if selected_match.text:
                    log.info(f"Selected match {selected_index}: '{selected_match.text}' at {selected_match.coordinates} via MCP")
                else:
                    log.info(f"Selected match {selected_index}: {target_desc} at {selected_match.coordinates} via MCP")
                return selected_match
            log.error(f"Strategy selection returned None for {target_desc} with {len(matches)} matches")
            return None
        except ValueError as strategy_error:
            log.error(f"Strategy selection failed for {target_desc}: {strategy_error}")
            log.error(f"Target strategy: {target.strategy}, Matches: {len(matches)}")
            return None

    @staticmethod
    def _log_strategy_info(strategy, match_count):
        """Log strategy name and parameters."""
        strategy_name = strategy.__class__.__name__ if strategy else "default"
        strategy_params = ""
        if strategy and hasattr(strategy, '__dict__'):
            import attrs
            if attrs.has(strategy):
                params = attrs.asdict(strategy)
                if params:
                    strategy_params = f" with params {params}"
        log.info(f"Applying {strategy_name} strategy{strategy_params} to select from {match_count} matches")

    async def _crop_screenshot_region(
        self,
        screenshot_base64: str,
        center_coords: tuple[int, int],
        padding: int,
        offset_x: int = 0,
        offset_y: int = 0
    ) -> tuple[str, int, int]:
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
        import base64

        import cv2
        import numpy as np

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

        except (ValueError, TypeError, OSError, cv2.error) as e:
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

    async def check_conditions(self, conditions: list, screenshot_base64: str = None) -> bool:
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
                    log.debug("Exists condition failed: target not found")
                    return False

            elif isinstance(condition, NotExistsCondition):
                # Check if target does NOT exist
                target = Target(
                    image=condition.image,
                    text=condition.text
                )
                match = await self.resolver.resolve_target(target, screenshot_base64)
                if match:
                    log.debug("NotExists condition failed: target found")
                    return False

        log.debug("All conditions met")
        return True
