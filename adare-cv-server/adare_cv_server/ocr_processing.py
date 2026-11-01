"""OCR processing: per-frame cached OCR, text matching and search."""

import asyncio
import hashlib
import io
import logging
import re
import time
from collections import OrderedDict
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from typing import Any

import cv2
import numpy as np

from .constants import OCRConstants, OCRProfiles
from .exceptions import OCRProcessingError
from .ocr_engines import OcrEngine, fingerprint_key, get_engine

log = logging.getLogger(__name__)

# One executor for the process instead of a fresh ThreadPoolExecutor (thread
# start + join) per OCR call. It also bounds how many OCR predictions run at once
# on the shared engine instance to MAX_WORKERS.
_OCR_EXECUTOR = ThreadPoolExecutor(max_workers=OCRConstants.MAX_WORKERS, thread_name_prefix='ocr')


def decode_screenshot(screenshot_bytes: bytes) -> np.ndarray:
    """Decode PNG/JPEG/BMP (or SVG, rasterized first) screenshot bytes to a BGR image."""
    if screenshot_bytes[:200].decode('utf-8', errors='ignore').strip().lower().startswith(('<?xml', '<svg')):
        try:
            import cairosvg
        except ImportError as e:
            raise OCRProcessingError("CairoSVG library required for SVG support. Install: pip install cairosvg") from e
        log.info("Detected SVG format, converting to PNG for OCR")
        try:
            screenshot_bytes = cairosvg.svg2png(bytestring=screenshot_bytes)
        except (ValueError, OSError) as e:
            raise OCRProcessingError(f"SVG conversion failed: {e}") from e

    img = cv2.imdecode(np.frombuffer(screenshot_bytes, np.uint8), cv2.IMREAD_COLOR)
    if img is None:
        raise OCRProcessingError("Could not decode screenshot image data")
    return img


class _OcrResultCache:
    """LRU of OCR results per (screenshot bytes, engine fingerprint), single-flight.

    The same frame is OCR'd repeatedly by the client (multi-leaf wait_until, `when`
    conditions, ClosestTo reference + target, failure evidence, polling an
    unchanged screen). A hit returns exactly what a fresh run would, because the key
    covers the bytes and everything that determines the engine's output.
    Concurrent requests for the same key await one computation.
    """

    def __init__(self, maxsize: int):
        self.maxsize = maxsize
        self._results: OrderedDict[str, list[Any]] = OrderedDict()
        self._inflight: dict[str, asyncio.Future] = {}
        self.hits = 0
        self.misses = 0

    def clear(self) -> None:
        self._results.clear()
        self._inflight.clear()

    async def get_or_compute(self, key: str, compute) -> list[Any]:
        if key in self._results:
            self._results.move_to_end(key)
            self.hits += 1
            log.info(f"OCR cache hit ({self.hits} hits / {self.misses} misses)")
            return self._results[key]

        loop = asyncio.get_running_loop()
        pending = self._inflight.get(key)
        # A future from another (finished) event loop - e.g. an earlier asyncio.run()
        # by an in-process caller - can never complete here; recompute instead.
        if pending is not None and pending.get_loop() is loop:
            self.hits += 1
            log.info("OCR cache: awaiting identical in-flight request")
            return await asyncio.shield(pending)

        self.misses += 1
        future = loop.run_in_executor(_OCR_EXECUTOR, compute)
        self._inflight[key] = future
        try:
            result = await asyncio.shield(future)
        finally:
            if self._inflight.get(key) is future:
                del self._inflight[key]
        self._results[key] = result
        self._results.move_to_end(key)
        while len(self._results) > self.maxsize:
            self._results.popitem(last=False)
        return result


class OCRProcessor:
    """Runs the process's pinned OCR engine (see ocr_engines) with a per-frame cache."""

    _cache = _OcrResultCache(OCRConstants.OCR_CACHE_SIZE)

    @staticmethod
    def _run_engine(engine: OcrEngine, screenshot_bytes: bytes) -> list[tuple[list[list[float]], tuple[str, float]]]:
        """Decode and OCR one screenshot (runs on the OCR executor)."""
        img = decode_screenshot(screenshot_bytes)
        log.info(f"Running OCR ({engine.profile}) on {img.shape[1]}x{img.shape[0]} image...")
        started = time.perf_counter()
        detections = engine.detect(img)
        log.info(
            f"OCR prediction completed in {time.perf_counter() - started:.3f}s"
            f" - found {len(detections)} text detections"
        )
        return detections

    @staticmethod
    async def process_screenshot(screenshot_bytes: bytes) -> list[tuple[list[list[float]], tuple[str, float]]]:
        """OCR a screenshot asynchronously; identical frames are served from the cache.

        The returned list is shared with the cache - callers must not mutate it.
        """
        engine = get_engine()
        key = f"{hashlib.sha256(screenshot_bytes).hexdigest()}:{fingerprint_key(engine)}"
        try:
            return await OCRProcessor._cache.get_or_compute(
                key, lambda: OCRProcessor._run_engine(engine, screenshot_bytes)
            )
        except OCRProcessingError:
            raise
        except Exception as e:
            # Engine boundary: PaddleOCR / onnxruntime raise arbitrary exception types.
            raise OCRProcessingError(f"OCR failed: {e}") from e

    @staticmethod
    def calculate_text_center(box: list[list[float]], offset_x: int = 0, offset_y: int = 0) -> tuple[int, int]:
        """Calculate center coordinates from bounding box."""
        x_coords = [point[0] for point in box]
        y_coords = [point[1] for point in box]
        center_x = int(sum(x_coords) / len(x_coords)) + offset_x
        center_y = int(sum(y_coords) / len(y_coords)) + offset_y
        return center_x, center_y


class TextMatcher:
    """Text matching utilities supporting substring, regex, and fuzzy matching."""

    _regex_cache: dict[tuple[str, int], re.Pattern] = {}

    @classmethod
    def compile_regex(cls, pattern: str, flags: list[str] | None = None) -> re.Pattern | None:
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
                'VERBOSE': re.VERBOSE,
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
    def regex_match(cls, pattern: str, text: str, flags: list[str] | None = None) -> bool:
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
                if s1[i - 1] == s2[j - 1]:
                    dp[i][j] = dp[i - 1][j - 1]
                else:
                    dp[i][j] = 1 + min(
                        dp[i - 1][j],  # deletion
                        dp[i][j - 1],  # insertion
                        dp[i - 1][j - 1],  # substitution
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
        allow_missing_chars=None,  # Union[bool, str, List[str]]
        max_missing: int | None = None,
        min_similarity: float | None = None,
        case_sensitive: bool = False,
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
        flags: list[str] | None = None,
        min_similarity: float = 0.8,
        case_sensitive: bool = False,
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

    _debug_output_dir: Any | None = None

    @classmethod
    def set_debug_output_dir(cls, output_dir: Any) -> None:
        """Set directory for saving debug images."""
        cls._debug_output_dir = output_dir

    @classmethod
    def _save_debug_image(
        cls, screenshot_bytes: bytes, detections: list[Any], prefix: str = "ocr", timestamp: str = None
    ) -> None:
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
                cv2.putText(img, display_text, (int(x), int(y) - 5), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 0, 0), 1)

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
    def _save_debug_csv(cls, detections: list[Any], prefix: str = "ocr", timestamp: str = None) -> None:
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
                writer.writerow(
                    [
                        'operation',
                        'timestamp',
                        'screenshot_file',
                        'text',
                        'confidence',
                        'center_x',
                        'center_y',
                        'box_x1',
                        'box_y1',
                        'box_x2',
                        'box_y2',
                        'box_x3',
                        'box_y3',
                        'box_x4',
                        'box_y4',
                    ]
                )

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
                    writer.writerow(
                        [
                            prefix,
                            timestamp,
                            png_filename,
                            text,
                            f"{score:.4f}",
                            center_x,
                            center_y,
                            box_x1,
                            box_y1,
                            box_x2,
                            box_y2,
                            box_x3,
                            box_y3,
                            box_x4,
                            box_y4,
                        ]
                    )

            log.info(f"Saved OCR debug CSV to {csv_filepath}")

        except Exception as e:
            log.warning(f"Failed to save OCR debug CSV: {e}")

    @staticmethod
    async def get_all_text(
        screenshot_bytes: bytes, offset_x: int = 0, offset_y: int = 0, output_format: str = "json"
    ) -> dict[str, Any]:
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
            return {"error": f"OCR processing failed: {str(e)}", "all_text": []}

        # Process all detected text with locations
        all_text = []
        for detection in result:
            box, (text_rec, confidence) = detection
            center_x, center_y = OCRProcessor.calculate_text_center(box, offset_x, offset_y)

            all_text.append(
                {
                    "text": text_rec,
                    "confidence": float(confidence),
                    "x": center_x,
                    "y": center_y,
                }
            )

        log.info(f"Found {len(all_text)} total text detections")

        return TextDetector._format_output(all_text, output_format)

    @staticmethod
    def _calculate_box_dimensions(box: list[list[float]]) -> tuple[int, int]:
        """Calculate width and height from bounding box."""
        x_coords = [point[0] for point in box]
        y_coords = [point[1] for point in box]
        width = int(max(x_coords) - min(x_coords))
        height = int(max(y_coords) - min(y_coords))
        return width, height

    MATCH_MODES = ("substring", "regex", "fuzzy", "regex_fuzzy")
    _LEADING_GLYPHS = re.compile(OCRProfiles.LEADING_GLYPH_PATTERN)

    @staticmethod
    def _match_candidates(text_rec: str, glyph_tolerance: bool) -> list[str]:
        """The OCR line, plus - with leading-glyph tolerance - the line without one
        leading run of 1-2 non-word glyphs (tree arrows read as '>', bullets, stars)."""
        if glyph_tolerance:
            stripped = TextDetector._LEADING_GLYPHS.sub('', text_rec, count=1)
            if stripped and stripped != text_rec:
                return [text_rec, stripped]
        return [text_rec]

    @staticmethod
    def _line_matches(
        text: str,
        text_rec: str,
        match_mode: str,
        regex_flags: list[str] | None,
        allow_missing_chars: bool | str | list[str] | None,
        max_missing: int | None,
        min_similarity: float | None,
        case_sensitive: bool,
    ) -> bool:
        """Whether one OCR line matches the query under ``match_mode``."""
        if match_mode == "regex":
            return TextMatcher.regex_match(text, text_rec, regex_flags)
        if match_mode == "fuzzy":
            return FuzzyMatcher.fuzzy_match(
                text, text_rec, allow_missing_chars, max_missing, min_similarity, case_sensitive
            )
        if match_mode == "regex_fuzzy":
            return FuzzyMatcher.regex_fuzzy_match(text, text_rec, regex_flags, min_similarity or 0.8, case_sensitive)
        # substring: case-insensitive containment
        return text.lower() in text_rec.lower()

    @staticmethod
    async def find_text(
        text: str,
        screenshot_bytes: bytes,
        offset_x: int = 0,
        offset_y: int = 0,
        output_format: str = "json",
        match_mode: str = "substring",
        regex_flags: list[str] | None = None,
        allow_missing_chars: bool | str | list[str] | None = None,
        max_missing: int | None = None,
        min_similarity: float | None = None,
        case_sensitive: bool = False,
    ) -> dict[str, Any]:
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
            return {"error": f"OCR processing failed: {str(e)}", "locations": []}

        # Log all detected text for debugging
        log.info(f"CLAUDE: OCR detected {len(result)} text elements while searching for '{text}':")
        for detection in result:
            box, (text_rec, confidence) = detection
            center_x, center_y = OCRProcessor.calculate_text_center(box)
            log.info(f"CLAUDE:   '{text_rec}' (conf: {confidence:.3f}) at ({center_x}, {center_y})")

        # Find all detections that match the text using specified mode
        if match_mode not in TextDetector.MATCH_MODES:
            log.warning(f"Unknown match_mode '{match_mode}', falling back to substring")
            match_mode = "substring"
        glyph_tolerance = get_engine().glyph_tolerance
        matches = []
        for detection in result:
            box, (text_rec, confidence) = detection

            matched = any(
                TextDetector._line_matches(
                    text,
                    candidate,
                    match_mode,
                    regex_flags,
                    allow_missing_chars,
                    max_missing,
                    min_similarity,
                    case_sensitive,
                )
                for candidate in TextDetector._match_candidates(text_rec, glyph_tolerance)
            )

            if matched:
                center_x, center_y = OCRProcessor.calculate_text_center(box, offset_x, offset_y)
                width, height = TextDetector._calculate_box_dimensions(box)

                matches.append(
                    {
                        "text": text_rec,
                        "confidence": float(confidence),
                        "x": center_x,
                        "y": center_y,
                        "width": width,
                        "height": height,
                    }
                )

        log.info(f"Found {len(matches)} text matches (mode: {match_mode})")

        if output_format.lower() == "csv":
            return TextDetector._format_csv_output(matches)
        return TextDetector._format_json_text_output(matches)

    @staticmethod
    def _format_output(all_text: list[dict[str, Any]], output_format: str) -> dict[str, Any]:
        """Format output based on requested format."""
        if output_format.lower() == "csv":
            return TextDetector._format_csv_output(all_text)
        return {"format": "json", "all_text": all_text}

    @staticmethod
    def _format_csv_output(text_data: list[dict[str, Any]]) -> dict[str, str]:
        """Format text data as CSV."""
        csv_output = io.StringIO()
        csv_output.write(f"{OCRConstants.CSV_HEADER}\n")

        for item in text_data:
            # Escape quotes in text by doubling them, wrap in quotes
            escaped_text = item["text"].replace('"', '""')
            csv_output.write(f'"{escaped_text}",{item["x"]},{item["y"]},{item["confidence"]}\n')

        return {"format": "csv", "data": csv_output.getvalue()}

    @staticmethod
    def _format_json_text_output(matches: list[dict[str, Any]]) -> dict[str, Any]:
        """Format text matches in JSON format for backward compatibility."""
        locations = []
        confidences = []

        for match in matches:
            loc_data = {
                "text": match["text"],
                "location": {
                    "x": match["x"],
                    "y": match["y"],
                },
            }
            if "width" in match:
                loc_data["location"]["width"] = match["width"]
            if "height" in match:
                loc_data["location"]["height"] = match["height"]

            locations.append(loc_data)
            confidences.append(match["confidence"])

        return {"format": "json", "locations": locations, "confidences": confidences}
