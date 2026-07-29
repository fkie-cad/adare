# =============================================================================
# COPY-ME example testfunction collection
# =============================================================================
#
# The built-in collections under `adare/appdata/testfunctions/` are integrity-
# protected (hash-verified before production runs) and are NOT meant to be edited
# in place. To author your own tests, copy THIS directory into your project's
# `testfunctions/` folder, rename it, and edit freely:
#
#     cp -r examples/testfunctions/example  <project>/testfunctions/mychecks
#     mv    <project>/testfunctions/mychecks/example.py \
#           <project>/testfunctions/mychecks/mychecks.py   # file stem == dir name!
#
# Then validate and load:
#
#     adare test validate <project>/testfunctions/mychecks
#     adare test load      <project>/testfunctions/mychecks
#
# Reference a test from a playbook by `<collection>.<name>`:
#
#     tests:
#       - name: keyword_present
#         function: mychecks.file_contains_word
#         parameter:
#           dst: "/evidence/log.txt"
#           word: "ERROR"
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
    """FILE_BASED pattern: resolve a path, read it, assert on its contents."""
    dst_path, status = ctx.resolve_globfilepath(dst)
    ctx.error_if(not dst_path, f'File {dst} could not be resolved ({status})')

    with open(dst_path, encoding='utf-8') as f:
        content = f.read()

    search_word = word
    if not case_sensitive:
        content = content.lower()
        search_word = word.lower()

    ctx.fail_if(search_word not in content, f'Word "{word}" not found in {dst}')
    return f'Word "{word}" found in {dst}'


@testfunction(
    name='line_count_at_least',
    description='passes if the file has at least min_lines lines; warns when nearly empty',
    category=HostModeCategory.FILE_CONTENT,
)
def line_count_at_least(ctx, dst: str, min_lines: int = 1):
    """FILE_CONTENT pattern + pass-with-warning.

    Demonstrates TestResult.warning: the test passes (does not fail the run
    verdict) but flags a noteworthy condition distinctly from a plain success.
    """
    dst_path, status = ctx.resolve_globfilepath(dst)
    ctx.error_if(not dst_path, f'File {dst} could not be resolved ({status})')

    with open(dst_path, encoding='utf-8') as f:
        lines = f.readlines()

    count = len(lines)
    ctx.fail_if(count < min_lines, f'expected >= {min_lines} lines, found {count}')

    if count == min_lines:
        # Passed, but only just — surface it as a warning, not a failure.
        return TestResult.warning([f'file has exactly the minimum {count} line(s)'])

    return TestResult.success([f'file has {count} line(s)'])


@testfunction(
    name='value_matches_placeholder',
    description='reads a single-line file and compares it against an expected value/placeholder',
    category=HostModeCategory.FILE_CONTENT,
)
def value_matches_placeholder(ctx, dst: str, expected: str):
    """Placeholder pattern: expected may contain {{VAR}} resolved from variables."""
    dst_path, status = ctx.resolve_globfilepath(dst)
    ctx.error_if(not dst_path, f'File {dst} could not be resolved ({status})')

    actual = Path(dst_path).read_text(encoding='utf-8').strip()

    if ctx.has_placeholders(expected):
        placeholders = ctx.get_placeholders(expected)
        if len(placeholders) == 1:
            success, message = ctx.compare_with_placeholder(placeholders[0], actual)
        else:
            success, message = ctx.handle_placeholders_comparison(actual, expected)
        ctx.fail_if(not success, message)
        return message

    ctx.fail_if(actual != expected, f'expected "{expected}", got "{actual}"')
    return f'value matches: "{actual}"'
