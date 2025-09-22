"""OCR processing utilities using PaddleOCR."""

import logging
import io
import asyncio
from concurrent.futures import ThreadPoolExecutor
from typing import List, Dict, Any, Tuple, Union
import numpy as np
import cv2

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
            ocr = PaddleOCR(
                use_doc_orientation_classify=False,
                use_doc_unwarping=False,
                use_textline_orientation=False
            )

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


class TextDetector:
    """Handles text detection and search operations."""

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
    async def find_text(
        text: str,
        screenshot_bytes: bytes,
        offset_x: int = 0,
        offset_y: int = 0,
        output_format: str = "json"
    ) -> Dict[str, Any]:
        """Find specific text locations in screenshot data."""
        log.info(f"Starting text search for: '{text}'")

        try:
            result = await OCRProcessor.process_screenshot(screenshot_bytes)
        except Exception as e:
            log.error(f"OCR processing failed: {e}", exc_info=True)
            return {
                "error": f"OCR processing failed: {str(e)}",
                "locations": []
            }

        # Find all detections that contain the text
        matches = []
        for detection in result:
            box, (text_rec, confidence) = detection
            if text.lower() in text_rec.lower():
                center_x, center_y = OCRProcessor.calculate_text_center(box, offset_x, offset_y)

                matches.append({
                    "text": text_rec,
                    "confidence": float(confidence),
                    "x": center_x,
                    "y": center_y,
                })

        log.info(f"Found {len(matches)} text matches")

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
            locations.append({
                "text": match["text"],
                "location": {
                    "x": match["x"],
                    "y": match["y"],
                }
            })
            confidences.append(match["confidence"])

        return {
            "format": "json",
            "locations": locations,
            "confidences": confidences
        }