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


def parse_permissions(perm_str):
    """Parse permission string to octal"""
    if perm_str.isdigit():
        # Already octal
        return int(perm_str, 8)

    # Parse symbolic notation like 'rwxr-xr-x'
    if len(perm_str) == 9:
        perms = 0
        # Owner permissions
        if perm_str[0] == 'r':
            perms |= stat.S_IRUSR
        if perm_str[1] == 'w':
            perms |= stat.S_IWUSR
        if perm_str[2] == 'x':
            perms |= stat.S_IXUSR
        # Group permissions
        if perm_str[3] == 'r':
            perms |= stat.S_IRGRP
        if perm_str[4] == 'w':
            perms |= stat.S_IWGRP
        if perm_str[5] == 'x':
            perms |= stat.S_IXGRP
        # Other permissions
        if perm_str[6] == 'r':
            perms |= stat.S_IROTH
        if perm_str[7] == 'w':
            perms |= stat.S_IWOTH
        if perm_str[8] == 'x':
            perms |= stat.S_IXOTH
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
