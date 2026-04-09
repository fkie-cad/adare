"""
Visual test functions for ADARE.

These test functions execute on the HOST (not VM) and use the CV server
to perform visual analysis of screenshots for text/icon detection.
"""

from pathlib import Path
import logging

from adarelib.testset import testfunction
from adarelib.testset.basictest import HostModeCategory
from adarelib.event.event import TestResult

log = logging.getLogger(__name__)


# =============================================================================
# Helper: find visual element (text or image) in a screenshot
# =============================================================================

async def _find_visual_element(ctx, text, image, window):
    """
    Take a screenshot and search for a text or image element.

    Returns:
        (locations, target_desc) - list of match locations and a human-readable description.

    Raises:
        FileNotFoundError with a specific message when the image file cannot be found.
    """
    screenshot = await ctx.host.screenshot.take(window=window)

    if text:
        log.debug(f"Visual test: Searching for text '{text}'")
        locations = await ctx.host.cv.find_text(text, screenshot)
        target_desc = f"text '{text}'"
    else:
        image_path = Path(image)
        if not image_path.is_absolute():
            image_path = ctx.host.playbook_dir / image_path

        log.debug(f"Visual test: Searching for image '{image_path.name}'")
        try:
            locations = await ctx.host.cv.find_icon(image_path, screenshot)
        except FileNotFoundError:
            return TestResult.execution_error(
                FileNotFoundError(f"Image file not found: {image}"),
                f"Image file not found: {image}",
            )
        target_desc = f"image '{image}'"

    return locations, target_desc


# =============================================================================
# Visual Test Functions
# =============================================================================

@testfunction(
    name='visual.exists',
    description='Check if text or image is visible on screen',
    category=HostModeCategory.HOST_NATIVE,
    execute_on_host=True,
)
async def visual_exists(ctx, text: str = None, image: str = None, window: str = None):
    ctx.error_if(not text and not image, "Either text or image parameter required")

    result = await _find_visual_element(ctx, text, image, window)

    # _find_visual_element returns TestResult on FileNotFoundError
    if isinstance(result, TestResult):
        return result

    locations, target_desc = result

    if locations:
        log.debug(f"Visual test: Found {len(locations)} matches")
    else:
        log.debug("Visual test: No matches found")

    ctx.fail_if(not locations, f"Visual element not found: {target_desc}")
    return TestResult.success()


@testfunction(
    name='visual.not_exists',
    description='Check if text or image is NOT visible on screen',
    category=HostModeCategory.HOST_NATIVE,
    execute_on_host=True,
)
async def visual_not_exists(ctx, text: str = None, image: str = None, window: str = None):
    ctx.error_if(not text and not image, "Either text or image parameter required")

    result = await _find_visual_element(ctx, text, image, window)

    if isinstance(result, TestResult):
        return result

    locations, target_desc = result

    if not locations:
        log.debug("Visual test: Confirmed element not present")
    else:
        log.debug(f"Visual test: Found {len(locations)} unexpected matches")

    ctx.fail_if(locations, f"Visual element should not exist but was found: {target_desc}")
    return TestResult.success()


@testfunction(
    name='visual.count_equals',
    description='Check if text or image appears exactly N times on screen',
    category=HostModeCategory.HOST_NATIVE,
    execute_on_host=True,
)
async def visual_count_equals(ctx, text: str = None, image: str = None, window: str = None, n: int = None):
    ctx.error_if(not text and not image, "Either text or image parameter required")
    ctx.error_if(n is None, "Parameter 'n' required for count_equals test")

    result = await _find_visual_element(ctx, text, image, window)

    if isinstance(result, TestResult):
        return result

    locations, target_desc = result
    actual_count = len(locations)

    log.debug(f"Visual test: Expected {n}, found {actual_count}")

    ctx.fail_if(
        actual_count != n,
        f"Visual element count mismatch for {target_desc}: expected {n}, found {actual_count}",
    )
    return TestResult.success()


@testfunction(
    name='visual.count_min',
    description='Check if text or image appears at least N times on screen',
    category=HostModeCategory.HOST_NATIVE,
    execute_on_host=True,
)
async def visual_count_min(ctx, text: str = None, image: str = None, window: str = None, min: int = None):
    ctx.error_if(not text and not image, "Either text or image parameter required")
    ctx.error_if(min is None, "Parameter 'min' required for count_min test")

    result = await _find_visual_element(ctx, text, image, window)

    if isinstance(result, TestResult):
        return result

    locations, target_desc = result
    actual_count = len(locations)

    log.debug(f"Visual test: Expected >= {min}, found {actual_count}")

    ctx.fail_if(
        actual_count < min,
        f"Visual element count below minimum for {target_desc}: expected >= {min}, found {actual_count}",
    )
    return TestResult.success()


@testfunction(
    name='visual.count_max',
    description='Check if text or image appears at most N times on screen',
    category=HostModeCategory.HOST_NATIVE,
    execute_on_host=True,
)
async def visual_count_max(ctx, text: str = None, image: str = None, window: str = None, max: int = None):
    ctx.error_if(not text and not image, "Either text or image parameter required")
    ctx.error_if(max is None, "Parameter 'max' required for count_max test")

    result = await _find_visual_element(ctx, text, image, window)

    if isinstance(result, TestResult):
        return result

    locations, target_desc = result
    actual_count = len(locations)

    log.debug(f"Visual test: Expected <= {max}, found {actual_count}")

    ctx.fail_if(
        actual_count > max,
        f"Visual element count exceeds maximum for {target_desc}: expected <= {max}, found {actual_count}",
    )
    return TestResult.success()
