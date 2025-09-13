# external imports
import attrs
from pathlib import Path
import json
import re
from typing import ClassVar, Optional, Union

# internal imports
from adarelib.testset.basictest import BasicTest, Parameter
from adarelib.event.event import TestResult
from adarelib.constants import StatusEnum

# configure logging
import logging
log = logging.getLogger(__name__)


@attrs.define
class ContainsKeyParameter(Parameter):
    dst: str
    key_path: str

@attrs.define
class ContainsKey(BasicTest):
    testname: ClassVar[str] = 'contains_key'
    testdescription: ClassVar[str] = 'tests if JSON file contains specified key path (supports dot notation like "user.profile.name")'

    name: str
    parameter: ContainsKeyParameter
    description: Optional[str] = ''
    variable_metadata: Optional[dict] = None

    def _get_nested_value(self, data, key_path):
        """Navigate nested dictionary using dot notation"""
        keys = key_path.split('.')
        current = data

        for key in keys:
            if isinstance(current, dict) and key in current:
                current = current[key]
            else:
                return None, False
        return current, True

    def test(self):
        try:
            dst, status = self.resolve_globfilepath(self.parameter.dst)
            if not dst:
                return TestResult.failed([f'JSON file {self.parameter.dst} not found ({status})'])

            log.debug(f'dst file {dst} will be used for test {self.name}')

            key_path = self.parameter.key_path

            try:
                with open(dst, 'r') as f:
                    data = json.load(f)

                value, exists = self._get_nested_value(data, key_path)

                if exists:
                    return TestResult.success([f'key path "{key_path}" exists with value: {value}'])
                else:
                    return TestResult.failed([f'key path "{key_path}" does not exist'])

            except json.JSONDecodeError as e:
                return TestResult.failed([f"Invalid JSON in file {dst}: {e}"])
            except FileNotFoundError:
                return TestResult.failed([f'JSON file {dst} does not exist'])
            except (PermissionError, OSError) as e:
                return TestResult.execution_error(e, f"Cannot read JSON file {dst}")

        except Exception as e:
            return TestResult.execution_error(e, "Unexpected error in JSON contains key test")


@attrs.define
class ValueMatchesParameter(Parameter):
    dst: str
    key_path: str
    expected_value: Union[str, int, float, bool, None]
    regex_match: Optional[bool] = False
    wildcard_mode: Optional[str] = "any"  # "any" or "all" - for wildcard matches

@attrs.define
class ValueMatches(BasicTest):
    testname: ClassVar[str] = 'value_matches'
    testdescription: ClassVar[str] = 'tests if JSON value at key path matches expected value using placeholders (supports wildcards [*] and * with any/all modes)'

    name: str
    parameter: ValueMatchesParameter
    description: Optional[str] = ''
    variable_metadata: Optional[dict] = None

    def _get_nested_value(self, data, key_path):
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

    def _compare_values(self, actual_value, expected_value):
        """Compare values using the same logic as FileContentEquals"""

        # Check for YamlRegexString objects (!re syntax) - handle like placeholder system
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
            pass  # YamlRegexString not available, continue with normal processing

        expected_str = str(expected_value)

        if not self.has_placeholders(expected_str):
            # No placeholders - check for regex_match flag
            if self.parameter.regex_match and isinstance(expected_value, str):
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
            # Has placeholders - use placeholder system (handles regex and timestamp with tolerance)
            placeholder_names = self.get_placeholders(expected_str)
            if len(placeholder_names) == 1:
                placeholder_name = placeholder_names[0]
                try:
                    return self.compare_with_placeholder(placeholder_name, str(actual_value))
                except Exception as e:
                    return False, f"placeholder comparison error: {e}"
            else:
                return False, f"expected 1 placeholder for single value comparison, got {len(placeholder_names)}"

    def _handle_wildcard_matching(self, values, expected_value, wildcard_mode, key_path):
        """Handle matching logic for wildcard results with 'any' or 'all' modes"""
        if not values:
            return TestResult.failed([f'no values found for wildcard path "{key_path}"'])

        # Validate wildcard_mode
        if wildcard_mode not in ['any', 'all']:
            return TestResult.execution_error(None, f"Invalid wildcard_mode: {wildcard_mode}. Must be 'any' or 'all'")

        matches = []
        non_matches = []

        # Check each value against expected using unified comparison method
        for i, value in enumerate(values):
            is_match, message = self._compare_values(value, expected_value)
            if is_match:
                matches.append((i, value, message))
            else:
                non_matches.append((i, value, message))

        # Apply wildcard mode logic
        if wildcard_mode == 'any':
            if matches:
                match_details = [f"element[{i}]: {val}" for i, val, _ in matches[:3]]  # Show first 3 matches
                if len(matches) > 3:
                    match_details.append(f"... and {len(matches) - 3} more matches")
                return TestResult.success([
                    f'wildcard path "{key_path}" matched {len(matches)}/{len(values)} values (mode: any)',
                    f'matching values: {", ".join(match_details)}'
                ])
            else:
                return TestResult.failed([
                    f'wildcard path "{key_path}" matched 0/{len(values)} values (mode: any)',
                    f'expected: "{expected_value}"',
                    f'got values: {[val for _, val, _ in non_matches[:5]]}'  # Show first 5 non-matches
                ])
        else:  # wildcard_mode == 'all'
            if not non_matches:
                return TestResult.success([
                    f'wildcard path "{key_path}" matched all {len(values)} values (mode: all)',
                    f'all values equal: "{expected_value}"'
                ])
            else:
                non_match_details = [f"element[{i}]: {val}" for i, val, _ in non_matches[:3]]  # Show first 3 non-matches
                if len(non_matches) > 3:
                    non_match_details.append(f"... and {len(non_matches) - 3} more non-matches")
                return TestResult.failed([
                    f'wildcard path "{key_path}" matched {len(matches)}/{len(values)} values (mode: all)',
                    f'expected: "{expected_value}"',
                    f'non-matching values: {", ".join(non_match_details)}'
                ])

    def test(self):
        try:
            dst, status = self.resolve_globfilepath(self.parameter.dst)
            if not dst:
                return TestResult.failed([f'JSON file {self.parameter.dst} not found ({status})'])

            log.debug(f'dst file {dst} will be used for test {self.name}')

            key_path = self.parameter.key_path
            expected_value = self.parameter.expected_value

            try:
                with open(dst, 'r') as f:
                    data = json.load(f)

                value, exists = self._get_nested_value(data, key_path)

                if not exists:
                    return TestResult.failed([f'key path "{key_path}" does not exist'])

                # Handle wildcard mode - check if we have multiple values
                wildcard_mode = getattr(self.parameter, 'wildcard_mode', 'any')
                if isinstance(value, list) and len(value) > 1:
                    # Multiple values from wildcard matching
                    return self._handle_wildcard_matching(value, expected_value, wildcard_mode, key_path)
                elif isinstance(value, list) and len(value) == 1:
                    # Single value from wildcard (treat as regular match)
                    value = value[0]

                # Regular single value matching using unified comparison
                is_match, message = self._compare_values(value, expected_value)
                if is_match:
                    return TestResult.success([message])
                else:
                    return TestResult.failed([message])

            except json.JSONDecodeError as e:
                return TestResult.failed([f"Invalid JSON in file {dst}: {e}"])
            except FileNotFoundError:
                return TestResult.failed([f'JSON file {dst} does not exist'])
            except (PermissionError, OSError) as e:
                return TestResult.execution_error(e, f"Cannot read JSON file {dst}")

        except Exception as e:
            return TestResult.execution_error(e, "Unexpected error in JSON value matches test")


@attrs.define
class ArrayContainsParameter(Parameter):
    dst: str
    array_path: str
    expected_element: Union[str, int, float, bool, dict, list]

@attrs.define
class ArrayContains(BasicTest):
    testname: ClassVar[str] = 'array_contains'
    testdescription: ClassVar[str] = 'tests if JSON array at specified path contains expected element'

    name: str
    parameter: ArrayContainsParameter
    description: Optional[str] = ''
    variable_metadata: Optional[dict] = None

    def _get_nested_value(self, data, key_path):
        """Navigate nested dictionary using dot notation"""
        keys = key_path.split('.')
        current = data

        for key in keys:
            if isinstance(current, dict) and key in current:
                current = current[key]
            else:
                return None, False
        return current, True

    def test(self):
        try:
            dst, status = self.resolve_globfilepath(self.parameter.dst)
            if not dst:
                return TestResult.failed([f'JSON file {self.parameter.dst} not found ({status})'])

            log.debug(f'dst file {dst} will be used for test {self.name}')

            array_path = self.parameter.array_path
            expected_element = self.parameter.expected_element  # Keep as string

            try:
                with open(dst, 'r') as f:
                    data = json.load(f)

                array, exists = self._get_nested_value(data, array_path)

                if not exists:
                    return TestResult.failed([f'array path "{array_path}" does not exist'])

                if not isinstance(array, list):
                    return TestResult.failed([f'path "{array_path}" is not an array, got {type(array).__name__}'])

                # Check if expected_element has placeholders for regex/timestamp tolerance
                expected_str = str(expected_element)
                if self.has_placeholders(expected_str):
                    # Use placeholder comparison for each array element
                    placeholder_names = self.get_placeholders(expected_str)
                    if len(placeholder_names) == 1:
                        placeholder_name = placeholder_names[0]
                        for i, element in enumerate(array):
                            try:
                                success, message = self.compare_with_placeholder(placeholder_name, str(element))
                                if success:
                                    return TestResult.success([f'array element [{i}] matches placeholder: {message}'])
                            except Exception as e:
                                continue  # Try next element
                        return TestResult.failed([f'no array element matches placeholder "{placeholder_name}"'])
                    else:
                        return TestResult.failed([f'expected 1 placeholder for array comparison, got {len(placeholder_names)}'])
                else:
                    # Regular direct comparison
                    if expected_element in array:
                        return TestResult.success([f'array contains expected element: {expected_element}'])
                    else:
                        return TestResult.failed([f'array does not contain expected element: {expected_element}'])

            except json.JSONDecodeError as e:
                return TestResult.failed([f"Invalid JSON in file {dst}: {e}"])
            except FileNotFoundError:
                return TestResult.failed([f'JSON file {dst} does not exist'])
            except (PermissionError, OSError) as e:
                return TestResult.execution_error(e, f"Cannot read JSON file {dst}")

        except Exception as e:
            return TestResult.execution_error(e, "Unexpected error in JSON array contains test")