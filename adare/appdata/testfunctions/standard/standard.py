# external imports
from pathlib import Path
import re
import os
import stat
from datetime import datetime
from typing import Optional, Union

# internal imports
from adarelib.testset.api import testfunction, TestContext
from adarelib.testset.basictest import HostModeCategory
from adarelib.event.event import TestResult
from adarelib.testset.content import detect_encoding_from_bom as _detect_encoding_from_bom
from adarelib.testset.content import strip_bom_from_text as _strip_bom_from_text
from adarelib.testset.content import file_hash, parse_byte_string, parse_duration
from adarelib.testset.fileinfo import file_timestamp, owner_and_group, parse_permissions, parse_timestamp
from adarelib.testset.archive import has_archive_separator
from adarelib.testset.structured import COMPARISON_TYPES, compare_count, count_parameter_errors

# configure logging
import logging

log = logging.getLogger(__name__)


# =============================================================================
# Test functions
# =============================================================================


@testfunction(
    name='file_exists',
    description='tests if file(s) with path destination(dst) exist (supports glob patterns with match_mode)',
    category=HostModeCategory.FILE_BASED,
)
def file_exists(ctx, dst: str = '', match_mode: str = "any"):
    """Pass when a regular file exists at ``dst`` (for globs: at least one match is a file).

    Use for: verifying a GUI action created/saved a file. Opposite: standard.file_does_not_exist.

    Args:
        dst: Guest path to the file. Glob characters ``* ? [ ]`` are expanded with Python
            ``glob`` (not recursive: ``**`` acts like ``*``; ``*`` skips dotfiles), e.g.
            ``C:/Users/*/Desktop/*.txt``. Case sensitivity follows the guest filesystem.
            A path that exists but is a directory fails.
        match_mode: ``any`` (default; any value except ``single`` behaves the same): passes
            if at least one match is a regular file. ``single``: a glob must match exactly
            one path, otherwise the test ERRORS (not fails).

    Example:
        function: standard.file_exists
        parameter:
          dst: /home/user/Documents/report.odt
    """
    try:
        paths, status = ctx.resolve_globfilepath(dst, match_mode=match_mode, return_list=True)
        if status:
            return TestResult.error(
                [f'path {dst} cannot be used, because no unambiguous file could be identified (because {status})']
            )

        # Plain paths come back from resolve_globfilepath unchecked; drop missing
        # ones so a nonexistent path is reported as missing, not as the wrong type.
        paths = [p for p in paths if os.path.lexists(p)]
        files = [p for p in paths if Path(p).is_file()]

        if match_mode == "single":
            if len(files) == 1:
                return TestResult.success([f'file {files[0]} exists'])
            if not files and paths:
                return TestResult.failed([f'path {paths[0]} exists but is not a file'])
            return TestResult.failed([f'file with path {dst} does not exist'])
        # "any"
        if files:
            return TestResult.success([f'{len(files)} file(s) found: {", ".join(files)}'])
        if paths:
            return TestResult.failed([f'{len(paths)} path(s) matched but none are files'])
        return TestResult.failed([f'no files match pattern {dst}'])
    except (OSError, PermissionError) as e:
        return TestResult.execution_error(e, f"Cannot check file existence for {dst}")


@testfunction(
    name='file_does_not_exist',
    description='tests if file(s) with path destination(dst) do NOT exist (supports glob patterns with match_mode)',
    category=HostModeCategory.FILE_BASED,
)
def file_does_not_exist(ctx, dst: str = '', match_mode: str = "any"):
    """Pass when no regular file exists at ``dst`` (for globs: no match is a file).

    Use for: verifying a file was deleted or never written. Opposite: standard.file_exists.
    A directory at ``dst`` does not count as a file, so it passes.

    Args:
        dst: Guest path; glob characters ``* ? [ ]`` expanded with Python ``glob``
            (not recursive). Case sensitivity follows the guest filesystem.
        match_mode: ``any`` (default; anything except ``single``): passes when zero matches
            are files. ``single``: a glob must match exactly one path, else the test ERRORS
            -- so a glob with no matches errors instead of passing; keep ``any`` for globs.

    Example:
        function: standard.file_does_not_exist
        parameter:
          dst: C:/Users/*/AppData/Local/Temp/secret.tmp
    """
    try:
        paths, status = ctx.resolve_globfilepath(dst, match_mode=match_mode, return_list=True)
        if status:
            return TestResult.error(
                [f'path {dst} cannot be used, because no unambiguous file could be identified (because {status})']
            )

        # Plain paths come back from resolve_globfilepath unchecked; drop missing
        # ones so a nonexistent path is reported as missing, not as the wrong type.
        paths = [p for p in paths if os.path.lexists(p)]
        files = [p for p in paths if Path(p).is_file()]

        if match_mode == "single":
            if not files:
                return TestResult.success([f'file {dst} does not exist'])
            return TestResult.failed([f'file {files[0]} exists'])
        # "any"
        if not files:
            count = len(paths)
            if count > 0:
                return TestResult.success([f'{count} path(s) matched but none are files'])
            return TestResult.success([f'no files match pattern {dst}'])
        return TestResult.failed([f'{len(files)} file(s) exist matching pattern: {", ".join(files)}'])
    except (OSError, PermissionError) as e:
        return TestResult.execution_error(e, f"Cannot check file existence for {dst}")


@testfunction(
    name='dir_exists',
    description='tests if directory(ies) with path destination(dst) exist (supports glob patterns with match_mode)',
    category=HostModeCategory.FILE_BASED,
)
def dir_exists(ctx, dst: str = '', match_mode: str = "any"):
    """Pass when a directory exists at ``dst`` (for globs: at least one match is a directory).

    Use for: verifying an install/extract step created a folder. Opposite: standard.dir_does_not_exist.

    Args:
        dst: Guest path to the directory; glob characters ``* ? [ ]`` expanded with Python
            ``glob`` (not recursive). A path that exists but is a file fails.
        match_mode: ``any`` (default; anything except ``single``): passes if one match is a
            directory. ``single``: a glob must match exactly one path, else the test ERRORS.

    Example:
        function: standard.dir_exists
        parameter:
          dst: /home/user/.config/someapp
    """
    try:
        paths, status = ctx.resolve_globfilepath(dst, match_mode=match_mode, return_list=True)
        if status:
            return TestResult.error(
                [f'path {dst} cannot be used, because no unambiguous directory could be identified (because {status})']
            )

        # Plain paths come back from resolve_globfilepath unchecked; drop missing
        # ones so a nonexistent path is reported as missing, not as the wrong type.
        paths = [p for p in paths if os.path.lexists(p)]
        dirs = [p for p in paths if Path(p).is_dir()]

        if match_mode == "single":
            if len(dirs) == 1:
                return TestResult.success([f'directory {dirs[0]} exists'])
            if not dirs and paths:
                return TestResult.failed([f'path {paths[0]} exists but is not a directory'])
            return TestResult.failed([f'directory with path {dst} does not exist'])
        # "any"
        if dirs:
            return TestResult.success([f'{len(dirs)} directory(ies) found: {", ".join(dirs)}'])
        if paths:
            return TestResult.failed([f'{len(paths)} path(s) matched but none are directories'])
        return TestResult.failed([f'no directories match pattern {dst}'])
    except (OSError, PermissionError) as e:
        return TestResult.execution_error(e, f"Cannot check directory existence for {dst}")


@testfunction(
    name='dir_does_not_exist',
    description='tests if directory(ies) with path destination(dst) do NOT exist (supports glob patterns with match_mode)',
    category=HostModeCategory.FILE_BASED,
)
def dir_does_not_exist(ctx, dst: str = '', match_mode: str = "any"):
    """Pass when no directory exists at ``dst`` (for globs: no match is a directory).

    Use for: verifying a folder was removed or never created. Opposite: standard.dir_exists.
    A regular file at ``dst`` does not count as a directory, so it passes.

    Args:
        dst: Guest path; glob characters ``* ? [ ]`` expanded with Python ``glob`` (not recursive).
        match_mode: ``any`` (default; anything except ``single``): passes when zero matches
            are directories. ``single``: a glob must match exactly one path, else the test
            ERRORS -- a glob with no matches errors instead of passing.

    Example:
        function: standard.dir_does_not_exist
        parameter:
          dst: C:/Users/user/AppData/Roaming/OldApp
    """
    try:
        paths, status = ctx.resolve_globfilepath(dst, match_mode=match_mode, return_list=True)
        if status:
            return TestResult.error(
                [f'path {dst} cannot be used, because no unambiguous directory could be identified (because {status})']
            )

        # Plain paths come back from resolve_globfilepath unchecked; drop missing
        # ones so a nonexistent path is reported as missing, not as the wrong type.
        paths = [p for p in paths if os.path.lexists(p)]
        dirs = [p for p in paths if Path(p).is_dir()]

        if match_mode == "single":
            if not dirs:
                return TestResult.success([f'directory {dst} does not exist'])
            return TestResult.failed([f'directory {dirs[0]} exists'])
        # "any"
        if not dirs:
            count = len(paths)
            if count > 0:
                return TestResult.success([f'{count} path(s) matched but none are directories'])
            return TestResult.success([f'no directories match pattern {dst}'])
        return TestResult.failed([f'{len(dirs)} directory(ies) exist matching pattern: {", ".join(dirs)}'])
    except (OSError, PermissionError) as e:
        return TestResult.execution_error(e, f"Cannot check directory existence for {dst}")


@testfunction(
    name='dir_content',
    description='tests if a directory has the expected files/folders',
    category=HostModeCategory.FILE_BASED,
)
def dir_content(ctx, dst: str = '', files: list = None):
    """Pass when every name in ``files`` is a direct entry of directory ``dst``.

    Use for: checking a folder contains expected files/subfolders. Extra entries are allowed
    (only listed in the failure details); the listing is not recursive.

    Args:
        dst: Guest path to the directory. A glob must match exactly one path, otherwise the
            test errors. A missing or unreadable directory is an execution error, not a failure.
        files: Entry names (not paths) that must be present, compared exactly and
            case-sensitively against the directory listing. ``None``/empty always passes.

    Example:
        function: standard.dir_content
        parameter:
          dst: /home/user/Documents/export
          files: [report.csv, images]
    """
    try:
        dst_param = dst
        dst, status = ctx.resolve_globfilepath(dst)
        if not dst:
            return TestResult.error(
                [
                    f'directory with path {dst_param} can\'t be used, because no unambiguous directory could be identified (because {status})'
                ]
            )

        log.debug(f'dst directory {dst} will be used for test')

        dir_content_list = [p.name for p in Path(dst).iterdir()]
        expected_files = files if files is not None else []
        expected_missing_files = [file for file in expected_files if file not in dir_content_list]
        additional_files = [file for file in dir_content_list if file not in expected_files]
        if expected_missing_files:
            details = [f'expected missing files: {expected_missing_files}']
            if additional_files:
                details.append(f'additional files: {additional_files}')
            return TestResult.failed(details)

        return TestResult.success()
    except (OSError, PermissionError) as e:
        return TestResult.execution_error(e, f"Cannot read directory content for {dst}")


@testfunction(
    name='file_content_matches_regex',
    description='tests if file content matches a given regex expression',
    category=HostModeCategory.FILE_BASED,
)
def file_content_matches_regex(ctx, dst: str = '', regex: str = '', encoding: str = 'utf-8', strip_bom: bool = False):
    """Pass when the regex ``regex`` is found anywhere in the text of file ``dst``.

    Use for: loose content checks (a value appears, a line has a given shape). For exact
    content use standard.file_content_equals; for a plain substring standard.file_content_contains.

    Args:
        dst: Guest path to the file. A glob must match exactly one path, otherwise the test
            errors. A missing file is an error.
        regex: Python ``re`` pattern applied with ``re.search`` to the whole file. Default
            flags: case-sensitive, ``^``/``$`` match only file start/end; use inline flags
            such as ``(?im)``. An empty pattern always passes; an invalid one errors.
        encoding: Python codec used to decode the file (strict: undecodable bytes error).
            ``BOM`` detects UTF-8/16/32 from the byte-order mark and errors if there is none.
        strip_bom: Remove a leading U+FEFF from the decoded text before matching.

    Example:
        function: standard.file_content_matches_regex
        parameter:
          dst: /home/user/notes.txt
          regex: '(?m)^Total: [0-9]+$'
    """
    dst_param = dst
    dst, status = ctx.resolve_globfilepath(dst)
    if not dst:
        return TestResult.error(
            [
                f'file with path {dst_param} can\'t be used, because no unambiguous file could be identified (because {status})'
            ]
        )

    log.debug(f'dst file {dst} will be used for test')

    # Handle BOM detection and encoding
    if encoding and encoding.upper() == 'BOM':
        detected_encoding, bom_length = _detect_encoding_from_bom(dst)
        if detected_encoding:
            encoding = detected_encoding
        else:
            return TestResult.execution_error(None, f"No BOM found in file {dst} to detect encoding")

    try:
        with open(dst, encoding=encoding) as f:
            data = f.read()

        # Strip BOM if requested
        if strip_bom:
            data = _strip_bom_from_text(data, encoding)

    except FileNotFoundError:
        return TestResult.error([f'file with path {dst} does not exist'])
    except (PermissionError, OSError, UnicodeDecodeError) as e:
        return TestResult.execution_error(e, f"Cannot read file {dst}")

    # Test regex compilation first
    try:
        pattern = re.compile(regex)
    except re.error as e:
        return TestResult.execution_error(e, f"Invalid regex pattern: {regex}")

    if pattern.search(data):
        return TestResult.success()
    return TestResult.failed(['file content does not match regex expression'])


@testfunction(
    name='file_content_equals',
    description='tests if file content equals the given content',
    category=HostModeCategory.FILE_BASED,
)
def file_content_equals(ctx, dst: str = '', content: str = '', encoding: str = 'utf-8', strip_bom: bool = False):
    r"""Pass when the text of file ``dst`` equals ``content`` (leading/trailing whitespace ignored).

    Use for: exact output checks, e.g. a tool's exit code or a saved text document.

    Args:
        dst: Guest path to the file. A glob must match exactly one path, otherwise the test
            errors. A missing file is an error; a failure includes a unified diff.
        content: Expected text. Both sides are ``strip()``-ed; inner whitespace must match
            (line endings are normalised to ``\n`` by text-mode reading). ``!re``/``!timestamp``
            tags inside the value become placeholders matched by type; the literal text
            around them must match exactly.
        encoding: Python codec used to decode the file (strict). ``BOM`` detects UTF-8/16/32
            from the byte-order mark and errors if there is none.
        strip_bom: Remove a leading U+FEFF from the decoded text before comparing.

    Example:
        function: standard.file_content_equals
        parameter:
          dst: '{{ out_dir }}/exit_code.txt'
          content: '0'
    """
    dst_param = dst
    dst, status = ctx.resolve_globfilepath(dst)
    if not dst:
        return TestResult.error(
            [
                f'file with path {dst_param} can\'t be used, because no unambiguous file could be identified (because {status})'
            ]
        )

    log.debug(f'dst file {dst} will be used for test')

    # Handle BOM detection and encoding
    if encoding and encoding.upper() == 'BOM':
        detected_encoding, bom_length = _detect_encoding_from_bom(dst)
        if detected_encoding:
            encoding = detected_encoding
        else:
            return TestResult.execution_error(None, f"No BOM found in file {dst} to detect encoding")

    try:
        with open(dst, encoding=encoding) as f:
            data = f.read()

        # Strip BOM if requested
        if strip_bom:
            data = _strip_bom_from_text(data, encoding)

    except FileNotFoundError:
        return TestResult.error([f'file with path {dst} does not exist'])
    except (PermissionError, OSError, UnicodeDecodeError) as e:
        return TestResult.execution_error(e, f"Cannot read file {dst}")

    # Check if we have placeholders that need special handling
    expected_content = content

    if not ctx.has_placeholders(expected_content):
        # No placeholders - direct comparison (content already fully resolved by client)
        success = data.strip() == expected_content.strip()
        message = "Direct content comparison"
    else:
        # Has placeholders - special handling needed
        success, message = ctx.handle_placeholders_comparison(data.strip(), expected_content)

    if success:
        return TestResult.success([message])
    # Show diff for debugging
    import difflib

    expected_for_diff = expected_content
    diff_lines = list(
        difflib.unified_diff(
            expected_for_diff.splitlines(keepends=True),
            data.splitlines(keepends=True),
            fromfile='expected',
            tofile='actual',
            lineterm='',
        )
    )
    diff_output = ''.join(diff_lines) if diff_lines else 'Content differs but no line-by-line diff available'

    return TestResult.failed([message, f'Diff:\n{diff_output}'])


@testfunction(
    name='file_hash_matches',
    description='tests if file hash matches expected value',
    category=HostModeCategory.FILE_BASED,
)
def file_hash_matches(ctx, dst: str = '', expected_hash: str = '', hash_type: str = 'sha256'):
    """Pass when the ``hash_type`` digest of file ``dst`` equals ``expected_hash``.

    Use for: verifying a file is byte-identical to a known artifact.

    Args:
        dst: Guest path to the file. A glob must match exactly one path, otherwise the test
            errors. A missing file is an error.
        expected_hash: Hex digest; compared case-insensitively but otherwise exactly (no
            whitespace stripping, no prefix such as ``sha256:``).
        hash_type: ``md5``, ``sha1``, ``sha256`` (default) or ``sha512`` (case-insensitive);
            anything else is an execution error.

    Example:
        function: standard.file_hash_matches
        parameter:
          dst: C:/Users/user/Downloads/setup.exe
          expected_hash: e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855
    """
    dst_param = dst
    dst, status = ctx.resolve_globfilepath(dst)
    if not dst:
        return TestResult.error(
            [f'file {dst_param} can\'t be used, because no unambiguous file could be identified (because {status})']
        )

    log.debug(f'dst file {dst} will be used for test')

    expected_hash = expected_hash.lower()

    try:
        actual_hash = file_hash(dst, hash_type)

        if actual_hash == expected_hash:
            return TestResult.success([f'{hash_type.upper()} hash matches: {actual_hash}'])
        return TestResult.failed([f'{hash_type.upper()} hash mismatch. Expected: {expected_hash}, Got: {actual_hash}'])

    except FileNotFoundError:
        return TestResult.error([f'file {dst} does not exist'])
    except (PermissionError, OSError) as e:
        return TestResult.execution_error(e, f"Cannot read file {dst}")
    except ValueError as e:
        return TestResult.execution_error(e, "Hash calculation error")


@testfunction(
    name='file_timestamps',
    description='tests file timestamps with various comparison types and formats',
    category=HostModeCategory.QGA_PROBE,
)
def file_timestamps(
    ctx,
    dst: str = '',
    timestamp_type: str = 'modified',
    comparison_type: str = 'equals',
    expected_time: str | int | float = None,
    time_format: str = None,
    tolerance_seconds: int = None,
    start_time: str | int | float = None,
    end_time: str | int | float = None,
    within_duration: str = None,
):
    """Pass when the chosen timestamp of file ``dst`` satisfies ``comparison_type``.

    Use for: MACB timestamp assertions (modified recently, accessed after an action, ...).

    Args:
        dst: Guest path to the file. A glob must match exactly one path, otherwise the test
            errors. A missing file is an error.
        timestamp_type: ``modified`` (mtime, default), ``accessed`` (atime) or ``created``:
            creation time on Windows; elsewhere ``st_birthtime`` if Python exposes it, else
            ``st_ctime`` (inode change time on Linux). Other values error.
        comparison_type: ``equals`` (default, within ``tolerance_seconds``), ``before`` /
            ``after`` (strict, vs ``expected_time``), ``between`` (inclusive, ``start_time``..
            ``end_time``) or ``within_last`` (``within_duration`` before the guest's now).
        expected_time: Reference for equals/before/after: Unix epoch seconds or a date string
            (see ``time_format``). Naive strings are read in the guest's local timezone (the
            trailing ``Z`` format too). Missing/unparseable values error.
        time_format: ``strptime`` format tried first; then ``%Y-%m-%d %H:%M:%S``,
            ``%Y-%m-%dT%H:%M:%S``, ``%Y-%m-%dT%H:%M:%SZ``, ``%Y-%m-%d``, ``%m/%d/%Y %H:%M:%S``, ``%m/%d/%Y``.
        tolerance_seconds: Allowed absolute difference for ``equals``; ``None`` means 0, which
            rarely matches sub-second filesystem times.
        start_time: Lower bound for ``between`` (same formats as ``expected_time``).
        end_time: Upper bound for ``between``.
        within_duration: For ``within_last``: integer plus unit ``s``/``m``/``h``/``d``, e.g. ``15m``.

    Example:
        function: standard.file_timestamps
        parameter:
          dst: /home/user/Documents/report.odt
          comparison_type: within_last
          within_duration: 10m
    """
    dst_param = dst
    dst, status = ctx.resolve_globfilepath(dst)
    if not dst:
        return TestResult.error(
            [f'file {dst_param} can\'t be used, because no unambiguous file could be identified (because {status})']
        )

    log.debug(f'dst file {dst} will be used for test')

    try:
        actual_time = file_timestamp(dst, timestamp_type)

        if comparison_type == 'equals':
            expected = parse_timestamp(expected_time, time_format)

            tolerance = tolerance_seconds or 0
            if abs(actual_time - expected) <= tolerance:
                return TestResult.success(
                    [f'{timestamp_type} timestamp matches (±{tolerance}s): {datetime.fromtimestamp(actual_time)}']
                )
            return TestResult.failed(
                [
                    f'{timestamp_type} timestamp mismatch. Expected: {datetime.fromtimestamp(expected)}, Got: {datetime.fromtimestamp(actual_time)}'
                ]
            )

        if comparison_type == 'before':
            expected = parse_timestamp(expected_time, time_format)
            if actual_time < expected:
                return TestResult.success([f'{timestamp_type} timestamp is before {datetime.fromtimestamp(expected)}'])
            return TestResult.failed([f'{timestamp_type} timestamp is not before {datetime.fromtimestamp(expected)}'])

        if comparison_type == 'after':
            expected = parse_timestamp(expected_time, time_format)
            if actual_time > expected:
                return TestResult.success([f'{timestamp_type} timestamp is after {datetime.fromtimestamp(expected)}'])
            return TestResult.failed([f'{timestamp_type} timestamp is not after {datetime.fromtimestamp(expected)}'])

        if comparison_type == 'between':
            start = parse_timestamp(start_time, time_format)
            end = parse_timestamp(end_time, time_format)
            if start <= actual_time <= end:
                return TestResult.success(
                    [
                        f'{timestamp_type} timestamp is between {datetime.fromtimestamp(start)} and {datetime.fromtimestamp(end)}'
                    ]
                )
            return TestResult.failed(
                [
                    f'{timestamp_type} timestamp is not between {datetime.fromtimestamp(start)} and {datetime.fromtimestamp(end)}'
                ]
            )

        if comparison_type == 'within_last':
            duration_seconds = parse_duration(within_duration)
            current_time = datetime.now().timestamp()
            threshold_time = current_time - duration_seconds

            if actual_time >= threshold_time:
                return TestResult.success([f'{timestamp_type} timestamp is within last {within_duration}'])
            return TestResult.failed([f'{timestamp_type} timestamp is not within last {within_duration}'])

        return TestResult.error([f'Unsupported comparison type: {comparison_type}'])

    except FileNotFoundError:
        return TestResult.error([f'file {dst} does not exist'])
    except (PermissionError, OSError) as e:
        return TestResult.execution_error(e, f"Cannot access file {dst}")
    except ValueError as e:
        return TestResult.execution_error(e, "Timestamp parsing/comparison error")


@testfunction(
    name='file_permissions', description='tests file permissions, owner, and group', category=HostModeCategory.QGA_PROBE
)
def file_permissions(
    ctx, dst: str = '', expected_permissions: str = '', check_owner: str = None, check_group: str = None
):
    """Pass when the permission bits (and optional owner/group) of ``dst`` match exactly.

    Use for: Unix mode/ownership checks after chmod/chown or a file save. Only meaningful on
    Linux guests: Windows reports synthetic mode bits and no owner/group (owner checks fail).

    Args:
        dst: Guest path to the file or directory. A glob must match exactly one path,
            otherwise the test errors. A missing path is an error.
        expected_permissions: Octal digits (``'644'``, ``'0755'``) or 9-char symbolic
            (``rwxr-xr-x``), compared with ``st_mode & 0o777`` (no setuid/sticky). Quote it in
            YAML (unquoted ``0644`` is read as decimal 420). Empty/invalid values error.
        check_owner: Expected owner user name (not UID); ``None`` skips the check.
        check_group: Expected group name (not GID); ``None`` skips the check.

    Example:
        function: standard.file_permissions
        parameter:
          dst: /home/user/.ssh/id_ed25519
          expected_permissions: '600'
          check_owner: user
    """
    dst_param = dst
    dst, status = ctx.resolve_globfilepath(dst)
    if not dst:
        return TestResult.error(
            [f'file {dst_param} can\'t be used, because no unambiguous file could be identified (because {status})']
        )

    log.debug(f'dst file {dst} will be used for test')

    try:
        stat_info = os.stat(dst)
        actual_perms = stat_info.st_mode & 0o777
        expected_perms = parse_permissions(expected_permissions)

        results = []
        success = True

        # Check permissions
        if actual_perms == expected_perms:
            results.append(f'permissions match: {oct(actual_perms)[-3:]}')
        else:
            results.append(f'permission mismatch. Expected: {oct(expected_perms)[-3:]}, Got: {oct(actual_perms)[-3:]}')
            success = False

        # Check owner and group if specified
        if check_owner or check_group:
            owner, group = owner_and_group(dst)

            if check_owner:
                if owner == check_owner:
                    results.append(f'owner matches: {owner}')
                else:
                    results.append(f'owner mismatch. Expected: {check_owner}, Got: {owner}')
                    success = False

            if check_group:
                if group == check_group:
                    results.append(f'group matches: {group}')
                else:
                    results.append(f'group mismatch. Expected: {check_group}, Got: {group}')
                    success = False

        if success:
            return TestResult.success(results)
        return TestResult.failed(results)

    except FileNotFoundError:
        return TestResult.error([f'file {dst} does not exist'])
    except (PermissionError, OSError) as e:
        return TestResult.execution_error(e, f"Cannot access file {dst}")
    except ValueError as e:
        return TestResult.execution_error(e, "Permission parsing error")


@testfunction(
    name='file_content_contains',
    description='tests if file content contains specified string or byte pattern',
    category=HostModeCategory.FILE_BASED,
)
def file_content_contains(
    ctx,
    dst: str = '',
    content: str = '',
    content_type: str = 'string',
    encoding: str = 'utf-8',
    strip_bom: bool = False,
):
    r"""Pass when file ``dst`` contains ``content`` as a substring (text) or byte sequence.

    Use for: checking a value/marker was written into a file. For patterns use
    standard.file_content_matches_regex; to count occurrences, search several encodings at
    once or assert a value is gone from a binary file use text.occurrence_count.

    Args:
        dst: Guest path to the file. A glob must match exactly one path, otherwise the test
            errors. A missing file is an error.
        content: Text to find (case-sensitive). An empty value always passes. In ``bytes``
            mode ASCII characters stand for their byte and Python escapes (``\x00``, ``\n``,
            ``\\``) are decoded; a non-ASCII character or an unknown escape is an error (write
            ``\xNN``, or use ``string`` mode with an ``encoding``).
        content_type: ``string`` (default) searches the decoded text, ``bytes`` the raw file
            bytes; other values are an error. A ``!re``/``!timestamp`` placeholder in ``content``
            is an error (use standard.file_content_matches_regex).
        encoding: Codec for ``string`` mode; undecodable bytes are silently dropped.
            ``BOM`` detects UTF-8/16/32 from the byte-order mark and errors if there is none.
        strip_bom: Remove a leading U+FEFF from the decoded text (``string`` mode only).

    Example:
        function: standard.file_content_contains
        parameter:
          dst: /home/user/.bash_history
          content: rm -rf ~/evidence
    """
    if content_type not in ('string', 'bytes'):
        return TestResult.error([f"invalid content_type {content_type!r} (allowed: string, bytes)"])
    if isinstance(content, str) and ctx.has_placeholders(content):
        return TestResult.error(
            [
                f'content {content!r} holds a !re or !timestamp placeholder, which is not supported here; '
                'use standard.file_content_matches_regex'
            ]
        )
    dst_param = dst
    dst, status = ctx.resolve_globfilepath(dst)
    if not dst:
        return TestResult.error(
            [f'file {dst_param} can\'t be used, because no unambiguous file could be identified (because {status})']
        )

    log.debug(f'dst file {dst} will be used for test')

    if content_type == 'bytes':
        try:
            search_bytes = parse_byte_string(content)
        except ValueError as e:
            return TestResult.error([str(e)])

    try:
        if content_type == 'bytes':
            with open(dst, 'rb') as f:
                file_data = f.read()
            if search_bytes in file_data:
                return TestResult.success(['byte pattern found in file'])
            return TestResult.failed(['byte pattern not found in file'])

        # default: string content
        # Handle BOM detection and encoding for string content
        if encoding and encoding.upper() == 'BOM':
            detected_encoding, bom_length = _detect_encoding_from_bom(dst)
            if detected_encoding:
                encoding = detected_encoding
            else:
                return TestResult.execution_error(None, f"No BOM found in file {dst} to detect encoding")

        # Read file as text
        with open(dst, encoding=encoding, errors='ignore') as f:
            file_content = f.read()

        # Strip BOM if requested
        if strip_bom:
            file_content = _strip_bom_from_text(file_content, encoding)

        search_string = content

        if search_string in file_content:
            return TestResult.success(['string content found in file'])
        return TestResult.failed(['string content not found in file'])

    except FileNotFoundError:
        return TestResult.error([f'file {dst} does not exist'])
    except (PermissionError, OSError) as e:
        return TestResult.execution_error(e, f"Cannot read file {dst}")


@testfunction(
    name='file_size',
    description='tests the size of a file in bytes',
    category=HostModeCategory.FILE_BASED,
)
def file_size(ctx, dst: str, expected_size: int, comparison_type: str = 'equals'):
    """Pass when the size in bytes of file ``dst`` satisfies ``comparison_type`` against ``expected_size``.

    Use for: checking a file is empty (``expected_size: 0``), non-empty (``greater`` 0) or
    grew/shrank past a threshold. Existence alone: standard.file_exists.

    Args:
        dst: Guest path to the file. A glob must match exactly one path; a missing file or a
            directory is an error. An archive member (``a.zip!/p/x.db``) has its extracted size.
        expected_size: Non-negative integer number of bytes; anything else is an error.
        comparison_type: ``equals`` (default), ``greater``, ``less``, ``greater_equal`` or
            ``less_equal``; other values are an error.

    Example:
        function: standard.file_size
        parameter:
          dst: /home/user/data/app.log
          expected_size: 0
          comparison_type: greater
    """
    if isinstance(expected_size, bool) or not isinstance(expected_size, int) or expected_size < 0:
        return TestResult.error([f'expected_size must be a non-negative integer, got {expected_size!r}'])
    if comparison_type not in COMPARISON_TYPES:
        return TestResult.error(
            [f"invalid comparison_type {comparison_type!r} (allowed: {', '.join(COMPARISON_TYPES)})"]
        )
    path, status = ctx.resolve_globfilepath(dst)
    if not path:
        return TestResult.error(
            [f'file {dst} can\'t be used, because no unambiguous file could be identified ({status})']
        )
    try:
        info = os.stat(path)
    except FileNotFoundError:
        return TestResult.error([f'file {path} does not exist'])
    except OSError as e:
        return TestResult.execution_error(e, f'Cannot stat file {path}')
    if stat.S_ISDIR(info.st_mode):
        return TestResult.error([f'{path} is a directory, not a file'])
    ok, message = compare_count(info.st_size, expected_size, comparison_type)
    details = [f'file {path} is {info.st_size} bytes', message.replace('count', 'size', 1)]
    return TestResult.success(details) if ok else TestResult.failed(details)


_FILE_COUNT_KINDS = ('file', 'dir', 'any')


@testfunction(
    name='file_count',
    description='tests the number of files (or directories) matching a path or glob',
    category=HostModeCategory.FILE_BASED,
)
def file_count(ctx, dst: str, expected_count: int, comparison_type: str = 'equals', kind: str = 'file'):
    """Pass when the number of paths matching ``dst`` that are of ``kind`` satisfies ``comparison_type``.

    Use for: how many files an application wrote (exactly 3 logs, at least one export) and
    absence of a whole group of files: ``expected_count: 0``. One file: standard.file_exists.

    Args:
        dst: Guest path or glob (Python ``glob``, not recursive: ``**`` acts like ``*``;
            ``*`` skips dotfiles), e.g. ``/home/user/logs/*.log``. No match counts 0, it is not
            an error; an empty ``dst`` or an unresolved ``{{placeholder}}`` is. Inside an archive (``a.zip!/logs/*.log``) the matching file members are
            counted; the archive itself must exist and be readable, otherwise an error.
        expected_count: Non-negative integer to compare against; anything else is an error.
        comparison_type: ``equals`` (default), ``greater``, ``less``, ``greater_equal`` or
            ``less_equal``; other values are an error.
        kind: ``file`` (default): regular files (also through a symlink); ``dir``:
            directories; ``any``: every existing path. Archives have file members only, so
            ``dir`` with an archive path is an error.

    Example:
        function: standard.file_count
        parameter:
          dst: /home/user/.cache/app/*.tmp
          expected_count: 0
    """
    problems = count_parameter_errors(expected_count, comparison_type)
    if kind not in _FILE_COUNT_KINDS:
        problems.append(f"invalid kind {kind!r} (allowed: {', '.join(_FILE_COUNT_KINDS)})")
    if not isinstance(dst, str) or not dst.strip() or '{{' in dst:
        problems.append(f'dst must be a resolved path, got {dst!r}')  # else an absence test passes on it
    in_archive = isinstance(dst, str) and has_archive_separator(dst)
    if in_archive and kind == 'dir':
        problems.append('kind dir cannot be counted inside an archive (members are files)')
    if problems:
        return TestResult.error(problems)
    paths, status = ctx.resolve_globfilepath(dst, match_mode='any', return_list=True)
    if status:
        return TestResult.error([f'path {dst} cannot be used ({status})'])
    try:
        if kind == 'file':
            matching = [p for p in paths if os.path.isfile(p)]
        elif kind == 'dir':
            matching = [p for p in paths if os.path.isdir(p)]
        else:
            matching = [p for p in paths if os.path.lexists(p)]
    except OSError as e:
        return TestResult.execution_error(e, f'Cannot check paths for {dst}')
    ok, message = compare_count(len(matching), expected_count, comparison_type)
    shown = ', '.join(sorted(matching)[:5]) + (', ...' if len(matching) > 5 else '')
    details = [f'{len(matching)} {kind} path(s) match {dst}' + (f': {shown}' if matching else ''), message]
    return TestResult.success(details) if ok else TestResult.failed(details)
