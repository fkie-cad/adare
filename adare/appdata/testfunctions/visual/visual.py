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
    """Pass when the given text, icon or image is found on a fresh screenshot of the guest.

    Use for: confirming a GUI state (dialog shown, file icon on the desktop). Runs on the host
    via the CV server. At least one of ``text``/``icon``/``image`` is required (none -> error).
    Opposite: visual.not_exists.

    Args:
        text: OCR search string: case-insensitive substring of a single OCR text box (a
            phrase split across boxes may not match). Wins over ``icon`` and ``image``.
        image: Template PNG on the HOST, relative to the playbook directory (or absolute);
            matched with the CV server's icon pipeline. A missing file is an execution error.
        icon: Name from the icon library (``appdata/icon-library.yml``, e.g. ``recycle_bin``,
            ``folder``), extracted from the target on first use; needs a connected agent.
            Used when ``text`` is empty; wins over ``image``.
        window: Capture only the first window whose title matches this search string (Linux
            guests; Windows currently captures the full screen). ``None`` = full screen;
            no matching window is an execution error.

    Example:
        function: visual.exists
        parameter:
          text: Document saved
    """
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
    """Pass when the given text, icon or image is NOT found on a fresh screenshot of the guest.

    Use for: confirming a dialog closed or an item disappeared. Opposite: visual.exists.
    At least one of ``text``/``icon``/``image`` is required (none -> error).

    Args:
        text: OCR search string: case-insensitive substring of a single OCR text box (a
            phrase split across boxes may not match). Wins over ``icon`` and ``image``.
        image: Template PNG on the HOST, relative to the playbook directory (or absolute);
            matched with the CV server's icon pipeline. A missing file is an execution error.
        icon: Name from the icon library (``appdata/icon-library.yml``, e.g. ``recycle_bin``,
            ``folder``), extracted from the target on first use; needs a connected agent.
            Used when ``text`` is empty; wins over ``image``.
        window: Capture only the first window whose title matches this search string (Linux
            guests; Windows currently captures the full screen). ``None`` = full screen;
            no matching window is an execution error.

    Example:
        function: visual.not_exists
        parameter:
          icon: recycle_bin_full
    """
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
    ctx,
    text: str = None,
    image: str = None,
    icon: str = None,
    window: str = None,
    n: int = None,
):
    """Pass when the text, icon or image is found exactly ``n`` times on the screenshot.

    Use for: counting visible items (e.g. 3 files on the desktop).
    Icon/image matches are capped at 10 by the CV call, so counts above 10 cannot be observed.

    Args:
        text: OCR search string: case-insensitive substring of a single OCR text box (a
            phrase split across boxes may not match). Wins over ``icon`` and ``image``.
        image: Template PNG on the HOST, relative to the playbook directory (or absolute);
            matched with the CV server's icon pipeline. A missing file is an execution error.
        icon: Name from the icon library (``appdata/icon-library.yml``, e.g. ``recycle_bin``,
            ``folder``), extracted from the target on first use; needs a connected agent.
            Used when ``text`` is empty; wins over ``image``.
        window: Capture only the first window whose title matches this search string (Linux
            guests; Windows currently captures the full screen). ``None`` = full screen;
            no matching window is an execution error.
        n: Required exact number of matches (``None`` -> error).

    Example:
        function: visual.count_equals
        parameter:
          image: icons/odt_file.png
          n: 3
    """
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
    ctx,
    text: str = None,
    image: str = None,
    icon: str = None,
    window: str = None,
    min: int = None,
):
    """Pass when the text, icon or image is found at least ``min`` times on the screenshot.

    Use for: "at least N items visible".
    Icon/image matches are capped at 10 by the CV call, so counts above 10 cannot be observed.

    Args:
        text: OCR search string: case-insensitive substring of a single OCR text box (a
            phrase split across boxes may not match). Wins over ``icon`` and ``image``.
        image: Template PNG on the HOST, relative to the playbook directory (or absolute);
            matched with the CV server's icon pipeline. A missing file is an execution error.
        icon: Name from the icon library (``appdata/icon-library.yml``, e.g. ``recycle_bin``,
            ``folder``), extracted from the target on first use; needs a connected agent.
            Used when ``text`` is empty; wins over ``image``.
        window: Capture only the first window whose title matches this search string (Linux
            guests; Windows currently captures the full screen). ``None`` = full screen;
            no matching window is an execution error.
        min: Required minimum number of matches, inclusive (``None`` -> error).

    Example:
        function: visual.count_min
        parameter:
          text: Untitled
          min: 2
    """
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
    ctx,
    text: str = None,
    image: str = None,
    icon: str = None,
    window: str = None,
    max: int = None,
):
    """Pass when the text, icon or image is found at most ``max`` times on the screenshot.

    Use for: "no more than N items visible"; ``max: 0`` behaves like visual.not_exists.
    Icon/image matches are capped at 10 by the CV call, so counts above 10 cannot be observed.

    Args:
        text: OCR search string: case-insensitive substring of a single OCR text box (a
            phrase split across boxes may not match). Wins over ``icon`` and ``image``.
        image: Template PNG on the HOST, relative to the playbook directory (or absolute);
            matched with the CV server's icon pipeline. A missing file is an execution error.
        icon: Name from the icon library (``appdata/icon-library.yml``, e.g. ``recycle_bin``,
            ``folder``), extracted from the target on first use; needs a connected agent.
            Used when ``text`` is empty; wins over ``image``.
        window: Capture only the first window whose title matches this search string (Linux
            guests; Windows currently captures the full screen). ``None`` = full screen;
            no matching window is an execution error.
        max: Allowed maximum number of matches, inclusive (``None`` -> error).

    Example:
        function: visual.count_max
        parameter:
          icon: folder
          max: 5
    """
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
