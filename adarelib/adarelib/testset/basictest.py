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
        if 'tolerance' not in metadata or not metadata['tolerance']:
            # No tolerance - do exact comparison  
            expected = metadata.get('resolved_value', '')
            success = actual_value == expected
            return success, f"Exact comparison: {'match' if success else 'no match'}"
        
        # Has tolerance - do timestamp comparison
        try:
            import dateutil.parser
            import datetime
            
            # Parse actual timestamp
            actual_dt = dateutil.parser.parse(actual_value)
            
            # Parse original timestamp
            raw_value = metadata.get('raw_value', '')
            original_dt = dateutil.parser.parse(raw_value)
            
            # Get tolerance range - handle both single value and array
            tolerance = metadata.get('tolerance', 0)
            if isinstance(tolerance, (int, float)):
                upper_tolerance = tolerance
                lower_tolerance = -tolerance
            elif isinstance(tolerance, list) and len(tolerance) >= 1:
                upper_tolerance = tolerance[0]
                lower_tolerance = tolerance[1] if len(tolerance) > 1 else -upper_tolerance
            else:
                upper_tolerance = 0
                lower_tolerance = 0
            
            # Calculate difference
            diff_seconds = (actual_dt - original_dt).total_seconds()
            
            # Check if within tolerance
            within_range = lower_tolerance <= diff_seconds <= upper_tolerance
            
            if within_range:
                return True, f"Within tolerance: {diff_seconds}s difference (range: {lower_tolerance}s to {upper_tolerance}s)"
            else:
                return False, f"Outside tolerance: {diff_seconds}s difference (range: {lower_tolerance}s to {upper_tolerance}s)"
                
        except Exception as e:
            # Fallback to string comparison
            expected = metadata.get('resolved_value', '')
            success = actual_value == expected
            return success, f"Tolerance comparison failed ({e}), used string comparison"

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
                    return False, f"Couldn't find delimiter '{next_delimiter}' after placeholder '{placeholders[i]}'"
                
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
            
            success, msg = self.compare_with_tolerance(placeholder, actual_value)
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
