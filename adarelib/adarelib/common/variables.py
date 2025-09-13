from __future__ import annotations
from enum import Enum
from typing import Any, Dict, Union, Optional, Type
from abc import ABC, abstractmethod
import attrs
import re
import datetime
import dateutil.parser
import dateutil.tz
from pathlib import Path
import pytz

import logging
log = logging.getLogger(__name__)


class VariableType(Enum):
    """Variable types with semantic meaning for validation and processing."""
    STRING = "string"
    REGEX = "regex" 
    TIMESTAMP = "timestamp"
    PATH = "path"
    INTEGER = "integer"
    FLOAT = "float"
    BOOLEAN = "boolean"
    LIST = "list"
    DICT = "dict"


class ValidationError(Exception):
    """Raised when variable validation fails."""
    pass


@attrs.define
class TimestampMetadata:
    """Metadata for timestamp variables supporting timezone, format, tolerance, and localtime conversion."""
    
    timezone: Optional[str] = None
    format_str: Optional[str] = None
    tolerance_upper: int = 0
    tolerance_lower: int = 0
    localtime: bool = False
    
    def to_dict(self) -> Dict[str, Any]:
        """Serialize to dict."""
        result = {}
        if self.timezone:
            result['timezone'] = self.timezone
        if self.format_str:
            result['format'] = self.format_str
        if self.tolerance_upper or self.tolerance_lower:
            result['tolerance'] = [self.tolerance_upper, self.tolerance_lower]
        if self.localtime:
            result['localtime'] = self.localtime
        return result
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'TimestampMetadata':
        """Create from dict."""
        tolerance = data.get('tolerance', [0, 0])
        if isinstance(tolerance, (list, tuple)) and len(tolerance) >= 2:
            tolerance_upper, tolerance_lower = tolerance[0], tolerance[1]
        elif isinstance(tolerance, (int, float)):
            tolerance_upper = tolerance_lower = tolerance
        else:
            tolerance_upper = tolerance_lower = 0
            
        return cls(
            timezone=data.get('timezone'),
            format_str=data.get('format'),
            tolerance_upper=tolerance_upper,
            tolerance_lower=tolerance_lower,
            localtime=data.get('localtime', False)
        )
    
    def get_jinja_filters(self, variable_registry: 'VariableRegistry') -> Dict[str, Any]:
        """Get Jinja2 filters for timestamp operations with metadata capture."""
        
        def timezone_filter(value, tz_name):
            """Convert timestamp to specified timezone and capture metadata."""
            # Find the variable this filter is being applied to
            source_var = self._find_variable_by_value(variable_registry, value, VariableType.TIMESTAMP)
            if source_var:
                # Update the variable's metadata
                if not source_var.structured_metadata:
                    source_var.structured_metadata = TimestampMetadata()
                source_var.structured_metadata.timezone = tz_name
                source_var.metadata['timezone'] = tz_name
                log.debug(f"Captured timezone filter '{tz_name}' for variable")
            
            # Return the original value for continued processing
            return value
        
        def format_filter(value, format_str):
            """Set timestamp format and capture metadata."""
            # Find the variable this filter is being applied to  
            source_var = self._find_variable_by_value(variable_registry, value, VariableType.TIMESTAMP)
            if source_var:
                # Update the variable's metadata
                if not source_var.structured_metadata:
                    source_var.structured_metadata = TimestampMetadata()
                source_var.structured_metadata.format_str = format_str
                source_var.metadata['format'] = format_str
                log.debug(f"Captured format filter '{format_str}' for variable")
            
            # Return the original value for continued processing
            return value
        
        def tolerance_filter(value, upper, lower=None):
            """Set timestamp tolerance and return placeholder for test-specific processing."""
            if lower is None:
                lower = -upper  # Symmetric tolerance
            
            # Find the variable this filter is being applied to
            source_var = self._find_variable_by_value(variable_registry, value, VariableType.TIMESTAMP)
            if source_var:
                # Update the variable's metadata
                if not source_var.structured_metadata:
                    source_var.structured_metadata = TimestampMetadata()
                source_var.structured_metadata.tolerance_upper = upper
                source_var.structured_metadata.tolerance_lower = lower
                source_var.metadata['tolerance'] = [upper, lower]
                log.debug(f"Captured tolerance filter '{upper},{lower}' for variable '{source_var.name}'")
                
                # Create placeholder name and register metadata
                placeholder_name = f"{source_var.name.upper()}_RESOLVED"
                
                # Register this placeholder in the variable registry for context generation
                if not hasattr(variable_registry, '_placeholder_metadata'):
                    variable_registry._placeholder_metadata = {}
                
                # Create flattened metadata structure for easier access
                flattened_metadata = {
                    'original_name': source_var.name,
                    'type': source_var.type.value,
                    'raw_value': source_var.get_string_value(),
                }
                
                # Add structured metadata fields directly to the top level
                flattened_metadata.update(source_var.structured_metadata.to_dict())
                
                # Also include any additional metadata
                flattened_metadata.update(source_var.metadata)
                
                variable_registry._placeholder_metadata[placeholder_name] = flattened_metadata
                
                log.debug(f"Created placeholder '{placeholder_name}' for tolerance filter")
                
                # Return placeholder instead of original value - this is the key change!
                return f"{{{{ {placeholder_name} }}}}"
            
            # Fallback: return original value if variable not found
            return value
        
        def localtime_filter(value):
            """Capture localtime filter metadata for server-side processing."""
            # Find the variable this filter is being applied to
            source_var = self._find_variable_by_value(variable_registry, value, VariableType.TIMESTAMP)
            if source_var:
                # Update the variable's metadata
                if not source_var.structured_metadata:
                    source_var.structured_metadata = TimestampMetadata()
                source_var.structured_metadata.localtime = True
                source_var.metadata['localtime'] = True
                log.debug(f"Captured localtime filter for variable")
            
            # Return the original value for continued processing (like timezone/format filters)
            return value

        return {
            'timezone': timezone_filter,
            'format': format_filter,
            'tolerance': tolerance_filter,
            'localtime': localtime_filter
        }
    
    def _find_variable_by_value(self, variable_registry: 'VariableRegistry', value: Any, var_type: VariableType) -> Optional['Variable']:
        """Find a variable in the registry by matching its value and type."""
        log.debug(f"Finding variable by value='{value}' (type: {type(value).__name__}) with var_type={var_type}")
        
        for var_name, variable in variable_registry.variables.items():
            log.debug(f"Checking variable '{var_name}': value='{variable.value}' (type: {type(variable.value).__name__}), var_type={variable.type}")
            
            # For timestamp variables, try both exact match and string representation match
            if variable.type == var_type:
                if variable.value == value:
                    log.debug(f"Exact match found for variable '{var_name}'")
                    return variable
                elif var_type == VariableType.TIMESTAMP:
                    # Try comparing string representations
                    var_str = variable.get_string_value()
                    value_str = str(value)
                    log.debug(f"String comparison - var_str='{var_str}' vs value_str='{value_str}'")
                    if var_str == value_str:
                        log.debug(f"String match found for timestamp variable '{var_name}'")
                        return variable
        
        log.debug(f"No variable found for value='{value}' with var_type={var_type}")
        return None


@attrs.define
class Variable:
    """
    Typed variable with validation and conversion capabilities.
    
    Supports both explicit type definition and YAML tag inference.
    Enhanced with metadata support for advanced variable features.
    """
    value: Any
    type: VariableType
    description: str = ""
    metadata: Dict[str, Any] = attrs.field(factory=dict)
    structured_metadata: Optional[Any] = None  # Type-specific metadata objects
    name: str = ""  # Variable name for reference in filters
    
    def __post_init__(self):
        """Validate and coerce value on creation."""
        self.value = self._validate_and_coerce(self.value, self.type)
        # Create structured metadata if available
        if self.metadata and not self.structured_metadata:
            self.structured_metadata = self._create_structured_metadata()
    
    def _create_structured_metadata(self) -> Optional[Any]:
        """Create type-specific structured metadata from metadata dict."""
        if self.type == VariableType.TIMESTAMP:
            return TimestampMetadata.from_dict(self.metadata)
        return None
    
    @classmethod
    def from_dict(cls, data: dict) -> 'Variable':
        """Create Variable from explicit dict definition."""
        return cls(
            value=data["value"],
            type=VariableType(data["type"]), 
            description=data.get("description", ""),
            metadata=data.get("metadata", {}),
            structured_metadata=data.get("structured_metadata")
        )
    
    @classmethod
    def from_yaml_tag(cls, yaml_obj) -> 'Variable':
        """Create Variable from YAML custom tag with type inference."""
        from adarelib.testset.yaml.customtags import (
            YamlString, YamlRegexString, YamlTimestamp, YamlPath
        )
        
        type_mapping = {
            YamlString: VariableType.STRING,
            YamlRegexString: VariableType.REGEX,
            YamlTimestamp: VariableType.TIMESTAMP, 
            YamlPath: VariableType.PATH,
        }
        
        var_type = type_mapping.get(type(yaml_obj))
        if not var_type:
            raise ValueError(f"Unknown YAML tag type: {type(yaml_obj)}")
        
        # Extract metadata from YAML tag if available
        metadata = {}
        if hasattr(yaml_obj, 'metadata') and yaml_obj.metadata:
            metadata = yaml_obj.metadata
        # For timestamp objects, extract metadata from their attributes
        elif var_type == VariableType.TIMESTAMP and hasattr(yaml_obj, 'tolerance'):
            metadata = {
                'tolerance': [yaml_obj.tolerance, yaml_obj.tolerance] if hasattr(yaml_obj, 'tolerance') else [0, 0]
            }
            if hasattr(yaml_obj, 'timestamp_format_comparison') and yaml_obj.timestamp_format_comparison:
                metadata['format'] = yaml_obj.timestamp_format_comparison
        
        return cls(yaml_obj.string, var_type, metadata=metadata)
    
    @classmethod
    def auto_infer(cls, value: Any, description: str = "", metadata: Dict[str, Any] = None) -> 'Variable':
        """Create Variable with automatic type inference."""
        if isinstance(value, bool):
            var_type = VariableType.BOOLEAN
        elif isinstance(value, int):
            var_type = VariableType.INTEGER
        elif isinstance(value, float):
            var_type = VariableType.FLOAT
        elif isinstance(value, list):
            var_type = VariableType.LIST
        elif isinstance(value, dict):
            var_type = VariableType.DICT
        elif isinstance(value, str):
            # Smart string inference
            if value.startswith('/') or '\\' in value:
                var_type = VariableType.PATH
            elif cls._looks_like_regex(value):
                var_type = VariableType.REGEX
            elif cls._looks_like_timestamp(value):
                var_type = VariableType.TIMESTAMP
            else:
                var_type = VariableType.STRING
        else:
            var_type = VariableType.STRING
        
        return cls(value, var_type, description, metadata or {})
    
    @classmethod
    def with_metadata(cls, value: Any, var_type: VariableType, metadata: Dict[str, Any], description: str = "") -> 'Variable':
        """Create Variable with explicit type and metadata."""
        return cls(value, var_type, description, metadata)
    
    @staticmethod
    def _looks_like_regex(value: str) -> bool:
        """Heuristic to detect regex patterns."""
        regex_chars = ['.', '*', '+', '?', '[', ']', '(', ')', '{', '}', '|', '^', '$']
        return any(char in value for char in regex_chars)
    
    @staticmethod
    def _looks_like_timestamp(value: str) -> bool:
        """Heuristic to detect timestamp strings."""
        try:
            dateutil.parser.parse(value)
            return True
        except (dateutil.parser.ParserError, ValueError, TypeError):
            return False
    
    def _validate_and_coerce(self, value: Any, var_type: VariableType) -> Any:
        """Validate and coerce value to match the specified type."""
        try:
            if var_type == VariableType.STRING:
                return str(value)
            
            elif var_type == VariableType.INTEGER:
                return int(value)
            
            elif var_type == VariableType.FLOAT:
                return float(value)
            
            elif var_type == VariableType.BOOLEAN:
                if isinstance(value, bool):
                    return value
                if isinstance(value, str):
                    return value.lower() in ('true', 'yes', '1', 'on')
                return bool(value)
            
            elif var_type == VariableType.PATH:
                path_str = str(value)
                # Validate path format but don't require existence
                try:
                    Path(path_str)
                    return path_str
                except (ValueError, OSError) as e:
                    raise ValidationError(f"Invalid path format '{path_str}': {e}")
            
            elif var_type == VariableType.REGEX:
                regex_str = str(value)
                # Validate regex compiles
                try:
                    re.compile(regex_str)
                    return regex_str
                except re.error as e:
                    raise ValidationError(f"Invalid regex '{regex_str}': {e}")
            
            elif var_type == VariableType.TIMESTAMP:
                if isinstance(value, datetime.datetime):
                    return value
                timestamp_str = str(value)
                try:
                    return dateutil.parser.parse(timestamp_str)
                except (dateutil.parser.ParserError, ValueError) as e:
                    raise ValidationError(f"Invalid timestamp '{timestamp_str}': {e}")
            
            elif var_type == VariableType.LIST:
                if isinstance(value, list):
                    return value
                raise ValidationError(f"Expected list, got {type(value)}")
            
            elif var_type == VariableType.DICT:
                if isinstance(value, dict):
                    return value
                raise ValidationError(f"Expected dict, got {type(value)}")
            
            else:
                return value
                
        except (ValueError, TypeError) as e:
            raise ValidationError(f"Cannot convert '{value}' to {var_type.value}: {e}")
    
    def to_yaml_tag(self):
        """Convert Variable back to YAML custom tag for processing."""
        from adarelib.testset.yaml.customtags import (
            YamlString, YamlRegexString, YamlTimestamp, YamlPath
        )
        
        tag_mapping = {
            VariableType.STRING: YamlString,
            VariableType.REGEX: YamlRegexString,
            VariableType.TIMESTAMP: YamlTimestamp,
            VariableType.PATH: YamlPath,
        }
        
        tag_class = tag_mapping.get(self.type, YamlString)
        return tag_class(str(self.value))
    
    def get_string_value(self) -> str:
        """Get string representation for variable substitution."""
        if self.type == VariableType.TIMESTAMP and isinstance(self.value, datetime.datetime):
            return self.value.isoformat()
        elif self.type == VariableType.BOOLEAN:
            return str(self.value).lower()
        elif self.type in (VariableType.LIST, VariableType.DICT):
            # For complex types, might want JSON serialization
            import json
            return json.dumps(self.value)
        else:
            return str(self.value)
    
    def get_escaped_string_value(self, for_regex: bool = False) -> str:
        """Get escaped string value for safe substitution."""
        string_val = self.get_string_value()
        
        if for_regex and self.type != VariableType.REGEX:
            # Escape special regex chars for non-regex variables in regex context
            return re.escape(string_val)
        else:
            return string_val


class VariableRegistry:
    """Registry for managing collections of typed variables."""
    
    def __init__(self, variables: Optional[Dict[str, Variable]] = None):
        self.variables = variables or {}
    
    def add(self, name: str, variable: Variable) -> None:
        """Add a variable to the registry."""
        variable.name = name  # Set the variable name for reference in filters
        self.variables[name] = variable
    
    def get(self, name: str) -> Optional[Variable]:
        """Get a variable by name."""
        return self.variables.get(name)
    
    def resolve_in_string(self, text: str, for_regex: bool = False) -> str:
        """
        Resolve variables in string using {{variable_name}} syntax.
        
        Args:
            text: String containing variable references
            for_regex: Whether the string will be used as a regex pattern
        """
        def replace_var(match):
            var_name = match.group(1).strip()
            variable = self.get(var_name)
            
            if not variable:
                log.warning(f'Variable "{var_name}" not found in registry')
                return match.group(0)  # Return original {{var}} if not found
            
            return variable.get_escaped_string_value(for_regex=for_regex)
        
        return re.sub(r'{{([^}]+)}}', replace_var, text)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to plain dict for serialization/legacy compatibility."""
        return {name: var.get_string_value() for name, var in self.variables.items()}
    
    def to_enriched_dict(self) -> Dict[str, Any]:
        """Convert to enriched dict with type and metadata information."""
        result = {}
        for name, var in self.variables.items():
            var_dict = {
                "type": var.type.value,
                "value": var.get_string_value(),
                "metadata": var.metadata
            }
            if var.structured_metadata:
                var_dict["structured_metadata"] = var.structured_metadata.to_dict()
            result[name] = var_dict
        return result
    
    def to_execution_context(self, for_tests: bool = False) -> Dict[str, Any]:
        """Convert to execution context with smart resolution based on usage.

        Args:
            for_tests: If True, uses placeholder resolution for variables with test-specific filters
        """
        context = {}

        for name, var in self.variables.items():
            if for_tests and self._has_test_specific_filters(var):
                # For tests with test-specific filters: use placeholder resolution
                log.debug(f"Variable '{name}' has test-specific filters, using placeholder resolution")
                # The filter system will create placeholders for this variable
                # We just use the raw value here, filters handle placeholder creation
                resolved_value = var.get_string_value()
            else:
                # Check if this variable needs special placeholder treatment based on its type/metadata
                needs_placeholder = False

                # Check for regex variables
                if var.type == VariableType.REGEX:
                    needs_placeholder = True
                    placeholder_type = 'regex'

                # Check for timestamp variables with tolerance
                elif var.type == VariableType.TIMESTAMP:
                    has_tolerance = False
                    if var.structured_metadata and isinstance(var.structured_metadata, TimestampMetadata):
                        has_tolerance = (var.structured_metadata.tolerance_upper != 0 or var.structured_metadata.tolerance_lower != 0)
                    elif var.metadata and 'tolerance' in var.metadata:
                        tolerance_val = var.metadata['tolerance']
                        has_tolerance = (tolerance_val is not None and tolerance_val != 0 and tolerance_val != [0, 0])

                    if has_tolerance:
                        needs_placeholder = True
                        placeholder_type = 'timestamp'

                if needs_placeholder:
                    # Create placeholder for special variable types
                    placeholder_name = f"{name}_resolved"
                    resolved_value = f"{{{{ {placeholder_name} }}}}"

                    # Create appropriate metadata
                    if placeholder_type == 'regex':
                        self._create_regex_metadata(placeholder_name, var)
                        log.debug(f"Created regex placeholder '{placeholder_name}' for variable '{name}'")
                    elif placeholder_type == 'timestamp':
                        self._create_timestamp_tolerance_metadata(placeholder_name, var)
                        log.debug(f"Created tolerance placeholder '{placeholder_name}' for variable '{name}'")
                else:
                    # For regular variables: full resolution
                    resolved_value = self._get_variable_resolved_value(var)

            context[name] = resolved_value
            log.debug(f"Resolved variable '{name}' to '{resolved_value}' (for_tests={for_tests})")

        # Add any placeholder metadata that was created by filters
        if hasattr(self, '_placeholder_metadata') and self._placeholder_metadata:
            context['_VARIABLE_METADATA'] = self._placeholder_metadata
            log.debug(f"Added {len(self._placeholder_metadata)} filter-generated placeholders: {list(self._placeholder_metadata.keys())}")

        return context

    def _create_regex_metadata(self, placeholder_name: str, var: 'Variable'):
        """Create placeholder metadata for regex variable."""
        if not hasattr(self, '_placeholder_metadata'):
            self._placeholder_metadata = {}

        # Get regex pattern value
        regex_pattern = var.get_string_value()

        # Create metadata in same format as existing placeholder system
        self._placeholder_metadata[placeholder_name] = {
            'raw_value': regex_pattern,
            'resolved_value': regex_pattern,
            'type': 'regex'
        }

        log.debug(f"Created metadata for regex placeholder '{placeholder_name}': pattern='{regex_pattern}'")

    def _create_timestamp_tolerance_metadata(self, placeholder_name: str, var: 'Variable'):
        """Create placeholder metadata for timestamp variable with tolerance."""
        if not hasattr(self, '_placeholder_metadata'):
            self._placeholder_metadata = {}

        # Get base timestamp value
        if isinstance(var.value, datetime.datetime):
            base_value = var.value.isoformat()
        else:
            base_value = str(var.value)

        # Extract tolerance information
        tolerance = None
        if var.structured_metadata and isinstance(var.structured_metadata, TimestampMetadata):
            metadata = var.structured_metadata
            if metadata.tolerance_upper != 0 or metadata.tolerance_lower != 0:
                tolerance = [metadata.tolerance_upper, metadata.tolerance_lower]
        elif var.metadata and 'tolerance' in var.metadata:
            tolerance = var.metadata['tolerance']

        # Create metadata in same format as existing placeholder system
        self._placeholder_metadata[placeholder_name] = {
            'raw_value': base_value,
            'resolved_value': base_value,
            'type': 'timestamp',
            'tolerance': tolerance
        }

        log.debug(f"Created metadata for tolerance placeholder '{placeholder_name}': base_value='{base_value}', tolerance={tolerance}")

    def _get_variable_resolved_value(self, var: 'Variable') -> Any:
        """Get fully resolved value for variable (apply timezone, format, and template resolution)."""

        # Note: Regex variables are handled by placeholder system in to_execution_context()

        # Handle TIMESTAMP variables
        if var.type == VariableType.TIMESTAMP and isinstance(var.value, datetime.datetime):
            result = var.value

            # Note: Timestamp variables with tolerance are handled by placeholder system in to_execution_context()

            # Apply variable-level transformations (not test-specific ones)
            if var.structured_metadata and isinstance(var.structured_metadata, TimestampMetadata):
                metadata = var.structured_metadata

                # TODO: check here if its done twice both on server and client?!

                # Apply localtime conversion first (convert local time to UTC)
                # if metadata.localtime:
                #     try:
                #         import time
                #         # Get the current local timezone offset in seconds
                #         local_offset = time.timezone
                #         if time.daylight and time.localtime().tm_isdst:
                #             local_offset = time.altzone

                #         # Subtract the offset to convert local time to UTC
                #         result = result - datetime.timedelta(seconds=local_offset)
                #         log.info(f"Applied localtime conversion: adjusted timestamp by {-local_offset} seconds ({-local_offset/3600:.1f} hours) to convert to UTC")
                #     except Exception as e:
                #         log.warning(f"Failed to apply localtime conversion: {e}")


                # Apply timezone conversion
                if metadata.timezone:
                    try:
                        import pytz
                        target_tz = pytz.timezone(metadata.timezone)
                        if result.tzinfo is None:
                            result = pytz.UTC.localize(result).astimezone(target_tz)
                        else:
                            result = result.astimezone(target_tz)
                        log.debug(f"Applied timezone '{metadata.timezone}' to timestamp")
                    except Exception as e:
                        log.warning(f"Failed to apply timezone '{metadata.timezone}': {e}")

                # Apply format
                if metadata.format_str:
                    try:
                        return result.strftime(metadata.format_str)
                    except Exception as e:
                        log.warning(f"Failed to apply format '{metadata.format_str}': {e}")

            # Return as ISO string if no format specified
            return result.isoformat()
        else:
            # For non-timestamp variables, get string value and apply template resolution
            base_value = var.get_string_value()

            # Apply template resolution to resolve nested variables like {{username}}
            resolved_value = self._resolve_nested_templates(base_value)
            return resolved_value
    
    def _resolve_nested_templates(self, text: str) -> str:
        """Resolve nested template variables in a string value."""
        if not text or '{{' not in text:
            return text
            
        try:
            import jinja2
            
            result = text
            max_iterations = 10  # Prevent infinite loops
            previous_results = set()  # Track previous results to detect cycles
            
            for i in range(max_iterations):
                # If no more variables to replace, we're done
                if '{{' not in result:
                    break
                
                # Check for cycles (same result appearing again)
                if result in previous_results:
                    log.warning(f"Circular variable reference detected in nested template: {text}")
                    break
                
                previous_results.add(result)
                
                # Create a simple context with just the variable names and values (no metadata)
                simple_context = {}
                for name, var in self.variables.items():
                    if var.type == VariableType.TIMESTAMP and isinstance(var.value, datetime.datetime):
                        simple_context[name] = var.value.isoformat()
                    else:
                        # Use basic string value to avoid infinite recursion
                        simple_context[name] = var.get_string_value()
                
                # Apply template resolution
                template = jinja2.Template(result)
                new_result = template.render(simple_context)
                log.debug(f"Nested template resolution iteration {i+1}: '{result}' -> '{new_result}'")
                
                # If no change occurred, break to avoid infinite loops
                if new_result == result:
                    break
                    
                result = new_result
            
            # Warn if we hit max iterations (possible infinite loop)
            if i == max_iterations - 1 and '{{' in result:
                log.warning(f"Nested template resolution hit max iterations for: {text}")
            
            log.debug(f"Final nested template resolution: '{text}' -> '{result}'")
            return result
            
        except Exception as e:
            log.warning(f"Failed to resolve nested template '{text}': {e}")
            return text
    
    def _has_test_specific_filters(self, var: 'Variable') -> bool:
        """Check if variable has test-specific filters that require placeholder resolution."""
        log.debug(f"Checking test-specific filters for variable '{var.name}', has metadata: {var.structured_metadata is not None}")
        
        if not var.structured_metadata:
            return False
        
        # For timestamp variables, check for test-specific filters
        if var.type == VariableType.TIMESTAMP:
            if isinstance(var.structured_metadata, TimestampMetadata):
                has_tolerance = (var.structured_metadata.tolerance_upper != 0 or 
                               var.structured_metadata.tolerance_lower != 0)
                log.debug(f"Variable '{var.name}' tolerance check: upper={var.structured_metadata.tolerance_upper}, lower={var.structured_metadata.tolerance_lower}, has_tolerance={has_tolerance}")
                return has_tolerance
        
        # Add checks for other variable types as they're implemented
        return False
    
    def _has_variable_level_metadata(self, var: 'Variable') -> bool:
        """Check if variable has variable-level metadata (timezone, format)."""
        if not var.structured_metadata:
            return False
        
        # For timestamp variables, check for variable-level filters
        if var.type == VariableType.TIMESTAMP:
            if isinstance(var.structured_metadata, TimestampMetadata):
                return (var.structured_metadata.timezone or 
                       var.structured_metadata.format_str)
        
        # Add checks for other variable types as they're implemented
        return False
    
    def get_all_jinja_filters(self) -> Dict[str, Any]:
        """Collect all Jinja2 filters based on variable types (not just existing metadata)."""
        all_filters = {}
        
        # Always provide timestamp filters if we have ANY timestamp variables
        has_timestamp_vars = any(var.type == VariableType.TIMESTAMP for var in self.variables.values())
        
        if has_timestamp_vars:
            # Create a temporary TimestampMetadata to get the filters
            temp_metadata = TimestampMetadata()
            timestamp_filters = temp_metadata.get_jinja_filters(self)
            all_filters.update(timestamp_filters)
            log.debug(f"Added timestamp filters: {list(timestamp_filters.keys())}")
        
        # Also include filters from variables that already have structured metadata
        for var_name, variable in self.variables.items():
            if variable.structured_metadata and hasattr(variable.structured_metadata, 'get_jinja_filters'):
                var_filters = variable.structured_metadata.get_jinja_filters(self)
                for filter_name, filter_func in var_filters.items():
                    if filter_name in all_filters:
                        log.debug(f"Filter '{filter_name}' already exists from type-based registration")
                    all_filters[filter_name] = filter_func
        
        return all_filters
    
    @classmethod
    def from_dict(cls, var_dict: Dict[str, Any]) -> 'VariableRegistry':
        """Create registry from mixed variable definitions."""
        registry = cls()
        
        for name, value in var_dict.items():
            if isinstance(value, Variable):
                registry.add(name, value)
            elif isinstance(value, dict) and "type" in value:
                # Explicit type definition
                registry.add(name, Variable.from_dict(value))
            elif hasattr(value, 'yaml_tag'):  # YAML custom tag
                registry.add(name, Variable.from_yaml_tag(value))
            else:
                # Auto-infer type
                registry.add(name, Variable.auto_infer(value))
        
        return registry


def parse_variables(var_dict: Dict[str, Any]) -> VariableRegistry:
    """Parse mixed format variables into a VariableRegistry."""
    return VariableRegistry.from_dict(var_dict)