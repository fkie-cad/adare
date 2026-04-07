"""OCR processing utilities using PaddleOCR."""

import logging
import io
import asyncio
import re
from concurrent.futures import ThreadPoolExecutor
from typing import List, Dict, Any, Tuple, Union, Optional
import numpy as np
import cv2
from datetime import datetime

from .constants import OCRConstants
from .exceptions import OCRProcessingError

log = logging.getLogger(__name__)


class OCRProcessor:
    """Handles OCR processing operations using PaddleOCR."""

    @staticmethod
    def _run_paddle_ocr(screenshot_bytes: bytes) -> List[Tuple[List[List[float]], Tuple[str, float]]]:
        """Run PaddleOCR in a separate thread to avoid blocking."""
        from paddleocr import PaddleOCR

        try:
            log.info("Initializing PaddleOCR...")
            
            # Capture current logging level as PaddleOCR might change it
            root_logger = logging.getLogger()
            original_level = root_logger.getEffectiveLevel()
            
            ocr = PaddleOCR(
                use_doc_orientation_classify=False,
                use_doc_unwarping=False,
                use_textline_orientation=False,
                text_det_unclip_ratio=OCRConstants.OCR_DET_UNCLIP_RATIO,
                text_det_thresh=OCRConstants.OCR_DET_DB_THRESH,
                text_det_box_thresh=OCRConstants.OCR_DET_BOX_THRESH,
                lang='en' # Explicitly set language
            )
            
            # Restore logging level
            root_logger.setLevel(original_level)

            log.info("Converting bytes to numpy array...")
            nparr = np.frombuffer(screenshot_bytes, np.uint8)
            img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)

            log.info("Running OCR prediction with numpy array...")
            result = ocr.predict(input=img)

            # Extract detection results from predict() format
            detections = []
            for res in result:
                rec_texts = res['rec_texts']
                rec_polys = res['rec_polys']
                rec_scores = res['rec_scores']

                # Combine texts, boxes and scores
                for text, box, score in zip(rec_texts, rec_polys, rec_scores):
                    box_points = box.tolist()
                    detections.append([box_points, (text, score)])

            log.info(f"OCR prediction completed - found {len(detections)} text detections")
            return detections

        except Exception as e:
            raise OCRProcessingError(f"OCR failed: {str(e)}") from e

    @staticmethod
    async def process_screenshot(screenshot_bytes: bytes) -> List[Tuple[List[List[float]], Tuple[str, float]]]:
        """Process screenshot with OCR asynchronously."""
        executor = ThreadPoolExecutor(max_workers=OCRConstants.MAX_WORKERS)

        try:
            log.info("Running PaddleOCR...")
            result = await asyncio.get_event_loop().run_in_executor(
                executor, OCRProcessor._run_paddle_ocr, screenshot_bytes
            )
            log.info("PaddleOCR completed successfully")
            return result

        except OCRProcessingError:
            raise
        except Exception as e:
            raise OCRProcessingError(f"PaddleOCR failed: {e}") from e
        finally:
            executor.shutdown(wait=True)

    @staticmethod
    def calculate_text_center(box: List[List[float]], offset_x: int = 0, offset_y: int = 0) -> Tuple[int, int]:
        """Calculate center coordinates from bounding box."""
        x_coords = [point[0] for point in box]
        y_coords = [point[1] for point in box]
        center_x = int(sum(x_coords) / len(x_coords)) + offset_x
        center_y = int(sum(y_coords) / len(y_coords)) + offset_y
        return center_x, center_y


class TextMatcher:
    """Text matching utilities supporting substring, regex, and fuzzy matching."""

    _regex_cache: Dict[Tuple[str, int], re.Pattern] = {}

    @classmethod
    def compile_regex(cls, pattern: str, flags: Optional[List[str]] = None) -> Optional[re.Pattern]:
        """Compile and cache regex pattern with flags.

        Args:
            pattern: Regex pattern string
            flags: List of flag names (IGNORECASE, MULTILINE, DOTALL, VERBOSE)

        Returns:
            Compiled regex pattern, or None if compilation fails
        """
        # Convert flag names to re module constants
        flag_value = 0
        if flags:
            flag_map = {
                'IGNORECASE': re.IGNORECASE,
                'MULTILINE': re.MULTILINE,
                'DOTALL': re.DOTALL,
                'VERBOSE': re.VERBOSE
            }
            for flag_name in flags:
                if flag_name in flag_map:
                    flag_value |= flag_map[flag_name]
                else:
                    log.warning(f"Unknown regex flag: {flag_name}")

        # Check cache
        cache_key = (pattern, flag_value)
        if cache_key in cls._regex_cache:
            return cls._regex_cache[cache_key]

        # Compile and cache
        try:
            compiled = re.compile(pattern, flag_value)
            cls._regex_cache[cache_key] = compiled
            return compiled
        except re.error as e:
            log.warning(f"Invalid regex pattern '{pattern}': {e}")
            return None

    @classmethod
    def regex_match(cls, pattern: str, text: str, flags: Optional[List[str]] = None) -> bool:
        """Check if regex pattern matches text.

        Args:
            pattern: Regex pattern string
            text: Text to search in
            flags: List of flag names

        Returns:
            True if pattern matches, False otherwise
        """
        compiled = cls.compile_regex(pattern, flags)
        if compiled is None:
            return False

        return compiled.search(text) is not None


class FuzzyMatcher:
    """Fuzzy text matching for OCR inaccuracies using Levenshtein distance."""

    @staticmethod
    def levenshtein_distance(s1: str, s2: str, case_sensitive: bool = False) -> int:
        """Calculate edit distance between two strings.

        Uses dynamic programming to compute minimum number of single-character
        edits (insertions, deletions, substitutions) needed to transform s1 into s2.

        Args:
            s1: First string
            s2: Second string
            case_sensitive: If False, compare case-insensitively

        Returns:
            Levenshtein distance (number of edits)
        """
        if not case_sensitive:
            s1 = s1.lower()
            s2 = s2.lower()

        # Early exit for identical strings
        if s1 == s2:
            return 0

        len1, len2 = len(s1), len(s2)

        # Create DP table
        dp = [[0] * (len2 + 1) for _ in range(len1 + 1)]

        # Initialize base cases
        for i in range(len1 + 1):
            dp[i][0] = i
        for j in range(len2 + 1):
            dp[0][j] = j

        # Fill DP table
        for i in range(1, len1 + 1):
            for j in range(1, len2 + 1):
                if s1[i-1] == s2[j-1]:
                    dp[i][j] = dp[i-1][j-1]
                else:
                    dp[i][j] = 1 + min(
                        dp[i-1][j],    # deletion
                        dp[i][j-1],    # insertion
                        dp[i-1][j-1]   # substitution
                    )

        return dp[len1][len2]

    @staticmethod
    def similarity_ratio(s1: str, s2: str, case_sensitive: bool = False) -> float:
        """Calculate similarity ratio between two strings.

        Args:
            s1: First string
            s2: Second string
            case_sensitive: If False, compare case-insensitively

        Returns:
            Similarity ratio between 0.0 (completely different) and 1.0 (identical)
        """
        if not case_sensitive:
            s1 = s1.lower()
            s2 = s2.lower()

        # Early exit for identical strings
        if s1 == s2:
            return 1.0

        # Early exit for empty strings
        if not s1 or not s2:
            return 0.0

        distance = FuzzyMatcher.levenshtein_distance(s1, s2, case_sensitive=True)  # Already lowercased above
        max_len = max(len(s1), len(s2))

        return 1.0 - (distance / max_len)

    @staticmethod
    def fuzzy_match(
        pattern: str,
        text_detected: str,
        allow_missing_chars = None,  # Union[bool, str, List[str]]
        max_missing: Optional[int] = None,
        min_similarity: Optional[float] = None,
        case_sensitive: bool = False
    ) -> bool:
        """Fuzzy match with missing chars or similarity threshold.

        Args:
            pattern: Expected text pattern
            text_detected: Text detected by OCR
            allow_missing_chars: Allowed missing characters:
                - True: Allow any character to be missing
                - ".": Only allow this specific character to be missing
                - [".", ","]: Only allow these characters to be missing
            max_missing: Max missing chars allowed (requires allow_missing_chars)
            min_similarity: Minimum similarity ratio 0.0-1.0
            case_sensitive: If False, compare case-insensitively

        Returns:
            True if fuzzy match succeeds, False otherwise
        """
        # Mode 1: Allow missing characters (special OCR mode)
        if allow_missing_chars is not None and allow_missing_chars is not False:
            # Normalize allow_missing_chars to a set
            if allow_missing_chars is True:
                # Allow any character to be missing
                allowed_chars_set = None  # None means all chars allowed
            elif isinstance(allow_missing_chars, str):
                # Single character specified
                allowed_chars_set = set(allow_missing_chars)
            elif isinstance(allow_missing_chars, list):
                # List of characters specified
                allowed_chars_set = set(''.join(allow_missing_chars))
            else:
                log.warning(f"Invalid allow_missing_chars type: {type(allow_missing_chars)}, treating as False")
                allowed_chars_set = set()  # Empty set = no chars allowed

            pattern_compare = pattern if case_sensitive else pattern.lower()
            text_compare = text_detected if case_sensitive else text_detected.lower()

            # Track which characters from pattern are present in detected text
            # We'll find the longest common subsequence and track missing chars
            pattern_idx = 0
            text_idx = 0
            missing_chars = []

            while pattern_idx < len(pattern_compare):
                if text_idx < len(text_compare) and pattern_compare[pattern_idx] == text_compare[text_idx]:
                    # Characters match, advance both pointers
                    pattern_idx += 1
                    text_idx += 1
                else:
                    # Character from pattern is missing in detected text
                    missing_char = pattern_compare[pattern_idx]
                    missing_chars.append(missing_char)
                    pattern_idx += 1

            # Check if all characters in detected text were found in pattern
            if text_idx < len(text_compare):
                # Detected text has extra characters not in pattern
                return False

            # Check if all missing characters are allowed
            if allowed_chars_set is not None:
                # Specific characters allowed
                for missing_char in missing_chars:
                    if missing_char not in allowed_chars_set:
                        # Found a missing character that's not allowed
                        return False

            # Check missing count against threshold
            missing_count = len(missing_chars)
            if max_missing is not None:
                return missing_count <= max_missing

            return True

        # Mode 2: Similarity ratio threshold
        if min_similarity is not None:
            ratio = FuzzyMatcher.similarity_ratio(pattern, text_detected, case_sensitive)
            return ratio >= min_similarity

        return False

    @staticmethod
    def regex_fuzzy_match(
        pattern: str,
        text_detected: str,
        flags: Optional[List[str]] = None,
        min_similarity: float = 0.8,
        case_sensitive: bool = False
    ) -> bool:
        """Combined regex + fuzzy matching.

        First finds all regex pattern matches, then fuzzy matches against similarity threshold.

        Args:
            pattern: Regex pattern string
            text_detected: Text detected by OCR
            flags: List of regex flag names
            min_similarity: Minimum similarity ratio
            case_sensitive: If False, compare case-insensitively

        Returns:
            True if regex matches and fuzzy similarity meets threshold
        """
        # Compile regex
        compiled = TextMatcher.compile_regex(pattern, flags)
        if compiled is None:
            return False

        # Find all regex matches
        matches = compiled.findall(text_detected)
        if not matches:
            return False

        # Check if any match meets fuzzy similarity threshold
        for match in matches:
            ratio = FuzzyMatcher.similarity_ratio(match, text_detected, case_sensitive)
            if ratio >= min_similarity:
                return True

        return False


class TextDetector:
    """Handles text detection and search operations."""
    
    _debug_output_dir: Optional[Any] = None

    @classmethod
    def set_debug_output_dir(cls, output_dir: Any) -> None:
        """Set directory for saving debug images."""
        cls._debug_output_dir = output_dir

    @classmethod
    def _save_debug_image(cls, screenshot_bytes: bytes, detections: List[Any], prefix: str = "ocr", timestamp: str = None) -> None:
        """Save screenshot with annotated detections if debug dir is set."""
        if not cls._debug_output_dir:
            return

        try:
            # cv2 and numpy are already imported at the top
            
            # Decode image
            nparr = np.frombuffer(screenshot_bytes, np.uint8)
            img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)

            # Draw detections
            for detection in detections:
                box, (text, score) = detection
                box = np.array(box).astype(np.int32).reshape((-1, 1, 2))
                
                # Draw bounding box (Red)
                cv2.polylines(img, [box], True, (0, 0, 255), 2)
                
                # Draw text and score (Blue)
                # Ensure text is clean string
                display_text = f"{text} ({score:.2f})"
                x, y = box[0][0]
                cv2.putText(img, display_text, (int(x), int(y) - 5), 
                           cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 0, 0), 1)

            # Generate timestamp if not provided
            if timestamp is None:
                timestamp = datetime.now().strftime("%H%M%S_%f")

            # Save to file
            filename = f"{prefix}_{timestamp}.png"
            filepath = cls._debug_output_dir / filename
            
            cv2.imwrite(str(filepath), img)
            log.info(f"Saved OCR debug image to {filepath}")

        except Exception as e:
            log.warning(f"Failed to save OCR debug image: {e}")

    @classmethod
    def _save_debug_csv(cls, detections: List[Any], prefix: str = "ocr", timestamp: str = None) -> None:
        """Save detection data to CSV if debug dir is set.

        Args:
            detections: List of (box, (text, score)) tuples from PaddleOCR
            prefix: Operation name (e.g., "get_all_text", "find_text_Login")
            timestamp: Timestamp string matching screenshot filename (format: HHMMSS_microseconds)
        """
        if not cls._debug_output_dir:
            return

        try:
            import csv

            # Generate timestamp if not provided
            if timestamp is None:
                timestamp = datetime.now().strftime("%H%M%S_%f")

            # Construct filenames
            csv_filename = f"{prefix}_{timestamp}.csv"
            png_filename = f"{prefix}_{timestamp}.png"
            csv_filepath = cls._debug_output_dir / csv_filename

            # Write CSV file
            with open(csv_filepath, 'w', newline='', encoding='utf-8') as csvfile:
                writer = csv.writer(csvfile)

                # Write header
                writer.writerow([
                    'operation', 'timestamp', 'screenshot_file',
                    'text', 'confidence',
                    'center_x', 'center_y',
                    'box_x1', 'box_y1', 'box_x2', 'box_y2',
                    'box_x3', 'box_y3', 'box_x4', 'box_y4'
                ])

                # Write detections
                for detection in detections:
                    box, (text, score) = detection

                    # Calculate center point
                    center_x, center_y = OCRProcessor.calculate_text_center(box)

                    # Extract box coordinates (4 corner points)
                    box_x1, box_y1 = int(box[0][0]), int(box[0][1])
                    box_x2, box_y2 = int(box[1][0]), int(box[1][1])
                    box_x3, box_y3 = int(box[2][0]), int(box[2][1])
                    box_x4, box_y4 = int(box[3][0]), int(box[3][1])

                    # Write row
                    writer.writerow([
                        prefix,
                        timestamp,
                        png_filename,
                        text,
                        f"{score:.4f}",
                        center_x,
                        center_y,
                        box_x1, box_y1,
                        box_x2, box_y2,
                        box_x3, box_y3,
                        box_x4, box_y4
                    ])

            log.info(f"Saved OCR debug CSV to {csv_filepath}")

        except Exception as e:
            log.warning(f"Failed to save OCR debug CSV: {e}")

    @staticmethod
    async def get_all_text(
        screenshot_bytes: bytes,
        offset_x: int = 0,
        offset_y: int = 0,
        output_format: str = "json"
    ) -> Dict[str, Any]:
        """Get all detected text from screenshot data."""
        log.info("Starting OCR to get all detected text")

        try:
            result = await OCRProcessor.process_screenshot(screenshot_bytes)

            # Save debug output with matching timestamps
            timestamp = datetime.now().strftime("%H%M%S_%f")
            TextDetector._save_debug_image(screenshot_bytes, result, "get_all_text", timestamp)
            TextDetector._save_debug_csv(result, "get_all_text", timestamp)

        except Exception as e:
            log.error(f"OCR processing failed: {e}", exc_info=True)
            return {
                "error": f"OCR processing failed: {str(e)}",
                "all_text": []
            }

        # Process all detected text with locations
        all_text = []
        for detection in result:
            box, (text_rec, confidence) = detection
            center_x, center_y = OCRProcessor.calculate_text_center(box, offset_x, offset_y)

            all_text.append({
                "text": text_rec,
                "confidence": float(confidence),
                "x": center_x,
                "y": center_y,
            })

        log.info(f"Found {len(all_text)} total text detections")

        return TextDetector._format_output(all_text, output_format)

    @staticmethod
    def _calculate_box_dimensions(box: List[List[float]]) -> Tuple[int, int]:
        """Calculate width and height from bounding box."""
        x_coords = [point[0] for point in box]
        y_coords = [point[1] for point in box]
        width = int(max(x_coords) - min(x_coords))
        height = int(max(y_coords) - min(y_coords))
        return width, height

    @staticmethod
    async def find_text(
        text: str,
        screenshot_bytes: bytes,
        offset_x: int = 0,
        offset_y: int = 0,
        output_format: str = "json",
        match_mode: str = "substring",
        regex_flags: Optional[List[str]] = None,
        allow_missing_chars: Optional[Union[bool, str, List[str]]] = None,
        max_missing: Optional[int] = None,
        min_similarity: Optional[float] = None,
        case_sensitive: bool = False
    ) -> Dict[str, Any]:
        """Find specific text locations in screenshot data with advanced matching.

        Args:
            text: Text or pattern to search for
            screenshot_bytes: Screenshot image bytes
            offset_x: X offset to add to coordinates
            offset_y: Y offset to add to coordinates
            output_format: Output format ("json" or "csv")
            match_mode: Matching mode ("substring", "regex", "fuzzy", "regex_fuzzy")
            regex_flags: List of regex flag names (for regex modes)
            allow_missing_chars: Allowed missing characters (fuzzy mode):
                - True: Allow any character to be missing
                - ".": Only allow this specific character to be missing
                - [".", ","]: Only allow these characters to be missing
            max_missing: Max missing chars allowed (fuzzy mode)
            min_similarity: Minimum similarity ratio 0.0-1.0 (fuzzy mode)
            case_sensitive: Enable case-sensitive matching

        Returns:
            Dictionary with locations and confidences
        """
        log.info(f"Starting text search for: '{text}' (mode: {match_mode})")

        try:
            result = await OCRProcessor.process_screenshot(screenshot_bytes)

            # Save debug output with matching timestamps
            timestamp = datetime.now().strftime("%H%M%S_%f")
            prefix = f"find_text_{text}"
            TextDetector._save_debug_image(screenshot_bytes, result, prefix, timestamp)
            TextDetector._save_debug_csv(result, prefix, timestamp)

        except Exception as e:
            log.error(f"OCR processing failed: {e}", exc_info=True)
            return {
                "error": f"OCR processing failed: {str(e)}",
                "locations": []
            }

        # Log all detected text for debugging
        log.info(f"CLAUDE: OCR detected {len(result)} text elements while searching for '{text}':")
        for detection in result:
            box, (text_rec, confidence) = detection
            center_x, center_y = OCRProcessor.calculate_text_center(box)
            log.info(f"CLAUDE:   '{text_rec}' (conf: {confidence:.3f}) at ({center_x}, {center_y})")

        # Find all detections that match the text using specified mode
        matches = []
        for detection in result:
            box, (text_rec, confidence) = detection

            # Apply matching strategy
            matched = False
            if match_mode == "substring":
                # Preserve current behavior - case-insensitive substring match
                matched = text.lower() in text_rec.lower()
            elif match_mode == "regex":
                matched = TextMatcher.regex_match(text, text_rec, regex_flags)
            elif match_mode == "fuzzy":
                matched = FuzzyMatcher.fuzzy_match(
                    text, text_rec, allow_missing_chars, max_missing, min_similarity, case_sensitive
                )
            elif match_mode == "regex_fuzzy":
                matched = FuzzyMatcher.regex_fuzzy_match(
                    text, text_rec, regex_flags, min_similarity or 0.8, case_sensitive
                )
            else:
                log.warning(f"Unknown match_mode '{match_mode}', falling back to substring")
                matched = text.lower() in text_rec.lower()

            if matched:
                center_x, center_y = OCRProcessor.calculate_text_center(box, offset_x, offset_y)
                width, height = TextDetector._calculate_box_dimensions(box)

                matches.append({
                    "text": text_rec,
                    "confidence": float(confidence),
                    "x": center_x,
                    "y": center_y,
                    "width": width,
                    "height": height
                })

        log.info(f"Found {len(matches)} text matches (mode: {match_mode})")

        if output_format.lower() == "csv":
            return TextDetector._format_csv_output(matches)
        else:
            return TextDetector._format_json_text_output(matches)

    @staticmethod
    def _format_output(all_text: List[Dict[str, Any]], output_format: str) -> Dict[str, Any]:
        """Format output based on requested format."""
        if output_format.lower() == "csv":
            return TextDetector._format_csv_output(all_text)
        else:
            return {
                "format": "json",
                "all_text": all_text
            }

    @staticmethod
    def _format_csv_output(text_data: List[Dict[str, Any]]) -> Dict[str, str]:
        """Format text data as CSV."""
        csv_output = io.StringIO()
        csv_output.write(f"{OCRConstants.CSV_HEADER}\n")

        for item in text_data:
            # Escape quotes in text by doubling them, wrap in quotes
            escaped_text = item["text"].replace('"', '""')
            csv_output.write(f'"{escaped_text}",{item["x"]},{item["y"]},{item["confidence"]}\n')

        return {
            "format": "csv",
            "data": csv_output.getvalue()
        }

    @staticmethod
    def _format_json_text_output(matches: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Format text matches in JSON format for backward compatibility."""
        locations = []
        confidences = []

        for match in matches:
            loc_data = {
                "text": match["text"],
                "location": {
                    "x": match["x"],
                    "y": match["y"],
                }
            }
            if "width" in match:
                loc_data["location"]["width"] = match["width"]
            if "height" in match:
                loc_data["location"]["height"] = match["height"]
                
            locations.append(loc_data)
            confidences.append(match["confidence"])

        return {
            "format": "json",
            "locations": locations,
            "confidences": confidences
        }