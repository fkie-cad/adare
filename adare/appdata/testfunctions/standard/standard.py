# external imports
from pathlib import Path
import re
import hashlib
import os
import stat
import platform
from datetime import datetime
from typing import Optional, Union

# internal imports
from adarelib.testset.api import testfunction, TestContext
from adarelib.testset.basictest import HostModeCategory
from adarelib.event.event import TestResult

# configure logging
import logging
log = logging.getLogger(__name__)


# =============================================================================
# Module-level helper functions (deduplicated)
# =============================================================================

def _detect_encoding_from_bom(file_path):
    """Detect encoding from BOM, return (encoding, bom_length)"""
    with open(file_path, 'rb') as f:
        raw_data = f.read(4)

    if raw_data.startswith(b'\xef\xbb\xbf'):
        return 'utf-8', 3
    if raw_data.startswith(b'\xff\xfe\x00\x00'):
        return 'utf-32-le', 4
    if raw_data.startswith(b'\x00\x00\xfe\xff'):
        return 'utf-32-be', 4
    if raw_data.startswith(b'\xff\xfe'):
        return 'utf-16-le', 2
    if raw_data.startswith(b'\xfe\xff'):
        return 'utf-16-be', 2
    return None, 0


def _strip_bom_from_text(text, encoding):
    """Strip BOM from text content"""
    if encoding.lower() == 'utf-8' and text.startswith('\ufeff') or encoding.lower().startswith('utf-16') and text.startswith('\ufeff') or encoding.lower().startswith('utf-32') and text.startswith('\ufeff'):
        return text[1:]
    return text


def _calculate_hash(filepath, hash_type):
    """Calculate file hash"""
    hash_algos = {
        'md5': hashlib.md5,
        'sha1': hashlib.sha1,
        'sha256': hashlib.sha256,
        'sha512': hashlib.sha512
    }

    if hash_type.lower() not in hash_algos:
        raise ValueError(f"Unsupported hash type: {hash_type}")

    hasher = hash_algos[hash_type.lower()]()

    with open(filepath, 'rb') as f:
        for chunk in iter(lambda: f.read(4096), b""):
            hasher.update(chunk)

    return hasher.hexdigest()


def _parse_duration(duration_str):
    """Parse duration string like '1h', '30m', '2d' to seconds"""
    units = {'s': 1, 'm': 60, 'h': 3600, 'd': 86400}

    if not duration_str or duration_str[-1] not in units:
        raise ValueError(f"Invalid duration format: {duration_str}")

    try:
        value = int(duration_str[:-1])
        unit = duration_str[-1]
        return value * units[unit]
    except ValueError:
        raise ValueError(f"Invalid duration format: {duration_str}")


def _parse_timestamp(timestamp, time_format=None):
    """Parse timestamp to Unix timestamp"""
    if isinstance(timestamp, (int, float)):
        return float(timestamp)

    timestamp = str(timestamp)

    # Try parsing as number first
    try:
        return float(timestamp)
    except (ValueError, TypeError):
        pass

    # Parse with custom format
    if time_format:
        try:
            dt = datetime.strptime(timestamp, time_format)
            return dt.timestamp()
        except ValueError:
            pass

    # Try common formats
    common_formats = [
        '%Y-%m-%d %H:%M:%S',
        '%Y-%m-%dT%H:%M:%S',
        '%Y-%m-%dT%H:%M:%SZ',
        '%Y-%m-%d',
        '%m/%d/%Y %H:%M:%S',
        '%m/%d/%Y'
    ]

    for fmt in common_formats:
        try:
            dt = datetime.strptime(timestamp, fmt)
            return dt.timestamp()
        except ValueError:
            continue

    raise ValueError(f"Cannot parse timestamp: {timestamp}")


def _get_file_timestamp(filepath, timestamp_type):
    """Get file timestamp based on type"""
    stat_info = os.stat(filepath)

    if timestamp_type == 'modified':
        return stat_info.st_mtime
    if timestamp_type == 'accessed':
        return stat_info.st_atime
    if timestamp_type == 'created':
        # On Unix, st_ctime is not creation time but change time
        # On Windows, it is creation time
        if platform.system() == 'Windows':
            return stat_info.st_ctime
        # Try to get birth time on systems that support it
        try:
            return stat_info.st_birthtime
        except AttributeError:
            # Fall back to change time
            return stat_info.st_ctime
    else:
        raise ValueError(f"Unsupported timestamp type: {timestamp_type}")


def _parse_permissions(perm_str):
    """Parse permission string to octal"""
    if perm_str.isdigit():
        # Already octal
        return int(perm_str, 8)

    # Parse symbolic notation like 'rwxr-xr-x'
    if len(perm_str) == 9:
        perms = 0
        # Owner permissions
        if perm_str[0] == 'r': perms |= stat.S_IRUSR
        if perm_str[1] == 'w': perms |= stat.S_IWUSR
        if perm_str[2] == 'x': perms |= stat.S_IXUSR
        # Group permissions
        if perm_str[3] == 'r': perms |= stat.S_IRGRP
        if perm_str[4] == 'w': perms |= stat.S_IWGRP
        if perm_str[5] == 'x': perms |= stat.S_IXGRP
        # Other permissions
        if perm_str[6] == 'r': perms |= stat.S_IROTH
        if perm_str[7] == 'w': perms |= stat.S_IWOTH
        if perm_str[8] == 'x': perms |= stat.S_IXOTH
        return perms

    raise ValueError(f"Invalid permission format: {perm_str}")


def _get_owner_group(filepath):
    """Get file owner and group names"""
    try:
        import pwd
        import grp
        stat_info = os.stat(filepath)
        owner = pwd.getpwuid(stat_info.st_uid).pw_name
        group = grp.getgrgid(stat_info.st_gid).gr_name
        return owner, group
    except ImportError:
        # Windows doesn't have pwd/grp modules
        return None, None
    except (KeyError, OSError):
        return None, None


def _parse_escape_sequences(text):
    """Parse Python-style escape sequences in string to actual bytes"""
    try:
        # Use codecs to decode escape sequences like \x41, \n, \t, etc.
        import codecs
        return codecs.decode(text, 'unicode_escape').encode('latin1')
    except (UnicodeDecodeError, UnicodeEncodeError):
        # If parsing fails, fall back to UTF-8 encoding
        return text.encode('utf-8')


# =============================================================================
# Test functions
# =============================================================================

@testfunction(
    name='file_exists',
    description='tests if file(s) with path destination(dst) exist (supports glob patterns with match_mode)',
    category=HostModeCategory.FILE_BASED
)
def file_exists(ctx, dst: str = '', match_mode: str = "any"):
    try:
        paths, status = ctx.resolve_globfilepath(
            dst,
            match_mode=match_mode,
            return_list=True
        )
        if status:
            return TestResult.error([f'path {dst} cannot be used, '
                                    f'because no unambiguous file could be identified (because {status})'])

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
    category=HostModeCategory.FILE_BASED
)
def file_does_not_exist(ctx, dst: str = '', match_mode: str = "any"):
    try:
        paths, status = ctx.resolve_globfilepath(
            dst,
            match_mode=match_mode,
            return_list=True
        )
        if status:
            return TestResult.error([f'path {dst} cannot be used, '
                                    f'because no unambiguous file could be identified (because {status})'])

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
    category=HostModeCategory.FILE_BASED
)
def dir_exists(ctx, dst: str = '', match_mode: str = "any"):
    try:
        paths, status = ctx.resolve_globfilepath(
            dst,
            match_mode=match_mode,
            return_list=True
        )
        if status:
            return TestResult.error([f'path {dst} cannot be used, '
                                    f'because no unambiguous directory could be identified (because {status})'])

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
    category=HostModeCategory.FILE_BASED
)
def dir_does_not_exist(ctx, dst: str = '', match_mode: str = "any"):
    try:
        paths, status = ctx.resolve_globfilepath(
            dst,
            match_mode=match_mode,
            return_list=True
        )
        if status:
            return TestResult.error([f'path {dst} cannot be used, '
                                    f'because no unambiguous directory could be identified (because {status})'])

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
    category=HostModeCategory.FILE_BASED
)
def dir_content(ctx, dst: str = '', files: list = None):
    try:
        dst, status = ctx.resolve_globfilepath(dst)
        if not dst:
            return TestResult.error([f'directory with path {dst} can\'t be used, because no unambiguous directory could be identified (because {status})'])

        log.debug(f'dst directory {dst} will be used for test')

        dir_content_list = [p.name for p in Path(dst).iterdir()]
        expected_files = files if files is not None else []
        expected_missing_files = [
            file for file in expected_files if file not in dir_content_list
        ]
        additional_files = [
            file for file in dir_content_list if file not in expected_files
        ]
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
    category=HostModeCategory.FILE_BASED
)
def file_content_matches_regex(ctx, dst: str = '', regex: str = '', encoding: str = 'utf-8', strip_bom: bool = False):
    try:
        dst, status = ctx.resolve_globfilepath(dst)
        if not dst:
            return TestResult.error([f'file with path {dst} can\'t be used, because no unambiguous file could be identified (because {status})'])

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
            return TestResult.failed([f'file with path {dst} does not exist'])
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

    except Exception as e:
        log.error(f"Unexpected error in file content regex test: {e}", exc_info=True)
        return TestResult.execution_error(e, "Unexpected error in file content regex test")


@testfunction(
    name='file_content_equals',
    description='tests if file content equals the given content',
    category=HostModeCategory.FILE_BASED
)
def file_content_equals(ctx, dst: str = '', content: str = '', encoding: str = 'utf-8', strip_bom: bool = False):
    try:
        dst, status = ctx.resolve_globfilepath(dst)
        if not dst:
            return TestResult.error([f'file with path {dst} can\'t be used, because no unambiguous file could be identified (because {status})'])

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
            return TestResult.failed([f'file with path {dst} does not exist'])
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
            try:
                success, message = ctx.handle_placeholders_comparison(data.strip(), expected_content)
            except Exception as e:
                log.error(f"Error in placeholder comparison logic: {e}", exc_info=True)
                return TestResult.execution_error(e, "Error in placeholder comparison logic")

        if success:
            return TestResult.success([message])
        # Show diff for debugging
        try:
            import difflib
            expected_for_diff = expected_content
            diff_lines = list(difflib.unified_diff(
                expected_for_diff.splitlines(keepends=True),
                data.splitlines(keepends=True),
                fromfile='expected',
                tofile='actual',
                lineterm=''
            ))
            diff_output = ''.join(diff_lines) if diff_lines else 'Content differs but no line-by-line diff available'

            return TestResult.failed([
                message,
                f'Diff:\n{diff_output}'
            ])
        except Exception as e:
            log.error(f"Error generating diff output: {e}", exc_info=True)
            return TestResult.execution_error(e, "Error generating diff output")

    except Exception as e:
        log.error(f"Unexpected error in file content equals test: {e}", exc_info=True)
        return TestResult.execution_error(e, "Unexpected error in file content equals test")


@testfunction(
    name='file_hash_matches',
    description='tests if file hash matches expected value',
    category=HostModeCategory.FILE_BASED
)
def file_hash_matches(ctx, dst: str = '', expected_hash: str = '', hash_type: str = 'sha256'):
    try:
        dst, status = ctx.resolve_globfilepath(dst)
        if not dst:
            return TestResult.error([f'file {dst} can\'t be used, because no unambiguous file could be identified (because {status})'])

        log.debug(f'dst file {dst} will be used for test')

        expected_hash = expected_hash.lower()

        try:
            actual_hash = _calculate_hash(dst, hash_type)

            if actual_hash == expected_hash:
                return TestResult.success([f'{hash_type.upper()} hash matches: {actual_hash}'])
            return TestResult.failed([f'{hash_type.upper()} hash mismatch. Expected: {expected_hash}, Got: {actual_hash}'])

        except FileNotFoundError:
            return TestResult.failed([f'file {dst} does not exist'])
        except (PermissionError, OSError) as e:
            return TestResult.execution_error(e, f"Cannot read file {dst}")
        except ValueError as e:
            return TestResult.execution_error(e, "Hash calculation error")

    except Exception as e:
        log.error(f"Unexpected error in file hash test: {e}", exc_info=True)
        return TestResult.execution_error(e, "Unexpected error in file hash test")


@testfunction(
    name='file_timestamps',
    description='tests file timestamps with various comparison types and formats',
    category=HostModeCategory.QGA_PROBE
)
def file_timestamps(ctx, dst: str = '', timestamp_type: str = 'modified', comparison_type: str = 'equals',
                    expected_time: str | int | float = None, time_format: str = None,
                    tolerance_seconds: int = None, start_time: str | int | float = None,
                    end_time: str | int | float = None, within_duration: str = None):
    try:
        dst, status = ctx.resolve_globfilepath(dst)
        if not dst:
            return TestResult.error([f'file {dst} can\'t be used, because no unambiguous file could be identified (because {status})'])

        log.debug(f'dst file {dst} will be used for test')

        try:
            actual_time = _get_file_timestamp(dst, timestamp_type)

            if comparison_type == 'equals':
                expected = _parse_timestamp(expected_time, time_format)

                tolerance = tolerance_seconds or 0
                if abs(actual_time - expected) <= tolerance:
                    return TestResult.success([f'{timestamp_type} timestamp matches (±{tolerance}s): {datetime.fromtimestamp(actual_time)}'])
                return TestResult.failed([f'{timestamp_type} timestamp mismatch. Expected: {datetime.fromtimestamp(expected)}, Got: {datetime.fromtimestamp(actual_time)}'])

            if comparison_type == 'before':
                expected = _parse_timestamp(expected_time, time_format)
                if actual_time < expected:
                    return TestResult.success([f'{timestamp_type} timestamp is before {datetime.fromtimestamp(expected)}'])
                return TestResult.failed([f'{timestamp_type} timestamp is not before {datetime.fromtimestamp(expected)}'])

            if comparison_type == 'after':
                expected = _parse_timestamp(expected_time, time_format)
                if actual_time > expected:
                    return TestResult.success([f'{timestamp_type} timestamp is after {datetime.fromtimestamp(expected)}'])
                return TestResult.failed([f'{timestamp_type} timestamp is not after {datetime.fromtimestamp(expected)}'])

            if comparison_type == 'between':
                start = _parse_timestamp(start_time, time_format)
                end = _parse_timestamp(end_time, time_format)
                if start <= actual_time <= end:
                    return TestResult.success([f'{timestamp_type} timestamp is between {datetime.fromtimestamp(start)} and {datetime.fromtimestamp(end)}'])
                return TestResult.failed([f'{timestamp_type} timestamp is not between {datetime.fromtimestamp(start)} and {datetime.fromtimestamp(end)}'])

            if comparison_type == 'within_last':
                duration_seconds = _parse_duration(within_duration)
                current_time = datetime.now().timestamp()
                threshold_time = current_time - duration_seconds

                if actual_time >= threshold_time:
                    return TestResult.success([f'{timestamp_type} timestamp is within last {within_duration}'])
                return TestResult.failed([f'{timestamp_type} timestamp is not within last {within_duration}'])

            return TestResult.error([f'Unsupported comparison type: {comparison_type}'])

        except FileNotFoundError:
            return TestResult.failed([f'file {dst} does not exist'])
        except (PermissionError, OSError) as e:
            return TestResult.execution_error(e, f"Cannot access file {dst}")
        except ValueError as e:
            return TestResult.execution_error(e, "Timestamp parsing/comparison error")

    except Exception as e:
        log.error(f"Unexpected error in file timestamps test: {e}", exc_info=True)
        return TestResult.execution_error(e, "Unexpected error in file timestamps test")


@testfunction(
    name='file_permissions',
    description='tests file permissions, owner, and group',
    category=HostModeCategory.QGA_PROBE
)
def file_permissions(ctx, dst: str = '', expected_permissions: str = '', check_owner: str = None, check_group: str = None):
    try:
        dst, status = ctx.resolve_globfilepath(dst)
        if not dst:
            return TestResult.error([f'file {dst} can\'t be used, because no unambiguous file could be identified (because {status})'])

        log.debug(f'dst file {dst} will be used for test')

        try:
            stat_info = os.stat(dst)
            actual_perms = stat_info.st_mode & 0o777
            expected_perms = _parse_permissions(expected_permissions)

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
                owner, group = _get_owner_group(dst)

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
            return TestResult.failed([f'file {dst} does not exist'])
        except (PermissionError, OSError) as e:
            return TestResult.execution_error(e, f"Cannot access file {dst}")
        except ValueError as e:
            return TestResult.execution_error(e, "Permission parsing error")

    except Exception as e:
        log.error(f"Unexpected error in file permissions test: {e}", exc_info=True)
        return TestResult.execution_error(e, "Unexpected error in file permissions test")


@testfunction(
    name='file_content_contains',
    description='tests if file content contains specified string or byte pattern',
    category=HostModeCategory.FILE_BASED
)
def file_content_contains(ctx, dst: str = '', content: str = '', content_type: str = 'string', encoding: str = 'utf-8', strip_bom: bool = False):
    try:
        dst, status = ctx.resolve_globfilepath(dst)
        if not dst:
            return TestResult.error([f'file {dst} can\'t be used, because no unambiguous file could be identified (because {status})'])

        log.debug(f'dst file {dst} will be used for test')

        try:
            if content_type == 'bytes':
                # Read file in binary mode
                with open(dst, 'rb') as f:
                    file_data = f.read()

                # Parse escape sequences in the string to get actual bytes
                search_content = _parse_escape_sequences(content)

                if search_content in file_data:
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
            return TestResult.failed([f'file {dst} does not exist'])
        except (PermissionError, OSError) as e:
            return TestResult.execution_error(e, f"Cannot read file {dst}")

    except Exception as e:
        log.error(f"Unexpected error in file content contains test: {e}", exc_info=True)
        return TestResult.execution_error(e, "Unexpected error in file content contains test")
