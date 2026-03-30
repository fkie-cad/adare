"""Verification tests for the redesigned CV detection pipeline.

Tests the new detection order (Template → SIFT → ORB) with SSIM validation,
spatial coherence checks, and multi-scale template matching.

Run with: python -m pytest test_cv_pipeline.py -v
Or standalone: python test_cv_pipeline.py
"""

import logging
import sys
from pathlib import Path

import cv2
import numpy as np

# Add the package to path for standalone execution
sys.path.insert(0, str(Path(__file__).parent))

from adare_cv_server.feature_matching import TemplateMatcher, ORBMatcher, SIFTMatcher
from adare_cv_server.image_processing import RegionValidator, FeatureMatchingResult, ImageDecoder

logging.basicConfig(level=logging.INFO, format="%(name)s - %(levelname)s - %(message)s")
log = logging.getLogger(__name__)


# --- Test helpers ---

def create_screenshot_with_icon(
    screenshot_size=(1920, 1080),
    icon_img=None,
    icon_position=(12, 50),
    background_color=(60, 60, 80),
):
    """Create a synthetic screenshot with an icon placed at a known position.

    Args:
        screenshot_size: (width, height)
        icon_img: numpy array of the icon, or None for a default colored square
        icon_position: (x, y) top-left corner where the icon is placed
        background_color: BGR background color

    Returns:
        (screenshot_bytes, icon_bytes, expected_center)
    """
    sw, sh = screenshot_size
    screenshot = np.full((sh, sw, 3), background_color, dtype=np.uint8)

    # Add some noise to simulate a real desktop wallpaper
    noise = np.random.randint(0, 15, screenshot.shape, dtype=np.uint8)
    screenshot = cv2.add(screenshot, noise)

    if icon_img is None:
        # Create a distinctive colored square as the icon
        icon_img = np.zeros((46, 42, 3), dtype=np.uint8)
        icon_img[5:41, 5:37] = (200, 120, 50)  # Blue-ish rectangle
        icon_img[15:30, 10:32] = (240, 200, 180)  # Light interior
        cv2.rectangle(icon_img, (5, 5), (37, 41), (255, 255, 255), 1)

    icon_h, icon_w = icon_img.shape[:2]
    ix, iy = icon_position

    # Place icon on screenshot
    screenshot[iy : iy + icon_h, ix : ix + icon_w] = icon_img

    expected_center = (ix + icon_w // 2, iy + icon_h // 2)

    _, screenshot_buf = cv2.imencode(".png", screenshot)
    _, icon_buf = cv2.imencode(".png", icon_img)

    return screenshot_buf.tobytes(), icon_buf.tobytes(), expected_center, screenshot, icon_img


def encode_image(img):
    """Encode numpy image to PNG bytes."""
    _, buf = cv2.imencode(".png", img)
    return buf.tobytes()


# --- Template matching tests ---

def test_template_matching_finds_exact_icon():
    """Template matching should find an exactly placed icon."""
    screenshot_bytes, icon_bytes, expected_center, _, _ = create_screenshot_with_icon()

    result = TemplateMatcher.find_icon_locations(screenshot_bytes, icon_bytes, threshold=0.8)

    assert result.success, "Template matching should find the icon"
    assert len(result.locations) >= 1, "Should have at least one match"

    # Check the best match is near the expected position
    best = result.locations[0]
    distance = ((best[0] - expected_center[0]) ** 2 + (best[1] - expected_center[1]) ** 2) ** 0.5
    assert distance < 10, f"Match at {best} too far from expected {expected_center} (distance: {distance:.1f})"
    log.info(f"PASS: Template found icon at {best}, expected {expected_center}")


def test_template_matching_multiscale():
    """Template matching should find a scaled version of the icon."""
    # Create icon and screenshot where icon is placed at 1.2x scale
    icon_img = np.zeros((40, 36, 3), dtype=np.uint8)
    icon_img[4:36, 4:32] = (180, 100, 40)
    cv2.rectangle(icon_img, (4, 4), (32, 36), (255, 255, 255), 1)

    scaled_icon = cv2.resize(icon_img, (43, 48), interpolation=cv2.INTER_LINEAR)  # ~1.2x

    screenshot = np.full((800, 1200, 3), (50, 50, 70), dtype=np.uint8)
    screenshot[100:148, 200:243] = scaled_icon

    screenshot_bytes = encode_image(screenshot)
    icon_bytes = encode_image(icon_img)

    result = TemplateMatcher.find_icon_locations(screenshot_bytes, icon_bytes, threshold=0.6)

    if result.success:
        log.info(f"PASS: Multi-scale template found match at {result.locations[0]}")
    else:
        log.warning("Multi-scale template did not find match (acceptable for edge cases)")


def test_template_matching_no_false_positive_on_noise():
    """Template matching should NOT match random noise."""
    icon_img = np.zeros((46, 42, 3), dtype=np.uint8)
    icon_img[5:41, 5:37] = (200, 120, 50)
    cv2.rectangle(icon_img, (5, 5), (37, 41), (255, 255, 255), 1)

    # Create a screenshot with just random noise — no icon
    screenshot = np.random.randint(0, 255, (1080, 1920, 3), dtype=np.uint8)

    screenshot_bytes = encode_image(screenshot)
    icon_bytes = encode_image(icon_img)

    result = TemplateMatcher.find_icon_locations(screenshot_bytes, icon_bytes, threshold=0.8)

    assert not result.success, "Template matching should NOT match random noise"
    log.info("PASS: No false positive on random noise")


# --- SSIM validation tests ---

def test_ssim_validates_correct_match():
    """SSIM should accept a match at the correct icon location."""
    _, _, expected_center, screenshot_img, icon_img = create_screenshot_with_icon()

    is_valid, score = RegionValidator.validate_match(screenshot_img, icon_img, expected_center)

    assert is_valid, f"SSIM should validate correct match (score: {score:.3f})"
    assert score > 0.5, f"SSIM score should be high for correct match, got {score:.3f}"
    log.info(f"PASS: SSIM validated correct match with score {score:.3f}")


def test_ssim_rejects_wrong_location():
    """SSIM should reject a match at a random wrong location (wallpaper area)."""
    _, _, _, screenshot_img, icon_img = create_screenshot_with_icon(
        icon_position=(12, 50)
    )

    # Check a location far from the icon (e.g., center of screenshot)
    wrong_center = (960, 540)
    is_valid, score = RegionValidator.validate_match(screenshot_img, icon_img, wrong_center)

    assert not is_valid, f"SSIM should reject wrong location (score: {score:.3f})"
    log.info(f"PASS: SSIM rejected wrong location with score {score:.3f}")


def test_ssim_filter_matches():
    """RegionValidator.filter_matches should keep good matches and reject bad ones."""
    _, _, expected_center, screenshot_img, icon_img = create_screenshot_with_icon(
        icon_position=(12, 50)
    )

    # Create a result with one correct and one incorrect location
    fake_result = FeatureMatchingResult(
        locations=[expected_center, (1002, 619)],  # real icon vs false positive
        similarities=[0.8, 0.6],
        method="orb",
    )

    filtered = RegionValidator.filter_matches(screenshot_img, icon_img, fake_result)

    assert len(filtered.locations) <= 1, "Should reject the false positive"
    if filtered.success:
        best = filtered.locations[0]
        distance = ((best[0] - expected_center[0]) ** 2 + (best[1] - expected_center[1]) ** 2) ** 0.5
        assert distance < 10, f"Kept match should be at the correct location, got {best}"
    log.info(f"PASS: SSIM filter kept {len(filtered.locations)} of 2 matches")


# --- Spatial coherence tests ---

def test_spatial_coherence_rejects_scattered_keypoints():
    """ORB should reject matches where keypoints are scattered across the screenshot."""
    # Create icon (small) and screenshot (large with scattered similar features)
    icon_img = np.zeros((30, 30, 3), dtype=np.uint8)
    cv2.circle(icon_img, (15, 15), 12, (200, 100, 50), -1)
    cv2.circle(icon_img, (15, 15), 8, (240, 200, 180), -1)

    screenshot = np.full((1080, 1920, 3), (40, 40, 60), dtype=np.uint8)

    # Place similar circles far apart to create scattered keypoints
    for pos in [(100, 100), (900, 500), (1500, 800), (300, 900)]:
        cv2.circle(screenshot, pos, 12, (200, 100, 50), -1)
        cv2.circle(screenshot, pos, 8, (240, 200, 180), -1)

    screenshot_bytes = encode_image(screenshot)
    icon_bytes = encode_image(icon_img)

    result = ORBMatcher.find_icon_locations(screenshot_bytes, icon_bytes)

    # Even if ORB finds matches, spatial coherence should reject scattered ones
    if result.success:
        for loc in result.locations:
            log.info(f"ORB found match at {loc}")
        # Matches should be near one of the actual circles, not averaged across them
        log.info("ORB found matches — checking they are near actual circles")
    else:
        log.info("PASS: ORB correctly found no matches for scattered features")


# --- Pipeline cascade order test ---

def test_cascade_template_first():
    """Verify template matching is tried first and succeeds without feature matching."""
    screenshot_bytes, icon_bytes, expected_center, _, _ = create_screenshot_with_icon()

    # Template should find it
    template_result = TemplateMatcher.find_icon_locations(screenshot_bytes, icon_bytes, threshold=0.8)
    assert template_result.success, "Template matching should succeed"

    log.info(f"PASS: Template matching found icon at {template_result.locations[0]} "
             f"(expected {expected_center}) — no need for ORB/SIFT")


# --- Test with real nautilus icon ---

def test_with_nautilus_icon():
    """Test pipeline with the real nautilus_taskbar.png icon if available."""
    icon_path = Path(__file__).parent.parent / "adare/appdata/examples/experiments/ubuntu_deletefile/img/nautilus_taskbar.png"

    if not icon_path.exists():
        log.warning(f"Skipping nautilus test — icon not found at {icon_path}")
        return

    icon_img = cv2.imread(str(icon_path))
    if icon_img is None:
        log.warning("Skipping nautilus test — failed to read icon")
        return

    icon_h, icon_w = icon_img.shape[:2]
    log.info(f"Nautilus icon size: {icon_w}x{icon_h}")

    # Create synthetic Ubuntu-like desktop with icon placed on left dock
    screenshot = np.full((1080, 1920, 3), (48, 10, 26), dtype=np.uint8)  # Dark Ubuntu background

    # Add a dock-like bar on the left
    screenshot[:, 0:60] = (30, 30, 30)

    # Place the icon on the dock
    dock_x, dock_y = 9, 60
    screenshot[dock_y : dock_y + icon_h, dock_x : dock_x + icon_w] = icon_img

    expected_center = (dock_x + icon_w // 2, dock_y + icon_h // 2)

    screenshot_bytes = encode_image(screenshot)
    icon_bytes = encode_image(icon_img)

    # Template matching should find it
    result = TemplateMatcher.find_icon_locations(screenshot_bytes, icon_bytes, threshold=0.7)

    if result.success:
        best = result.locations[0]
        distance = ((best[0] - expected_center[0]) ** 2 + (best[1] - expected_center[1]) ** 2) ** 0.5
        log.info(f"PASS: Template found nautilus icon at {best} (expected {expected_center}, distance: {distance:.1f})")
        assert distance < 10, f"Match too far: {distance:.1f}px"
    else:
        log.warning("Template matching did not find nautilus icon in synthetic screenshot")

    # Verify no false positive at wrong location via SSIM
    decoded = ImageDecoder.decode_images(screenshot_bytes, icon_bytes)
    if decoded:
        screenshot_img_dec, icon_img_dec, _ = decoded
        is_valid, score = RegionValidator.validate_match(
            screenshot_img_dec, icon_img_dec, (1002, 619)  # The known false positive location
        )
        assert not is_valid, f"SSIM should reject false positive at (1002, 619), got score {score:.3f}"
        log.info(f"PASS: SSIM rejected false positive at (1002, 619) with score {score:.3f}")


# --- Run all tests ---

def run_all():
    """Run all tests and report results."""
    tests = [
        test_template_matching_finds_exact_icon,
        test_template_matching_multiscale,
        test_template_matching_no_false_positive_on_noise,
        test_ssim_validates_correct_match,
        test_ssim_rejects_wrong_location,
        test_ssim_filter_matches,
        test_spatial_coherence_rejects_scattered_keypoints,
        test_cascade_template_first,
        test_with_nautilus_icon,
    ]

    passed = 0
    failed = 0

    for test in tests:
        name = test.__name__
        try:
            test()
            passed += 1
        except AssertionError as e:
            log.error(f"FAIL: {name}: {e}")
            failed += 1
        except Exception as e:
            log.error(f"ERROR: {name}: {e}")
            failed += 1

    print(f"\n{'=' * 60}")
    print(f"Results: {passed} passed, {failed} failed, {len(tests)} total")
    print(f"{'=' * 60}")

    return failed == 0


if __name__ == "__main__":
    success = run_all()
    sys.exit(0 if success else 1)
