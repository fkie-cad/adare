import asyncio
import importlib.util

import cv2
import numpy as np
import pytest
from adare_cv_server import ocr_engines
from adare_cv_server.ocr_processing import OCRProcessor


@pytest.fixture(params=['rapidocr', 'paddle'])
def ocr_engine(request):
    """Run against each OCR engine; paddle only when the `paddle` extra is installed."""
    if request.param == 'paddle' and importlib.util.find_spec('paddleocr') is None:
        pytest.skip("paddle extra not installed")
    previous = ocr_engines._engine
    ocr_engines.configure_engine(request.param)
    yield request.param
    ocr_engines._engine = previous


# Helper to create image bytes
def create_test_image_bytes(gap=30):
    img = np.ones((100, 800, 3), dtype=np.uint8) * 255
    start_x = 50
    cv2.putText(img, "Label", (start_x, 60), cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 0, 0), 2)
    label_size = cv2.getTextSize("Label", cv2.FONT_HERSHEY_SIMPLEX, 1, 2)[0]
    end_x = start_x + label_size[0]
    second_word_x = end_x + gap
    cv2.putText(img, "Value", (second_word_x, 60), cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 0, 0), 2)

    is_success, buffer = cv2.imencode(".png", img)
    return buffer.tobytes()


# Smallest gap (px, ~22 px glyphs) each engine must keep as two detections. PaddleOCR's
# server detector splits at 30 px; RapidOCR's mobile detector merges up to ~30 px and
# splits from 40 px (measured 2026-11-01) - a known profile difference, not a bug.
SEPARATION_GAP = {'paddle': 30, 'rapidocr': 40}


def test_ocr_separation_at_gap(ocr_engine):
    """Verify that two words SEPARATION_GAP[engine] apart are separated."""
    asyncio.run(_run_test_ocr_separation(SEPARATION_GAP[ocr_engine]))


async def _run_test_ocr_separation(gap=30):
    # Based on reproduction, 20px was merged even at 1.2.
    # BUT we want to ensure 30px is separated (which was merged at 1.5 but separated at 1.2).
    # Let's test 30px gap separation.

    screenshot_bytes = create_test_image_bytes(gap=gap)

    detections = await OCRProcessor.process_screenshot(screenshot_bytes)

    # Flatten texts
    texts = [d[1][0] for d in detections]

    # We expect "Label" and "Value" to be separate
    # detections format: List[Tuple[box, Tuple[text, score]]]

    print(f"Detected texts: {texts}")

    # Check that we have at least 2 detected items
    # Or check that "LabelValue" is NOT in the texts

    assert len(texts) >= 2, f"Expected at least 2 detections, got {len(texts)}: {texts}"
    assert "Label" in texts or any("Label" in t for t in texts)
    assert "Value" in texts or any("Value" in t for t in texts)

    # Explicitly check against merging
    assert "LabelValue" not in texts, "Words were merged into a single detection"


if __name__ == "__main__":
    asyncio.run(_run_test_ocr_separation())
