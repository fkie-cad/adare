"""
Visual test functions for ADARE.

These test functions execute on the HOST (not VM) and use the CV server
to perform visual analysis of screenshots for text/icon detection.
"""

from pathlib import Path
import logging

from adarelib.testset.api import testfunction
from adarelib.testset.basictest import HostModeCategory
from adarelib.event.event import TestResult

log = logging.getLogger(__name__)


# =============================================================================
# Helper: find visual element (text or image) in a screenshot
# =============================================================================

async def _find_visual_element(ctx, text, image, window, icon=None):
    """
    Take a screenshot and search for a text, icon-library, or image element.

    Exactly one of ``text``, ``icon``, or ``image`` selects the search mode:
      - ``text``:  OCR search for a string.
      - ``icon``:  a name from the Windows icon library (e.g. ``recycle_bin``).
                   The correct icon is extracted from the target at runtime,
                   cached, and matched -- no PNG is shipped in the playbook.
      - ``image``: a PNG file path relative to the playbook directory.

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
    elif icon:
        icon_result = await _resolve_icon_path(ctx, icon)
        if isinstance(icon_result, TestResult):
            return icon_result
        icon_path = icon_result
        log.debug(f"Visual test: Searching for icon '{icon}' ({icon_path.name})")
        locations = await ctx.host.cv.find_icon(icon_path, screenshot)
        target_desc = f"icon '{icon}'"
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


async def _resolve_icon_path(ctx, icon):
    """Resolve an icon-library term to a cached PNG path (extract on miss).

    Returns the Path, or a TestResult.execution_error if the icon library is
    unavailable or resolution fails.
    """
    from adare.backend.experiment.icon_library import IconLibraryError

    if getattr(ctx.host, 'icons', None) is None:
        return TestResult.execution_error(
            RuntimeError("Icon library unavailable (no connected target/agent)"),
            f"Cannot resolve icon '{icon}': icon library not available in this run mode",
        )
    try:
        return await ctx.host.icons.resolve(icon)
    except IconLibraryError as exc:
        return TestResult.execution_error(exc, f"Icon '{icon}' could not be resolved: {exc}")


# =============================================================================
# Visual Test Functions
# =============================================================================

@testfunction(
    name='visual.exists',
    description='Check if text or image is visible on screen',
    category=HostModeCategory.HOST_NATIVE,
    execute_on_host=True,
)
async def visual_exists(ctx, text: str = None, image: str = None, icon: str = None, window: str = None):
    ctx.error_if(not text and not image and not icon, "One of text, image, or icon parameter required")

    result = await _find_visual_element(ctx, text, image, window, icon)

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
async def visual_not_exists(ctx, text: str = None, image: str = None, icon: str = None, window: str = None):
    ctx.error_if(not text and not image and not icon, "One of text, image, or icon parameter required")

    result = await _find_visual_element(ctx, text, image, window, icon)

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
async def visual_count_equals(
    ctx, text: str = None, image: str = None, icon: str = None, window: str = None, n: int = None,
):
    ctx.error_if(not text and not image and not icon, "One of text, image, or icon parameter required")
    ctx.error_if(n is None, "Parameter 'n' required for count_equals test")

    result = await _find_visual_element(ctx, text, image, window, icon)

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
async def visual_count_min(
    ctx, text: str = None, image: str = None, icon: str = None, window: str = None, min: int = None,
):
    ctx.error_if(not text and not image and not icon, "One of text, image, or icon parameter required")
    ctx.error_if(min is None, "Parameter 'min' required for count_min test")

    result = await _find_visual_element(ctx, text, image, window, icon)

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
async def visual_count_max(
    ctx, text: str = None, image: str = None, icon: str = None, window: str = None, max: int = None,
):
    ctx.error_if(not text and not image and not icon, "One of text, image, or icon parameter required")
    ctx.error_if(max is None, "Parameter 'max' required for count_max test")

    result = await _find_visual_element(ctx, text, image, window, icon)

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
