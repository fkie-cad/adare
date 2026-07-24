# =============================================================================
# ADARE testfunction collection
# =============================================================================
#
# This file was scaffolded by `adare test create`. Each function decorated with
# @testfunction below becomes a named test you can reference from a playbook:
#
#     tests:
#       - name: check_for_keyword
#         function: mycollection.file_contains_word   # <collection>.<name>
#         parameter:
#           dst: "/evidence/logfile.txt"
#           word: "ERROR"
#           case_sensitive: false
#
# IMPORTANT rules (enforced at load / validate time):
#   * The .py file must be named exactly like its directory:
#         testfunctions/mycollection/mycollection.py   (dir == file stem)
#     A mismatch is skipped on load — `adare test validate <dir>` reports it.
#   * Every test function's first parameter must be `ctx`.
#   * Annotate every other parameter (`dst: str`, `count: int = 5`); the type
#     annotations drive cattrs validation of playbook `parameter:` blocks.
#   * `name=` values must be unique within this collection (no silent overwrite).
#
# Add third-party dependencies to the sibling requirements.txt — they are
# installed into ADARE's interpreter when the collection is loaded.
# =============================================================================

# external imports
from pathlib import Path

# internal imports
from adarelib.testset.api import testfunction
from adarelib.testset.basictest import HostModeCategory
from adarelib.event.event import TestResult

# configure logging
import logging
log = logging.getLogger(__name__)


@testfunction(
    name='file_contains_word',
    description='tests if a file contains the given word',
    category=HostModeCategory.FILE_BASED,
)
def file_contains_word(ctx, dst: str, word: str, case_sensitive: bool = True):
    """Example FILE_BASED test.

    Parameters (everything after ctx) become the playbook `parameter:` block.
    Always annotate them so playbook values structure correctly.
    """
    # Resolve the target path (supports glob patterns).
    dst_path, status = ctx.resolve_globfilepath(dst)
    # error_if -> ERROR (a precondition/setup problem, not a test failure).
    ctx.error_if(not dst_path, f'File {dst} could not be resolved ({status})')

    with open(dst_path, encoding='utf-8') as f:
        content = f.read()

    search_word = word
    if not case_sensitive:
        content = content.lower()
        search_word = word.lower()

    # fail_if -> FAILED (the test ran, but the condition was not met).
    ctx.fail_if(search_word not in content, f'Word "{word}" not found in {dst}')

    # Returning a str/list -> TestResult.success([...]).
    # You can also return TestResult.success/failed/error/warning([...]) directly.
    return f'Word "{word}" found in {dst}'


# -----------------------------------------------------------------------------
# Host / async stub (uncomment to test against the live screen via ctx.host).
# Host-mode tests use `async def` + execute_on_host=True and are NOT covered by
# the offline `adare test dry-run` harness (they need a running VM/host context).
# -----------------------------------------------------------------------------
#
# @testfunction(
#     name='screen_shows_text',
#     description='checks that some text is visible on screen',
#     category=HostModeCategory.HOST_NATIVE,
#     execute_on_host=True,
# )
# async def screen_shows_text(ctx, text: str):
#     screenshot = await ctx.host.screenshot.take()
#     locations = await ctx.host.cv.find_text(text, screenshot)
#     ctx.fail_if(not locations, f'text "{text}" not found on screen')
#     return f'text "{text}" is visible'
