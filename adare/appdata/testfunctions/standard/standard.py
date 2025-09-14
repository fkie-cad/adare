# external imports
import attrs
from pathlib import Path
import re
import hashlib
import os
import stat
import platform
from datetime import datetime
from typing import ClassVar, Optional, Union

# internal imports
from adarelib.testset.basictest import BasicTest, Parameter
from adarelib.event.event import TestResult

# configure logging
import logging
log = logging.getLogger(__name__)


@attrs.define
class FileExistsParameter(Parameter):
    dst: str


@attrs.define
class FileExists(BasicTest):
    testname: ClassVar[str] = 'file_exists'
    testdescription: ClassVar[str] = 'tests if a file with path destination(dst)  is existing'

    name: str
    parameter: FileExistsParameter
    description: Optional[str] = ''
    variable_metadata: Optional[dict] = None

    def test(self):
        try:
            if Path(self.parameter.dst).is_file():
                return TestResult.success()
            else:
                return TestResult.failed([f'file with path {self.parameter.dst} does not exist'])
        except (OSError, PermissionError) as e:
            return TestResult.execution_error(e, f"Cannot check file existence for {self.parameter.dst}")


@attrs.define
class FileDoesNotExistParameter(Parameter):
    dst: str


@attrs.define
class FileDoesNotExist(BasicTest):
    testname: ClassVar[str] = 'file_does_not_exist'
    testdescription: ClassVar[str] = 'tests if a file with path destination(dst) is NOT existing'

    name: str
    parameter: FileDoesNotExistParameter
    description: Optional[str] = ''
    variable_metadata: Optional[dict] = None

    def test(self):
        try:
            if not Path(self.parameter.dst).is_file():
                return TestResult.success()
            else:
                return TestResult.failed([f'file with path {self.parameter.dst} does exist'])
        except (OSError, PermissionError) as e:
            return TestResult.execution_error(e, f"Cannot check file existence for {self.parameter.dst}")



@attrs.define
class DirExistsParameter(Parameter):
    dst: str


@attrs.define
class DirExists(BasicTest):
    testname: ClassVar[str] = 'dir_exists'
    testdescription: ClassVar[str] = 'tests if a directory with path destination(dst) is existing'

    name: str
    parameter: DirExistsParameter
    description: Optional[str] = ''
    variable_metadata: Optional[dict] = None

    def test(self):
        try:
            if Path(self.parameter.dst).is_dir():
                return TestResult.success()
            else:
                return TestResult.failed([f'directory with path {self.parameter.dst} does not exist'])
        except (OSError, PermissionError) as e:
            return TestResult.execution_error(e, f"Cannot check directory existence for {self.parameter.dst}")


@attrs.define
class DirDoesNotExistParameter(Parameter):
    dst: str


@attrs.define
class DirDoesNotExist(BasicTest):
    testname: ClassVar[str] = 'dir_does_not_exist'
    testdescription: ClassVar[str] = 'tests if a directory with path destination(dst) is NOT existing'

    name: str
    parameter: DirDoesNotExistParameter
    description: Optional[str] = ''
    variable_metadata: Optional[dict] = None

    def test(self):
        try:
            if not Path(self.parameter.dst).is_dir():
                return TestResult.success()
            else:
                return TestResult.failed([f'directory with path {self.parameter.dst} does exist'])
        except (OSError, PermissionError) as e:
            return TestResult.execution_error(e, f"Cannot check directory existence for {self.parameter.dst}")


@attrs.define
class DirContentParameter(Parameter):
    dst: str
    files: list


@attrs.define
class DirContent(BasicTest):
    testname: ClassVar[str] = 'dir_content'
    testdescription: ClassVar[str] = 'tests if a directory has the expected files/folders'

    name: str
    parameter: DirContentParameter
    description: Optional[str] = ''
    variable_metadata: Optional[dict] = None

    def test(self):
        try:
            dst, status = self.resolve_globfilepath(self.parameter.dst)
            if not dst:
                return TestResult.error([f'directory with path {self.parameter.dst} can\'t be used, because no unambiguous directory could be identified (because {status})'])

            log.debug(f'dst directory {dst} will be used for test {self.name}')

            dir_content = [str(p) for p in Path(dst).iterdir()]
            expected_missing_files = [
                file for file in self.parameter.files if file not in dir_content
            ]
            additional_files = [
                file for file in dir_content if file not in self.parameter.files
            ]
            if expected_missing_files:
                details = [f'expected missing files: {expected_missing_files}']
                if additional_files:
                    details.append(f'additional files: {additional_files}')
                return TestResult.failed(details)

            return TestResult.success()
        except (OSError, PermissionError) as e:
            return TestResult.execution_error(e, f"Cannot read directory content for {self.parameter.dst}")


@attrs.define
class FileContentMatchesRegexParameter(Parameter):
    dst: str
    regex: str


@attrs.define
class FileContentMatchesRegex(BasicTest):
    testname: ClassVar[str] = 'file_content_matches_regex'
    testdescription: ClassVar[str] = 'tests if file content matches a given regex expression'

    name: str
    parameter: FileContentMatchesRegexParameter
    description: Optional[str] = ''
    variable_metadata: Optional[dict] = None

    def test(self):
        try:
            dst, status = self.resolve_globfilepath(self.parameter.dst)
            if not dst:
                return TestResult.error([f'file with path {self.parameter.dst} can\'t be used, because no unambiguous file could be identified (because {status})'])

            log.debug(f'dst file {dst} will be used for test {self.name}')

            try:
                with open(dst, 'r') as f:
                    data = f.read()
            except FileNotFoundError:
                return TestResult.failed([f'file with path {self.parameter.dst} does not exist'])
            except (PermissionError, OSError) as e:
                return TestResult.execution_error(e, f"Cannot read file {dst}")

            # Test regex compilation first
            try:
                pattern = re.compile(self.parameter.regex)
            except re.error as e:
                return TestResult.execution_error(e, f"Invalid regex pattern: {self.parameter.regex}")

            if pattern.search(data):
                return TestResult.success()
            else:
                return TestResult.failed(['file content does not match regex expression'])

        except Exception as e:
            return TestResult.execution_error(e, "Unexpected error in file content regex test")


@attrs.define
class FileContentEqualsParameter(Parameter):
    dst: str
    content: str

@attrs.define
class FileContentEquals(BasicTest):
    testname: ClassVar[str] = 'file_content_equals'
    testdescription: ClassVar[str] = 'tests if file content equals the given content'

    name: str
    parameter: FileContentEqualsParameter
    description: Optional[str] = ''
    variable_metadata: Optional[dict] = None

    def test(self):
        try:
            dst, status = self.resolve_globfilepath(self.parameter.dst)
            if not dst:
                return TestResult.error([f'file with path {self.parameter.dst} can\'t be used, because no unambiguous file could be identified (because {status})'])

            log.debug(f'dst file {dst} will be used for test {self.name}')
            try:
                with open(dst, 'r') as f:
                    data = f.read()
            except FileNotFoundError:
                return TestResult.failed([f'file with path {self.parameter.dst} does not exist'])
            except (PermissionError, OSError, UnicodeDecodeError) as e:
                return TestResult.execution_error(e, f"Cannot read file {dst}")

            # Check if we have placeholders that need special handling
            expected_content = self.parameter.content

            if not self.has_placeholders(expected_content):
                # No placeholders - direct comparison (content already fully resolved by client)
                success = data.strip() == expected_content.strip()
                message = "Direct content comparison"
            else:
                # Has placeholders - special handling needed
                try:
                    success, message = self._handle_placeholders_comparison(data.strip(), expected_content)
                except Exception as e:
                    return TestResult.execution_error(e, "Error in placeholder comparison logic")

            if success:
                return TestResult.success([message])
            else:
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
                    return TestResult.execution_error(e, "Error generating diff output")

        except Exception as e:
            return TestResult.execution_error(e, "Unexpected error in file content equals test")


@attrs.define
class FileHashMatchesParameter(Parameter):
    dst: str
    expected_hash: str
    hash_type: str = 'sha256'  # md5, sha1, sha256, sha512

@attrs.define
class FileHashMatches(BasicTest):
    testname: ClassVar[str] = 'file_hash_matches'
    testdescription: ClassVar[str] = 'tests if file hash matches expected value'

    name: str
    parameter: FileHashMatchesParameter
    description: Optional[str] = ''
    variable_metadata: Optional[dict] = None

    def _calculate_hash(self, filepath, hash_type):
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

    def test(self):
        try:
            dst, status = self.resolve_globfilepath(self.parameter.dst)
            if not dst:
                return TestResult.error([f'file {self.parameter.dst} can\'t be used, because no unambiguous file could be identified (because {status})'])

            log.debug(f'dst file {dst} will be used for test {self.name}')

            expected_hash = self.parameter.expected_hash

            expected_hash = expected_hash.lower()

            try:
                actual_hash = self._calculate_hash(dst, self.parameter.hash_type)

                if actual_hash == expected_hash:
                    return TestResult.success([f'{self.parameter.hash_type.upper()} hash matches: {actual_hash}'])
                else:
                    return TestResult.failed([f'{self.parameter.hash_type.upper()} hash mismatch. Expected: {expected_hash}, Got: {actual_hash}'])

            except FileNotFoundError:
                return TestResult.failed([f'file {dst} does not exist'])
            except (PermissionError, OSError) as e:
                return TestResult.execution_error(e, f"Cannot read file {dst}")
            except ValueError as e:
                return TestResult.execution_error(e, "Hash calculation error")

        except Exception as e:
            return TestResult.execution_error(e, "Unexpected error in file hash test")


@attrs.define
class FileTimestampsParameter(Parameter):
    dst: str
    timestamp_type: str = 'modified'  # modified, accessed, created
    comparison_type: str = 'equals'  # equals, before, after, between, within_last
    expected_time: Optional[Union[str, int, float]] = None
    time_format: Optional[str] = None  # strptime format
    tolerance_seconds: Optional[int] = None
    start_time: Optional[Union[str, int, float]] = None  # For 'between' comparison
    end_time: Optional[Union[str, int, float]] = None    # For 'between' comparison
    within_duration: Optional[str] = None  # For 'within_last' e.g., "1h", "30m", "2d"

@attrs.define
class FileTimestamps(BasicTest):
    testname: ClassVar[str] = 'file_timestamps'
    testdescription: ClassVar[str] = 'tests file timestamps with various comparison types and formats'

    name: str
    parameter: FileTimestampsParameter
    description: Optional[str] = ''
    variable_metadata: Optional[dict] = None

    def _parse_duration(self, duration_str):
        """Parse duration string like '1h', '30m', '2d' to seconds"""
        units = {'s': 1, 'm': 60, 'h': 3600, 'd': 86400}

        if not duration_str or not duration_str[-1] in units:
            raise ValueError(f"Invalid duration format: {duration_str}")

        try:
            value = int(duration_str[:-1])
            unit = duration_str[-1]
            return value * units[unit]
        except ValueError:
            raise ValueError(f"Invalid duration format: {duration_str}")

    def _parse_timestamp(self, timestamp, time_format=None):
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

    def _get_file_timestamp(self, filepath, timestamp_type):
        """Get file timestamp based on type"""
        stat_info = os.stat(filepath)

        if timestamp_type == 'modified':
            return stat_info.st_mtime
        elif timestamp_type == 'accessed':
            return stat_info.st_atime
        elif timestamp_type == 'created':
            # On Unix, st_ctime is not creation time but change time
            # On Windows, it is creation time
            if platform.system() == 'Windows':
                return stat_info.st_ctime
            else:
                # Try to get birth time on systems that support it
                try:
                    return stat_info.st_birthtime
                except AttributeError:
                    # Fall back to change time
                    return stat_info.st_ctime
        else:
            raise ValueError(f"Unsupported timestamp type: {timestamp_type}")

    def test(self):
        try:
            dst, status = self.resolve_globfilepath(self.parameter.dst)
            if not dst:
                return TestResult.error([f'file {self.parameter.dst} can\'t be used, because no unambiguous file could be identified (because {status})'])

            log.debug(f'dst file {dst} will be used for test {self.name}')

            try:
                actual_time = self._get_file_timestamp(dst, self.parameter.timestamp_type)
                comparison_type = self.parameter.comparison_type

                if comparison_type == 'equals':
                    expected_time = self._parse_timestamp(self.parameter.expected_time, self.parameter.time_format)

                    tolerance = self.parameter.tolerance_seconds or 0
                    if abs(actual_time - expected_time) <= tolerance:
                        return TestResult.success([f'{self.parameter.timestamp_type} timestamp matches (±{tolerance}s): {datetime.fromtimestamp(actual_time)}'])
                    else:
                        return TestResult.failed([f'{self.parameter.timestamp_type} timestamp mismatch. Expected: {datetime.fromtimestamp(expected_time)}, Got: {datetime.fromtimestamp(actual_time)}'])

                elif comparison_type == 'before':
                    expected_time = self._parse_timestamp(self.parameter.expected_time, self.parameter.time_format)
                    if actual_time < expected_time:
                        return TestResult.success([f'{self.parameter.timestamp_type} timestamp is before {datetime.fromtimestamp(expected_time)}'])
                    else:
                        return TestResult.failed([f'{self.parameter.timestamp_type} timestamp is not before {datetime.fromtimestamp(expected_time)}'])

                elif comparison_type == 'after':
                    expected_time = self._parse_timestamp(self.parameter.expected_time, self.parameter.time_format)
                    if actual_time > expected_time:
                        return TestResult.success([f'{self.parameter.timestamp_type} timestamp is after {datetime.fromtimestamp(expected_time)}'])
                    else:
                        return TestResult.failed([f'{self.parameter.timestamp_type} timestamp is not after {datetime.fromtimestamp(expected_time)}'])

                elif comparison_type == 'between':
                    start_time = self._parse_timestamp(self.parameter.start_time, self.parameter.time_format)
                    end_time = self._parse_timestamp(self.parameter.end_time, self.parameter.time_format)
                    if start_time <= actual_time <= end_time:
                        return TestResult.success([f'{self.parameter.timestamp_type} timestamp is between {datetime.fromtimestamp(start_time)} and {datetime.fromtimestamp(end_time)}'])
                    else:
                        return TestResult.failed([f'{self.parameter.timestamp_type} timestamp is not between {datetime.fromtimestamp(start_time)} and {datetime.fromtimestamp(end_time)}'])

                elif comparison_type == 'within_last':
                    duration_seconds = self._parse_duration(self.parameter.within_duration)
                    current_time = datetime.now().timestamp()
                    threshold_time = current_time - duration_seconds

                    if actual_time >= threshold_time:
                        return TestResult.success([f'{self.parameter.timestamp_type} timestamp is within last {self.parameter.within_duration}'])
                    else:
                        return TestResult.failed([f'{self.parameter.timestamp_type} timestamp is not within last {self.parameter.within_duration}'])

                else:
                    return TestResult.error([f'Unsupported comparison type: {comparison_type}'])

            except FileNotFoundError:
                return TestResult.failed([f'file {dst} does not exist'])
            except (PermissionError, OSError) as e:
                return TestResult.execution_error(e, f"Cannot access file {dst}")
            except ValueError as e:
                return TestResult.execution_error(e, "Timestamp parsing/comparison error")

        except Exception as e:
            return TestResult.execution_error(e, "Unexpected error in file timestamps test")


@attrs.define
class FilePermissionsParameter(Parameter):
    dst: str
    expected_permissions: str  # octal like '755' or symbolic like 'rwxr-xr-x'
    check_owner: Optional[str] = None
    check_group: Optional[str] = None

@attrs.define
class FilePermissions(BasicTest):
    testname: ClassVar[str] = 'file_permissions'
    testdescription: ClassVar[str] = 'tests file permissions, owner, and group'

    name: str
    parameter: FilePermissionsParameter
    description: Optional[str] = ''
    variable_metadata: Optional[dict] = None

    def _parse_permissions(self, perm_str):
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

    def _get_owner_group(self, filepath):
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

    def test(self):
        try:
            dst, status = self.resolve_globfilepath(self.parameter.dst)
            if not dst:
                return TestResult.error([f'file {self.parameter.dst} can\'t be used, because no unambiguous file could be identified (because {status})'])

            log.debug(f'dst file {dst} will be used for test {self.name}')

            expected_permissions = self.parameter.expected_permissions
            check_owner = self.parameter.check_owner
            check_group = self.parameter.check_group

            try:
                stat_info = os.stat(dst)
                actual_perms = stat_info.st_mode & 0o777
                expected_perms = self._parse_permissions(expected_permissions)

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
                    owner, group = self._get_owner_group(dst)

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
                else:
                    return TestResult.failed(results)

            except FileNotFoundError:
                return TestResult.failed([f'file {dst} does not exist'])
            except (PermissionError, OSError) as e:
                return TestResult.execution_error(e, f"Cannot access file {dst}")
            except ValueError as e:
                return TestResult.execution_error(e, "Permission parsing error")

        except Exception as e:
            return TestResult.execution_error(e, "Unexpected error in file permissions test")


@attrs.define
class FileContentContainsParameter(Parameter):
    dst: str
    content: Union[str, bytes]
    content_type: str = 'string'  # 'string' or 'bytes'


@attrs.define
class FileContentContains(BasicTest):
    testname: ClassVar[str] = 'file_content_contains'
    testdescription: ClassVar[str] = 'tests if file content contains specified string or byte pattern'

    name: str
    parameter: FileContentContainsParameter
    description: Optional[str] = ''
    variable_metadata: Optional[dict] = None

    def test(self):
        try:
            dst, status = self.resolve_globfilepath(self.parameter.dst)
            if not dst:
                return TestResult.error([f'file {self.parameter.dst} can\'t be used, because no unambiguous file could be identified (because {status})'])

            log.debug(f'dst file {dst} will be used for test {self.name}')

            try:
                if self.parameter.content_type == 'bytes':
                    # Read file in binary mode
                    with open(dst, 'rb') as f:
                        file_data = f.read()

                    # Convert content to bytes if it's a string
                    if isinstance(self.parameter.content, str):
                        search_content = self.parameter.content.encode('utf-8')
                    else:
                        search_content = self.parameter.content

                    if search_content in file_data:
                        return TestResult.success([f'byte pattern found in file'])
                    else:
                        return TestResult.failed([f'byte pattern not found in file'])

                else:  # default: string content
                    # Read file as text
                    with open(dst, 'r', encoding='utf-8', errors='ignore') as f:
                        file_content = f.read()

                    search_string = str(self.parameter.content)

                    if search_string in file_content:
                        return TestResult.success([f'string content found in file'])
                    else:
                        return TestResult.failed([f'string content not found in file'])

            except FileNotFoundError:
                return TestResult.failed([f'file {dst} does not exist'])
            except (PermissionError, OSError) as e:
                return TestResult.execution_error(e, f"Cannot read file {dst}")

        except Exception as e:
            return TestResult.execution_error(e, "Unexpected error in file content contains test")