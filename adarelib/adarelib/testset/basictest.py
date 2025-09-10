# external imports
import glob
from typing import Optional, ClassVar, Dict, Any, List, Tuple
import attrs
import re

# internal imports
from adarelib.testset.yaml.customtags import YamlCustomTag
from adarelib.common.variables import VariableRegistry

# configure logging
import logging

log = logging.getLogger(__name__)


def resolve_var_in_match_regex(regex_match, variables):
    """
    resolve the variable in a regex match (which is a regex expression)
    :param regex_match: regex match object
    :param variables: dict with variables
    :return:
    """
    key = regex_match.group(1)
    if key in variables.keys():
        return re.escape(variables[key])
    log.error(f'variable {key} can\'t be replaced because it\'s not present in the variable file')
    return ''


def resolve_var_in_match_string(regex_match, variables):
    """
    resolve the variable in a regex match (which is a simple string)
    :param regex_match: regex match object
    :param variables: dict with variables
    :return:
    """
    key = regex_match.group(1)
    if key in variables.keys():
        return variables[key]
    log.error(f'variable {key} can\'t be replaced because it\'s not present in the variable file')
    return ''


def resolve_yamlobj_in_dict(dictionary: dict):
    """
    resolve all YamlCustomTag objects in a dict with their __repr__ value
    :param dictionary: dict to replace YamlCustomTag objects in
    :return:
    """
    new_d = {}
    for key, value in dictionary.items():
        if isinstance(value, YamlCustomTag):
            new_d[key] = value.__repr__()
        elif isinstance(value, dict):
            new_value = resolve_yamlobj_in_dict(value)
            new_d[key] = new_value
        elif isinstance(value, list):
            new_value = []
            for v in value:
                if isinstance(v, YamlCustomTag):
                    new_value.append(v.__repr__())
                else:
                    new_value.append(v)
            new_d[key] = new_value
        else:
            new_d[key] = value
    return new_d


@attrs.define
class Parameter:
    """
    Parameter is the base class for all test parameters.
    """
    pass


@attrs.define
class BasicTest:
    """
    BasicTest is the base class for all tests. It provides basic functionality like setting the result of a test.
    """
    testname: ClassVar[str] = ''
    testdescription: ClassVar[str] = ''

    name: str
    parameter: Parameter
    description: Optional[str]
    variable_metadata: Optional[Dict[str, Any]]

    def resolve_globfilepath(self, globfilepath: str) -> tuple[str, str]:
        """
        find a file that matches the given glob expression and return it. If no file is found or more than one file is
        found, return an error message.
        :param globfilepath: glob expression to find a file
        :return: (filepath, error message)
        """
        found_files = list(glob.glob(globfilepath))
        if not found_files:
            return "", "no files match the given path (glob) expression"
        elif len(found_files) > 1:
            return "", f"{len(found_files)} files found that match given path (glob) expression"
        else:
            return found_files[0], ""


    # === PLACEHOLDER HELPER METHODS ===
    
    def has_placeholders(self, text: str) -> bool:
        """Check if text has any {{ }} placeholders."""
        return '{{' in text and '}}' in text
    
    def get_placeholders(self, text: str) -> List[str]:
        """Get all placeholder names from text."""
        matches = re.findall(r'\{\{\s*([^}]+)\s*\}\}', text)
        return [match.strip() for match in matches]
    
    def get_placeholder_metadata(self, placeholder_name: str) -> Dict[str, Any]:
        """Get metadata for specific placeholder."""
        if not self.variable_metadata:
            return {}
        return self.variable_metadata.get(placeholder_name, {})
    
    def has_tolerance_metadata(self, placeholder_name: str) -> bool:
        """Check if placeholder has tolerance metadata."""
        metadata = self.get_placeholder_metadata(placeholder_name)
        return 'tolerance' in metadata and bool(metadata['tolerance'])
    
    def compare_with_placeholder(self, placeholder_name: str, actual_value: str) -> Tuple[bool, str]:
        """Compare actual value with placeholder based on its type (regex, timestamp, string)."""
        metadata = self.get_placeholder_metadata(placeholder_name)
        placeholder_type = metadata.get('type', 'string')
        
        if placeholder_type == 'regex':
            import re
            try:
                regex_pattern = metadata.get('resolved_value', metadata.get('raw_value', '.*'))
                compiled_regex = re.compile(regex_pattern)
                if compiled_regex.match(actual_value):
                    return True, f"Regex match: '{actual_value}' matches pattern '{regex_pattern}'"
                else:
                    return False, f"Regex no match: '{actual_value}' doesn't match pattern '{regex_pattern}'"
            except re.error as e:
                return False, f"Regex error: Invalid pattern '{regex_pattern}' - {e}"
        
        elif placeholder_type == 'timestamp':
            return self._compare_timestamp_with_tolerance(metadata, actual_value)
        
        else:
            # Default: exact string comparison
            expected = metadata.get('resolved_value', '')
            success = actual_value == expected
            return success, f"Exact comparison: {'match' if success else 'no match'}"

    def _compare_timestamp_with_tolerance(self, metadata: dict, actual_value: str) -> Tuple[bool, str]:
        """Compare timestamp values with tolerance."""
        log.info(f"CLAUDE: Starting tolerance comparison - metadata: {metadata}")
        log.info(f"CLAUDE: Actual value from file: '{actual_value}'")
        
        if 'tolerance' not in metadata or not metadata['tolerance']:
            # No tolerance - do exact comparison  
            expected = metadata.get('resolved_value', '')
            success = actual_value == expected
            return success, f"Exact comparison: {'match' if success else 'no match'}"
        
        # Has tolerance - do timestamp comparison
        try:
            import datetime
            
            # Parse actual timestamp using format metadata if available
            actual_dt = self._parse_timestamp_with_format(actual_value, metadata)
            log.info(f"CLAUDE: Parsed actual timestamp: {actual_dt}")
            
            # Parse original timestamp (raw_value should be in ISO format)
            raw_value = metadata.get('raw_value', '')
            log.info(f"CLAUDE: Raw timestamp value: '{raw_value}'")
            
            # Check if timestamp needs runtime resolution
            if metadata.get('needs_runtime_resolution', False) and '{{' in raw_value and '}}' in raw_value:
                log.info(f"CLAUDE: Template '{raw_value}' marked for runtime resolution")
                
                # Runtime resolution will be handled by the test execution system
                # The test execution context should have the updated variables
                # For now, we need to get the resolved timestamp from somewhere else
                
                # This is a limitation - we can't easily get the execution context here
                # But the test system should re-resolve templates with current context
                log.warning(f"Template '{raw_value}' requires runtime resolution but execution context not available in test function")
                
                # Try to extract variable name and use it if available from test parameter resolution
                # This is a workaround - ideally test resolution should happen after all variables are set
                import re
                template_match = re.search(r'\{\{\s*(\w+)\s*\}\}', raw_value)
                if template_match:
                    var_name = template_match.group(1)
                    log.info(f"CLAUDE: Extracted variable name '{var_name}' from template")
                    # The template should have been resolved during test processing
                    # If we're still seeing the template here, it means the variable was empty during test resolution
            
            # Use resolved_value instead of raw_value for comparison - this should contain the properly resolved timestamp
            comparison_value = metadata.get('resolved_value', raw_value)
            log.info(f"CLAUDE: Using resolved_value for comparison: '{comparison_value}'")

            original_dt = self._parse_timestamp_with_format(comparison_value, metadata, is_original=True)
            log.info(f"CLAUDE: Parsed original timestamp: {original_dt}")
            
            # Get tolerance range - handle both single value and array
            tolerance = metadata.get('tolerance', 0)
            log.info(f"CLAUDE: Tolerance from metadata: {tolerance}")
            
            if isinstance(tolerance, (int, float)):
                # Single value: create symmetric range around original timestamp
                abs_tolerance = abs(tolerance)
                lower_tolerance = -abs_tolerance
                upper_tolerance = abs_tolerance
            elif isinstance(tolerance, list) and len(tolerance) >= 1:
                # For array [a, b], interpret as [lower_bound, upper_bound] relative to original timestamp
                # So [0, 5] means actual can be from original+0 to original+5
                lower_tolerance = tolerance[0]
                upper_tolerance = tolerance[1] if len(tolerance) > 1 else tolerance[0]
            else:
                lower_tolerance = 0
                upper_tolerance = 0
                
            log.info(f"CLAUDE: Calculated tolerance range: {lower_tolerance}s to {upper_tolerance}s")
            
            # Calculate difference
            diff_seconds = (original_dt - actual_dt).total_seconds()
            log.info(f"CLAUDE: Time difference: {diff_seconds}s")
            
            # Check if within tolerance
            within_range = lower_tolerance <= diff_seconds <= upper_tolerance
            log.info(f"CLAUDE: Within tolerance? {within_range} ({lower_tolerance} <= {diff_seconds} <= {upper_tolerance})")
            
            if within_range:
                return True, f"Within tolerance: {diff_seconds}s difference (range: {lower_tolerance}s to {upper_tolerance}s)"
            else:
                return False, f"Outside tolerance: {diff_seconds}s difference (range: {lower_tolerance}s to {upper_tolerance}s)"
                
        except Exception as e:
            # Fallback to string comparison
            expected = metadata.get('resolved_value', '')
            success = actual_value == expected
            return success, f"Tolerance comparison failed ({e}), used string comparison"
    
    def _parse_timestamp_with_format(self, timestamp_str: str, metadata: dict, is_original: bool = False) -> 'datetime.datetime':
        """
        Parse timestamp using format metadata.

        Behavior:
        - is_original == True (template/expected side):
            * Never convert timezones.
            * If naive, assume UTC and attach tzinfo=UTC (label only, no clock change).
            * If aware, return as-is.

        - is_original == False (actual/observed side):
            * DEFAULT: Treat naive strings as LOCAL wall time (label with system tz, no clock change).
            This avoids the "assume UTC then convert to local" double-shift.
            * If metadata['localtime'] is explicitly False, treat naive as UTC and convert to system local.
            * If the parsed value is already tz-aware, convert to system local for consistent comparison display.

        Notes:
        - Subtraction of tz-aware datetimes is done on absolute instants, so comparison is correct.
        - Provide `metadata['format']` for deterministic parsing when possible.
        """
        import datetime
        from dateutil import parser as _parser

        _SYSTEM_TZ = datetime.datetime.now().astimezone().tzinfo

        def _finalize(dt: datetime.datetime) -> datetime.datetime:
            if is_original:
                # Original: ensure tz-aware, but NO conversion.
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=datetime.timezone.utc)  # label as UTC, no clock shift
                return dt

            # Actual: apply interpretation rules.
            treat_as_local = metadata.get('localtime', True)  # default True to avoid double shift

            if treat_as_local:
                # Naive actuals are LOCAL wall time → label as local (no shift).
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=_SYSTEM_TZ)
                else:
                    # If already aware, normalize to local for consistency.
                    dt = dt.astimezone(_SYSTEM_TZ)
                return dt
            else:
                # Explicitly treat as UTC wall time → attach UTC if naive, then convert to local.
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=datetime.timezone.utc)  # label as UTC
                # Convert aware/UTC to system local for display/consistency.
                return dt.astimezone(_SYSTEM_TZ)

        fmt = metadata.get('format')

        # Try explicit format first
        if fmt:
            try:
                dt = datetime.datetime.strptime(timestamp_str, fmt)
                return _finalize(dt)
            except ValueError:
                # Fall through to flexible parser
                pass

        # Flexible parsing fallback
        dt = _parser.parse(timestamp_str)
        return _finalize(dt)

    def _handle_placeholders_comparison(self, actual_content: str, expected_template: str) -> Tuple[bool, str]:
        """Handle comparison when placeholders are present using string splitting approach."""
        placeholders = self.get_placeholders(expected_template)
        
        # Check if we got unconverted Jinja2 templates (client-side issue)
        for placeholder in placeholders:
            if '|' in placeholder:
                return False, f"Received unconverted Jinja2 template '{{{{ {placeholder} }}}}'. This suggests client-side variable resolution failed. Expected placeholder format: '{{{{ VARIABLE_RESOLVED }}}}'."
        
        # Split template into text parts (before/between/after placeholders)
        import re
        text_parts = re.split(r'\{\{\s*[^}]+\s*\}\}', expected_template)
        
        # Extract values by finding delimiters step by step
        current_pos = 0
        extracted_values = []
        
        for i in range(len(placeholders)):
            # Check that text before this placeholder matches
            expected_prefix = text_parts[i]
            if not actual_content[current_pos:].startswith(expected_prefix):
                return False, f"Text before '{placeholders[i]}' doesn't match. Expected: '{expected_prefix}'"
            
            # Move past the matching prefix
            current_pos += len(expected_prefix)
            
            # Find where this placeholder's value ends
            # Check if there's a meaningful next delimiter (not empty and not the last)
            if i + 1 < len(text_parts) and text_parts[i + 1]:
                # Not the last placeholder and has non-empty delimiter - find next delimiter
                next_delimiter = text_parts[i + 1]
                delimiter_pos = actual_content.find(next_delimiter, current_pos)
                if delimiter_pos == -1:
                    # If delimiter not found, handle special cases
                    if next_delimiter.strip() == "" and current_pos >= len(actual_content.rstrip()):
                        # Delimiter is trailing whitespace - extract to end of content
                        placeholder_value = actual_content[current_pos:].rstrip()
                        current_pos = len(actual_content)
                    elif next_delimiter == '\n':
                        # Special case: newline delimiter - extract to end of current line
                        line_end = actual_content.find('\n', current_pos)
                        if line_end == -1:
                            # No newline found - take to end of content
                            placeholder_value = actual_content[current_pos:]
                            current_pos = len(actual_content)
                        else:
                            # Extract to the newline
                            placeholder_value = actual_content[current_pos:line_end]
                            current_pos = line_end
                    else:
                        return False, f"Couldn't find delimiter '{repr(next_delimiter)}' after placeholder '{placeholders[i]}'"
                else:
                    # Extract value between current position and delimiter
                    placeholder_value = actual_content[current_pos:delimiter_pos]
                    current_pos = delimiter_pos
            elif i + 1 < len(text_parts) and not text_parts[i + 1] and i + 1 < len(placeholders):
                # Empty delimiter between placeholders (not at end) - this is an error
                return False, f"Empty delimiter after '{placeholders[i]}' - cannot determine where placeholder ends. Please add text between placeholders."
            else:
                # Last placeholder or placeholder at end with empty suffix - take everything to the end
                final_suffix = text_parts[-1] if len(text_parts) > len(placeholders) and text_parts[-1] else ""
                if final_suffix:
                    # Find the final suffix to determine where placeholder ends
                    suffix_pos = actual_content.rfind(final_suffix)
                    if suffix_pos == -1 or suffix_pos < current_pos:
                        return False, f"Couldn't find final text '{final_suffix}' after last placeholder '{placeholders[i]}'"
                    placeholder_value = actual_content[current_pos:suffix_pos]
                    current_pos = suffix_pos
                else:
                    # No final suffix - take everything to end
                    placeholder_value = actual_content[current_pos:]
                    current_pos = len(actual_content)
            
            extracted_values.append(placeholder_value)
        
        # Validate each extracted value using its metadata
        validation_messages = []
        for i, placeholder in enumerate(placeholders):
            actual_value = extracted_values[i]
            
            success, msg = self.compare_with_placeholder(placeholder, actual_value)
            validation_messages.append(f"{placeholder}: {msg}")
            
            if not success:
                return False, f"Validation failed - {'; '.join(validation_messages)}"
        
        return True, f"All placeholders valid - {'; '.join(validation_messages)}"

    def test(self):
        """
        This method has to be implemented by all subclasses. It should return a TestResult object.
        :return:
        """
        pass
