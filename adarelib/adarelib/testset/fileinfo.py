"""File metadata helpers for the built-in ``standard`` collection: timestamps, permissions, owners.

Ships with the agent's adarelib wheel (see :mod:`adarelib.testset.compare` for how collections
and adarelib stay in step). Standard library only, importable on Python 3.10.
"""

import os
import platform
import stat
from datetime import datetime


def parse_timestamp(timestamp, time_format=None):
    """Parse timestamp to Unix timestamp"""
    if isinstance(timestamp, (int, float)):
        return float(timestamp)

    timestamp = str(timestamp)

    # A custom format wins: "20240115" with %Y%m%d is a date, not 20 million epoch seconds
    if time_format:
        try:
            dt = datetime.strptime(timestamp, time_format)
            return dt.timestamp()
        except ValueError:
            pass

    # Then a number (Unix seconds)
    try:
        return float(timestamp)
    except (ValueError, TypeError):
        pass

    # Try common formats
    common_formats = [
        '%Y-%m-%d %H:%M:%S',
        '%Y-%m-%dT%H:%M:%S',
        '%Y-%m-%dT%H:%M:%SZ',
        '%Y-%m-%d',
        '%m/%d/%Y %H:%M:%S',
        '%m/%d/%Y',
    ]

    for fmt in common_formats:
        try:
            dt = datetime.strptime(timestamp, fmt)
            return dt.timestamp()
        except ValueError:
            continue

    raise ValueError(f"Cannot parse timestamp: {timestamp}")


def file_timestamp(filepath, timestamp_type):
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


_SYMBOLIC_BITS = (
    (stat.S_IRUSR, stat.S_IWUSR, stat.S_IXUSR),
    (stat.S_IRGRP, stat.S_IWGRP, stat.S_IXGRP),
    (stat.S_IROTH, stat.S_IWOTH, stat.S_IXOTH),
)


def parse_permissions(perm_str):
    """Permission bits of an octal string (``644``) or symbolic ``rwxr-xr-x``.

    :raises ValueError: anything else (a non-octal digit, a letter other than ``r``/``w``/``x``
        in its place or ``-``, another length)
    """
    if perm_str.isdigit():
        try:
            return int(perm_str, 8)
        except ValueError:
            raise ValueError(f"Invalid octal permissions: {perm_str}") from None

    if len(perm_str) == 9:
        perms = 0
        for i, char in enumerate(perm_str):
            letter = 'rwx'[i % 3]
            if char == letter:
                perms |= _SYMBOLIC_BITS[i // 3][i % 3]
            elif char != '-':
                raise ValueError(f"Invalid permission format: {perm_str} ({char!r} at position {i + 1})")
        return perms

    raise ValueError(f"Invalid permission format: {perm_str}")


def owner_and_group(filepath):
    """Get file owner and group names"""
    try:
        import grp
        import pwd

        stat_info = os.stat(filepath)
        owner = pwd.getpwuid(stat_info.st_uid).pw_name
        group = grp.getgrgid(stat_info.st_gid).gr_name
        return owner, group
    except ImportError:
        # Windows doesn't have pwd/grp modules
        return None, None
    except (KeyError, OSError):
        return None, None
