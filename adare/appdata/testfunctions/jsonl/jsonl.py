# external imports
import attrs
from pathlib import Path
import json
import re
from typing import ClassVar, Optional, Union, Dict, Any, List, Tuple

# internal imports
from adarelib.testset.basictest import BasicTest, Parameter, HostModeCategory
from adarelib.event.event import TestResult
from adarelib.constants import StatusEnum

# configure logging
import logging
log = logging.getLogger(__name__)


def _get_nested_value(data, key_path):
    """Navigate nested dictionary using dot notation with wildcard support

    Supports:
    - [*] for all array elements (e.g., "users[*].name")
    - * for all object keys (e.g., "config.*.enabled")

    Returns:
    - For exact paths: (value, True) or (None, False)
    - For wildcard paths: (list_of_values, True) or ([], False)
    """
    keys = key_path.split('.')
    current_values = [data]  # Start with data wrapped in list for consistent handling

    for key in keys:
        next_values = []

        for current in current_values:
            if key == '*':
                # Wildcard for all keys in dict
                if isinstance(current, dict):
                    next_values.extend(current.values())
            elif key.endswith('[*]'):
                # Array wildcard (e.g., "users[*]")
                base_key = key[:-3]  # Remove '[*]'
                if isinstance(current, dict) and base_key in current:
                    array_value = current[base_key]
                    if isinstance(array_value, list):
                        next_values.extend(array_value)
            elif isinstance(current, dict) and key in current:
                # Regular key access
                next_values.append(current[key])

        if not next_values:
            # No matching values found
            return [], False

        current_values = next_values

    # If we have multiple values, it was a wildcard match
    if len(current_values) > 1:
        return current_values, True
    elif len(current_values) == 1:
        return current_values[0], True
    else:
        return None, False


def _compare_values(test_instance, actual_value, expected_value, regex_match=False):
    """Compare values using placeholder system from BasicTest"""

    # Check for YamlRegexString objects (!re syntax)
    try:
        from adarelib.testset.yaml.customtags import YamlRegexString
        if isinstance(expected_value, YamlRegexString):
            try:
                pattern = re.compile(expected_value.string)
                if pattern.match(str(actual_value)):
                    return True, f'value "{actual_value}" matches regex "{expected_value.string}"'
                else:
                    return False, f'value "{actual_value}" does not match regex "{expected_value.string}"'
            except re.error as e:
                return False, f'Invalid regex pattern: {expected_value.string} - {e}'
    except ImportError:
        pass

    expected_str = str(expected_value)

    if not test_instance.has_placeholders(expected_str):
        # No placeholders - check for regex_match flag
        if regex_match and isinstance(expected_value, str):
            # Special case: "*" means "field exists" (any value)
            if expected_value == "*":
                return True, f'field exists with value "{actual_value}"'

            # Regex matching
            try:
                pattern = re.compile(expected_value)
                if pattern.search(str(actual_value)):
                    return True, f'value "{actual_value}" matches regex "{expected_value}"'
                else:
                    return False, f'value "{actual_value}" does not match regex "{expected_value}"'
            except re.error as e:
                return False, f'Invalid regex pattern: {expected_value} - {e}'
        else:
            # Direct value comparison
            if actual_value == expected_value:
                return True, f'value matches expected: {actual_value}'
            else:
                return False, f'expected "{expected_value}", got "{actual_value}"'
    else:
        # Has placeholders - use placeholder system
        placeholder_names = test_instance.get_placeholders(expected_str)
        if len(placeholder_names) == 1:
            placeholder_name = placeholder_names[0]
            try:
                return test_instance.compare_with_placeholder(placeholder_name, str(actual_value))
            except Exception as e:
                return False, f"placeholder comparison error: {e}"
        else:
            return False, f"expected 1 placeholder for single value comparison, got {len(placeholder_names)}"


@attrs.define
class LineMatchesParameter(Parameter):
    dst: str
    conditions: Dict[str, Union[str, int, float, bool, None]]
    match_mode: Optional[str] = "any"  # "any" or "all"
    regex_match: Optional[bool] = False
    skip_malformed: Optional[bool] = True  # Skip malformed JSON lines or fail


@attrs.define
class LineMatches(BasicTest):
    testname: ClassVar[str] = 'line_matches'
    testdescription: ClassVar[str] = 'tests if lines in JSONL file match specified conditions (supports any/all modes)'
    host_mode_category: ClassVar[HostModeCategory] = HostModeCategory.FILE_CONTENT

    name: str
    parameter: LineMatchesParameter
    description: Optional[str] = ''
    variable_metadata: Optional[dict] = None

    def test(self):
        try:
            dst, status = self.resolve_globfilepath(self.parameter.dst)
            if not dst:
                return TestResult.failed([f'JSONL file {self.parameter.dst} not found ({status})'])

            log.debug(f'dst file {dst} will be used for test {self.name}')

            conditions = self.parameter.conditions
            match_mode = self.parameter.match_mode or "any"
            regex_match = self.parameter.regex_match or False
            skip_malformed = self.parameter.skip_malformed

            if match_mode not in ['any', 'all']:
                return TestResult.execution_error(None, f"Invalid match_mode: {match_mode}. Must be 'any' or 'all'")

            try:
                # Check if file is empty (edge case handling)
                import os
                if os.path.getsize(dst) == 0:
                    return TestResult.failed(['JSONL file is empty (0 bytes)'])
                matching_lines = []
                non_matching_lines = []
                malformed_lines = []
                line_num = 0

                with open(dst, 'r') as f:
                    for line in f:
                        line_num += 1
                        line = line.strip()

                        # Skip blank lines
                        if not line:
                            continue

                        # Try to parse JSON
                        try:
                            data = json.loads(line)
                        except json.JSONDecodeError as e:
                            malformed_lines.append((line_num, line[:100]))
                            if not skip_malformed:
                                return TestResult.failed([
                                    f'Malformed JSON on line {line_num}: {e}',
                                    f'Line content: {line[:200]}'
                                ])
                            continue

                        # Check all conditions for this line
                        all_conditions_met = True
                        failed_conditions = []

                        for key_path, expected_value in conditions.items():
                            value, exists = _get_nested_value(data, key_path)

                            if not exists:
                                all_conditions_met = False
                                failed_conditions.append(f"{key_path} (not found)")
                                continue

                            # Handle multiple values from wildcards
                            if isinstance(value, list):
                                # Check if any value matches (for wildcards)
                                any_match = False
                                for v in value:
                                    is_match, msg = _compare_values(self, v, expected_value, regex_match)
                                    if is_match:
                                        any_match = True
                                        break
                                if not any_match:
                                    all_conditions_met = False
                                    failed_conditions.append(f"{key_path} (no wildcard matches)")
                            else:
                                # Single value comparison
                                is_match, msg = _compare_values(self, value, expected_value, regex_match)
                                if not is_match:
                                    all_conditions_met = False
                                    failed_conditions.append(f"{key_path} ({msg})")

                        if all_conditions_met:
                            matching_lines.append((line_num, data))
                        else:
                            non_matching_lines.append((line_num, data, failed_conditions))

                # Log malformed lines if any
                if malformed_lines:
                    log.warning(f"Skipped {len(malformed_lines)} malformed JSON lines in {dst}")

                # Determine success based on match_mode
                if match_mode == "any":
                    if matching_lines:
                        messages = [
                            f'Found {len(matching_lines)} matching line(s) out of {line_num} total lines (mode: any)',
                            f'First matching line: {matching_lines[0][0]}'
                        ]
                        if len(matching_lines) > 1:
                            messages.append(f'Additional matches on lines: {[ln for ln, _ in matching_lines[1:4]]}')
                        return TestResult.success(messages)
                    else:
                        messages = [
                            f'No lines matched all conditions (mode: any)',
                            f'Analyzed {line_num} lines',
                            f'Conditions: {conditions}'
                        ]
                        if non_matching_lines[:3]:
                            messages.append('Sample non-matching lines:')
                            for ln, data, failed in non_matching_lines[:3]:
                                messages.append(f'  Line {ln}: failed {failed}')
                        return TestResult.failed(messages)
                else:  # match_mode == "all"
                    total_valid_lines = len(matching_lines) + len(non_matching_lines)
                    if total_valid_lines == 0:
                        return TestResult.failed(['No valid JSON lines found in file'])

                    if len(matching_lines) == total_valid_lines:
                        return TestResult.success([
                            f'All {total_valid_lines} lines matched conditions (mode: all)',
                            f'Conditions: {conditions}'
                        ])
                    else:
                        messages = [
                            f'Only {len(matching_lines)}/{total_valid_lines} lines matched (mode: all)',
                            f'Conditions: {conditions}'
                        ]
                        if non_matching_lines[:3]:
                            messages.append('Sample non-matching lines:')
                            for ln, data, failed in non_matching_lines[:3]:
                                messages.append(f'  Line {ln}: failed {failed}')
                        return TestResult.failed(messages)

            except FileNotFoundError:
                return TestResult.failed([f'JSONL file {dst} does not exist'])
            except (PermissionError, OSError) as e:
                return TestResult.execution_error(e, f"Cannot read JSONL file {dst}")

        except Exception as e:
            log.error(f"Unexpected error in JSONL line matches test: {e}", exc_info=True)
            return TestResult.execution_error(e, "Unexpected error in JSONL line matches test")


@attrs.define
class LineCountParameter(Parameter):
    dst: str
    conditions: Optional[Dict[str, Union[str, int, float, bool, None]]] = None
    expected_count: Optional[Union[int, Dict[str, int]]] = None  # int, {"min": x, "max": y}, or None (at least 1)
    regex_match: Optional[bool] = False
    skip_malformed: Optional[bool] = True


@attrs.define
class LineCount(BasicTest):
    testname: ClassVar[str] = 'line_count'
    testdescription: ClassVar[str] = 'counts lines in JSONL file matching conditions and validates against expected count (if None, requires at least 1 match)'
    host_mode_category: ClassVar[HostModeCategory] = HostModeCategory.FILE_CONTENT

    name: str
    parameter: LineCountParameter
    description: Optional[str] = ''
    variable_metadata: Optional[dict] = None

    def test(self):
        try:
            dst, status = self.resolve_globfilepath(self.parameter.dst)
            if not dst:
                return TestResult.failed([f'JSONL file {self.parameter.dst} not found ({status})'])

            log.debug(f'dst file {dst} will be used for test {self.name}')

            conditions = self.parameter.conditions
            expected_count = self.parameter.expected_count
            regex_match = self.parameter.regex_match or False
            skip_malformed = self.parameter.skip_malformed

            # Parse expected_count
            if expected_count is None:
                # No expected_count specified - require at least 1 match
                min_count = 1
                max_count = float('inf')
            elif isinstance(expected_count, int):
                min_count = expected_count
                max_count = expected_count
            elif isinstance(expected_count, dict):
                min_count = expected_count.get('min', 0)
                max_count = expected_count.get('max', float('inf'))
            else:
                return TestResult.execution_error(None, "expected_count must be int, dict with 'min'/'max', or None (at least 1)")

            try:
                # Check if file is empty (edge case handling)
                import os
                if os.path.getsize(dst) == 0:
                    return TestResult.failed(['JSONL file is empty (0 bytes)'])
                matching_count = 0
                total_lines = 0
                malformed_count = 0

                with open(dst, 'r') as f:
                    for line_num, line in enumerate(f, 1):
                        line = line.strip()

                        # Skip blank lines
                        if not line:
                            continue

                        total_lines += 1

                        # Try to parse JSON
                        try:
                            data = json.loads(line)
                        except json.JSONDecodeError as e:
                            malformed_count += 1
                            if not skip_malformed:
                                return TestResult.failed([
                                    f'Malformed JSON on line {line_num}: {e}',
                                    f'Line content: {line[:200]}'
                                ])
                            continue

                        # If no conditions, count all valid JSON lines
                        if not conditions:
                            matching_count += 1
                            continue

                        # Check all conditions for this line
                        all_conditions_met = True

                        for key_path, expected_value in conditions.items():
                            value, exists = _get_nested_value(data, key_path)

                            if not exists:
                                all_conditions_met = False
                                break

                            # Handle multiple values from wildcards
                            if isinstance(value, list):
                                any_match = False
                                for v in value:
                                    is_match, msg = _compare_values(self, v, expected_value, regex_match)
                                    if is_match:
                                        any_match = True
                                        break
                                if not any_match:
                                    all_conditions_met = False
                                    break
                            else:
                                is_match, msg = _compare_values(self, value, expected_value, regex_match)
                                if not is_match:
                                    all_conditions_met = False
                                    break

                        if all_conditions_met:
                            matching_count += 1

                # Log malformed lines if any
                if malformed_count > 0:
                    log.warning(f"Skipped {malformed_count} malformed JSON lines in {dst}")

                # Check if count is within expected range
                if min_count <= matching_count <= max_count:
                    messages = [f'Found {matching_count} matching lines']
                    if self.parameter.expected_count is None:
                        messages[0] += f' (expected at least 1)'
                    elif min_count == max_count:
                        messages[0] += f' (expected exactly {min_count})'
                    else:
                        messages[0] += f' (expected {min_count}-{max_count if max_count != float("inf") else "∞"})'
                    messages.append(f'Total valid lines: {total_lines - malformed_count}')
                    if conditions:
                        messages.append(f'Conditions: {conditions}')
                    return TestResult.success(messages)
                else:
                    messages = [
                        f'Found {matching_count} matching lines',
                    ]
                    if self.parameter.expected_count is None:
                        messages.append(f'Expected: at least 1')
                    elif min_count == max_count:
                        messages.append(f'Expected: {min_count}')
                    else:
                        messages.append(f'Expected: {min_count}-{max_count if max_count != float("inf") else "∞"}')
                    messages.append(f'Total valid lines: {total_lines - malformed_count}')
                    if conditions:
                        messages.append(f'Conditions: {conditions}')
                    return TestResult.failed(messages)

            except FileNotFoundError:
                return TestResult.failed([f'JSONL file {dst} does not exist'])
            except (PermissionError, OSError) as e:
                return TestResult.execution_error(e, f"Cannot read JSONL file {dst}")

        except Exception as e:
            log.error(f"Unexpected error in JSONL line count test: {e}", exc_info=True)
            return TestResult.execution_error(e, "Unexpected error in JSONL line count test")


@attrs.define
class ValueInAnyLineParameter(Parameter):
    dst: str
    key_path: str
    expected_value: Union[str, int, float, bool, None]
    regex_match: Optional[bool] = False
    skip_malformed: Optional[bool] = True


@attrs.define
class ValueInAnyLine(BasicTest):
    testname: ClassVar[str] = 'value_in_any_line'
    testdescription: ClassVar[str] = 'tests if specified key path with expected value exists in any line of JSONL file'
    host_mode_category: ClassVar[HostModeCategory] = HostModeCategory.FILE_CONTENT

    name: str
    parameter: ValueInAnyLineParameter
    description: Optional[str] = ''
    variable_metadata: Optional[dict] = None

    def test(self):
        try:
            dst, status = self.resolve_globfilepath(self.parameter.dst)
            if not dst:
                return TestResult.failed([f'JSONL file {self.parameter.dst} not found ({status})'])

            log.debug(f'dst file {dst} will be used for test {self.name}')

            key_path = self.parameter.key_path
            expected_value = self.parameter.expected_value
            regex_match = self.parameter.regex_match or False
            skip_malformed = self.parameter.skip_malformed

            try:
                # Check if file is empty (edge case handling)
                import os
                if os.path.getsize(dst) == 0:
                    return TestResult.failed(['JSONL file is empty (0 bytes)'])
                matching_lines = []
                total_lines = 0
                malformed_count = 0
                lines_with_key = 0

                with open(dst, 'r') as f:
                    for line_num, line in enumerate(f, 1):
                        line = line.strip()

                        # Skip blank lines
                        if not line:
                            continue

                        total_lines += 1

                        # Try to parse JSON
                        try:
                            data = json.loads(line)
                        except json.JSONDecodeError as e:
                            malformed_count += 1
                            if not skip_malformed:
                                return TestResult.failed([
                                    f'Malformed JSON on line {line_num}: {e}',
                                    f'Line content: {line[:200]}'
                                ])
                            continue

                        # Get value at key path
                        value, exists = _get_nested_value(data, key_path)

                        if not exists:
                            continue

                        lines_with_key += 1

                        # Handle multiple values from wildcards
                        if isinstance(value, list):
                            for v in value:
                                is_match, msg = _compare_values(self, v, expected_value, regex_match)
                                if is_match:
                                    matching_lines.append((line_num, v, msg))
                                    break  # Only record once per line
                        else:
                            is_match, msg = _compare_values(self, value, expected_value, regex_match)
                            if is_match:
                                matching_lines.append((line_num, value, msg))

                # Log malformed lines if any
                if malformed_count > 0:
                    log.warning(f"Skipped {malformed_count} malformed JSON lines in {dst}")

                # Determine success
                if matching_lines:
                    messages = [
                        f'Found matching value in {len(matching_lines)} line(s)',
                        f'First match: line {matching_lines[0][0]} with value "{matching_lines[0][1]}"'
                    ]
                    if len(matching_lines) > 1:
                        messages.append(f'Additional matches on lines: {[ln for ln, _, _ in matching_lines[1:4]]}')
                    return TestResult.success(messages)
                else:
                    messages = [
                        f'No lines found with key path "{key_path}" matching expected value "{expected_value}"',
                        f'Analyzed {total_lines - malformed_count} valid JSON lines'
                    ]
                    if lines_with_key > 0:
                        messages.append(f'Found {lines_with_key} lines with key "{key_path}" but none matched the expected value')
                    else:
                        messages.append(f'Key path "{key_path}" not found in any line')
                    return TestResult.failed(messages)

            except FileNotFoundError:
                return TestResult.failed([f'JSONL file {dst} does not exist'])
            except (PermissionError, OSError) as e:
                return TestResult.execution_error(e, f"Cannot read JSONL file {dst}")

        except Exception as e:
            log.error(f"Unexpected error in JSONL value in any line test: {e}", exc_info=True)
            return TestResult.execution_error(e, "Unexpected error in JSONL value in any line test")
