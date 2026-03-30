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
                source_var.metadata['tolerance'] = [lower, upper]
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
    
    def __attrs_post_init__(self):
        """Validate and coerce value on creation."""
        log.info(f"CLAUDE: Variable.__attrs_post_init__ called - value='{self.value}', type={self.type}, metadata={self.metadata}")
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
        log.info(f"CLAUDE: Variable.from_dict called with data: {data}")

        # Collect metadata from both explicit metadata dict and top-level properties
        metadata = data.get("metadata", {}).copy()

        # For timestamp variables, collect timezone, format, and other properties into metadata
        if data.get("type") == "timestamp":
            for key in ["timezone", "format", "tolerance", "localtime"]:
                if key in data:
                    metadata[key] = data[key]
                    log.info(f"CLAUDE: Collected {key}='{data[key]}' into metadata")

        log.info(f"CLAUDE: Final metadata for Variable.from_dict: {metadata}")

        return cls(
            value=data["value"],
            type=VariableType(data["type"]),
            description=data.get("description", ""),
            metadata=metadata,
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
        log.info(f"CLAUDE: Variable.auto_infer called with value='{value}', metadata={metadata}")

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

        log.info(f"CLAUDE: auto_infer determined type: {var_type}")
        return cls(value, var_type, description, metadata or {})
    
    @classmethod
    def with_metadata(cls, value: Any, var_type: VariableType, metadata: Dict[str, Any], description: str = "") -> 'Variable':
        """Create Variable with explicit type and metadata."""
        return cls(value, var_type, description, metadata)
    
    @staticmethod
    def _looks_like_regex(value: str) -> bool:
        """Heuristic to detect regex patterns."""
        regex_chars = ['*', '+', '?', '[', ']', '(', '{', '}', '|', '^', '$']
        return any(char in value for char in regex_chars)
    
    @staticmethod
    def _looks_like_timestamp(value: str) -> bool:
        """Heuristic to detect timestamp strings."""
        # Avoid matching version numbers (e.g. 4.13.0) as timestamps
        # If it contains only digits and dots, and has more than one dot, it's likely a version
        if all(c.isdigit() or c == '.' for c in value) and value.count('.') > 1:
            return False
            
        try:
            dateutil.parser.parse(value)
            return True
        except (dateutil.parser.ParserError, ValueError, TypeError):
            return False

    @staticmethod
    def _is_raw_string_literal(text: Any) -> bool:
        """Check if text is a Python-style raw string literal (e.g. r"..." or r'...')."""
        if not isinstance(text, str):
            return False
        
        # Check for r"..." prefix/suffix
        if text.startswith('r"') and text.endswith('"') and len(text) >= 3:
            return True
            
        # Check for r'...' prefix/suffix
        if text.startswith("r'") and text.endswith("'") and len(text) >= 3:
            return True
            
        return False
        
    @staticmethod
    def _strip_raw_string_literal(text: str) -> str:
        """Strip raw string literal wrapper."""
        if text.startswith('r"') or text.startswith("r'"):
            return text[2:-1]
        return text
    
    def _validate_and_coerce(self, value: Any, var_type: VariableType) -> Any:
        """Validate and coerce value to match the specified type."""
        log.info(f"CLAUDE: _validate_and_coerce called with value='{value}', type={var_type}")
        try:
            # Handle raw string literals for string-like types
            if var_type in (VariableType.STRING, VariableType.PATH, VariableType.REGEX):
                if Variable._is_raw_string_literal(value):
                    original_value = value
                    value = Variable._strip_raw_string_literal(value)
                    log.debug(f"Stripped raw string literal: '{original_value}' -> '{value}'")

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
                    # Already a datetime - convert to Unix timestamp if has timezone info
                    if value.tzinfo is not None:
                        return value.timestamp()
                    return value
                timestamp_str = str(value)
                try:
                    parsed_dt = dateutil.parser.parse(timestamp_str)

                    # Apply timezone metadata if available and datetime is naive
                    log.info(f"CLAUDE: Timezone conversion check - parsed_dt.tzinfo: {parsed_dt.tzinfo}, hasattr(self, 'metadata'): {hasattr(self, 'metadata')}")
                    if hasattr(self, 'metadata'):
                        log.info(f"CLAUDE: self.metadata: {self.metadata}")

                    if parsed_dt.tzinfo is None and hasattr(self, 'metadata') and self.metadata:
                        timezone_str = self.metadata.get('timezone')
                        log.info(f"CLAUDE: Found timezone in metadata: '{timezone_str}'")
                        if timezone_str:
                            try:
                                # Parse timezone offset (e.g., "+04:00", "-05:00")
                                if timezone_str.startswith(('+', '-')):
                                    # Create timezone from offset string
                                    tz = dateutil.tz.gettz(timezone_str)
                                    if tz:
                                        parsed_dt = parsed_dt.replace(tzinfo=tz)
                                        log.info(f"CLAUDE: Applied offset timezone '{timezone_str}' to timestamp: {parsed_dt}")
                                else:
                                    # Named timezone (e.g., "UTC", "US/Eastern")
                                    tz = dateutil.tz.gettz(timezone_str)
                                    if tz:
                                        parsed_dt = parsed_dt.replace(tzinfo=tz)
                                        log.info(f"CLAUDE: Applied named timezone '{timezone_str}' to timestamp: {parsed_dt}")
                            except Exception as e:
                                log.warning(f"Failed to apply timezone '{timezone_str}': {e}", exc_info=True)

                    # Convert timezone-aware datetime to UTC Unix timestamp for consistent storage
                    if parsed_dt.tzinfo is not None:
                        unix_timestamp = parsed_dt.timestamp()
                        log.info(f"CLAUDE: Converted timezone-aware timestamp to Unix timestamp: {unix_timestamp}")
                        return unix_timestamp
                    else:
                        # Keep naive datetime as-is for backward compatibility
                        log.info(f"CLAUDE: Keeping naive datetime (no timezone): {parsed_dt}")
                        return parsed_dt

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
        if self.type == VariableType.TIMESTAMP:
            if isinstance(self.value, datetime.datetime):
                return self.value.isoformat()
            elif isinstance(self.value, (int, float)):
                # Unix timestamp - return as string
                return str(self.value)
        elif self.type == VariableType.BOOLEAN:
            return str(self.value).lower()
        elif self.type in (VariableType.LIST, VariableType.DICT):
            # For complex types, might want JSON serialization
            import json
            return json.dumps(self.value)
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
                    
                    # IMPORTANT: Add the RESOLVED value of the placeholder to the context as well
                    # This enables recursive resolution: {{ var }} -> {{ var_resolved }} -> value
                    # which is required for CommandAction and others that need a fully resolved string
                    placeholder_value = self._get_variable_resolved_value(var)
                    context[placeholder_name] = placeholder_value
                    log.debug(f"Added resolved value for placeholder '{placeholder_name}': '{placeholder_value}'")

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

    def to_execution_context_lazy(self, referenced_variables: set = None, for_tests: bool = False) -> Dict[str, Any]:
        """Convert to execution context with lazy resolution - only process referenced variables.

        Args:
            referenced_variables: Set of variable names that are actually referenced in the test
            for_tests: If True, uses placeholder resolution for variables with test-specific filters
        """
        context = {}

        # If no referenced variables specified, process all (fallback to old behavior)
        if referenced_variables is None:
            return self.to_execution_context(for_tests)

        # Track metadata created during this specific call
        current_call_metadata = {}

        # Build minimal resolution context for nested template resolution
        # Include variables without nested templates (typically automatic variables)
        resolution_context = {}
        for name in referenced_variables:
            if name in self.variables:
                var = self.variables[name]
                var_str = var.get_string_value()
                # For automatic variables (no nested templates), add them to context
                if '{{' not in var_str:
                    resolution_context[name] = var_str
        log.debug(f"Built resolution context with {len(resolution_context)} variables: {list(resolution_context.keys())}")

        # Only process variables that are actually referenced
        for name in referenced_variables:
            if name not in self.variables:
                log.warning(f"Referenced variable '{name}' not found in registry")
                continue

            var = self.variables[name]

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

                    # Create appropriate metadata and track it locally
                    if placeholder_type == 'regex':
                        metadata = self._create_regex_metadata(placeholder_name, var, local_only=True)
                        current_call_metadata[placeholder_name] = metadata
                        log.debug(f"Created regex placeholder '{placeholder_name}' for variable '{name}'")
                    elif placeholder_type == 'timestamp':
                        metadata = self._create_timestamp_tolerance_metadata(placeholder_name, var, local_only=True)
                        current_call_metadata[placeholder_name] = metadata
                        log.debug(f"Created tolerance placeholder '{placeholder_name}' for variable '{name}'")
                    
                    # IMPORTANT: Add the RESOLVED value of the placeholder to the context as well
                    placeholder_value = self._get_variable_resolved_value(var, resolution_context)
                    context[placeholder_name] = placeholder_value
                    log.debug(f"Added resolved value for placeholder '{placeholder_name}': '{placeholder_value}'")
                else:
                    # For regular variables: full resolution with resolution context
                    resolved_value = self._get_variable_resolved_value(var, resolution_context)

            context[name] = resolved_value
            log.debug(f"Lazy resolved variable '{name}' to '{resolved_value}' (for_tests={for_tests})")

        # Only add metadata that was created during this specific call
        if current_call_metadata:
            context['_VARIABLE_METADATA'] = current_call_metadata
            log.debug(f"Added {len(current_call_metadata)} lazy-generated placeholders for this test: {list(current_call_metadata.keys())}")

        return context

    def extract_referenced_variables(self, data: Any) -> set:
        """Extract all variable names that are referenced in the data structure.

        This scans through the data structure looking for Jinja2 template references
        like {{variable_name}} to determine which variables are actually used.
        Also recursively resolves dependencies when variable values contain other variables.

        Args:
            data: The data structure to scan for variable references

        Returns:
            Set of variable names including all nested dependencies
        """
        referenced_vars = set()

        def _scan_for_variables(obj):
            if isinstance(obj, str):
                # Look for {{variable_name}} patterns
                import re
                variable_pattern = r'\{\{\s*(\w+)(?:\s*\|[^}]*)?\s*\}\}'
                matches = re.findall(variable_pattern, obj)
                for match in matches:
                    referenced_vars.add(match)
            elif isinstance(obj, dict):
                for value in obj.values():
                    _scan_for_variables(value)
            elif isinstance(obj, list):
                for item in obj:
                    _scan_for_variables(item)

        _scan_for_variables(data)

        # Recursively resolve variable dependencies
        all_vars = set(referenced_vars)
        to_process = list(referenced_vars)
        visited = set()
        max_depth = 20  # Safety limit for circular references
        depth = 0

        while to_process and depth < max_depth:
            var_name = to_process.pop(0)
            if var_name in visited:
                continue
            visited.add(var_name)
            depth += 1

            # Get variable from registry
            var = self.variables.get(var_name)
            if not var:
                continue

            # Extract nested template references from variable value
            var_value_str = var.get_string_value()
            if '{{' in var_value_str:
                nested_vars = self._extract_template_variables(var_value_str)
                for nested_var in nested_vars:
                    if nested_var not in all_vars:
                        all_vars.add(nested_var)
                        to_process.append(nested_var)

        if depth >= max_depth:
            log.warning(f"Variable dependency resolution hit max depth ({max_depth}), possible circular reference")

        log.debug(f"Extracted {len(all_vars)} variables including dependencies: {all_vars}")
        return all_vars

    def _extract_template_variables(self, template_str: str) -> set:
        """Extract variable names from a template string.

        Args:
            template_str: String that may contain {{variable}} references

        Returns:
            Set of variable names found in the template
        """
        import re
        variable_pattern = r'\{\{\s*(\w+)(?:\s*\|[^}]*)?\s*\}\}'
        matches = re.findall(variable_pattern, template_str)
        return set(matches)

    def _create_regex_metadata(self, placeholder_name: str, var: 'Variable', local_only: bool = False):
        """Create placeholder metadata for regex variable."""
        # Get regex pattern value
        regex_pattern = var.get_string_value()

        # Create metadata in same format as existing placeholder system
        metadata = {
            'raw_value': regex_pattern,
            'resolved_value': regex_pattern,
            'type': 'regex'
        }

        if not local_only:
            # Store globally (original behavior)
            if not hasattr(self, '_placeholder_metadata'):
                self._placeholder_metadata = {}
            self._placeholder_metadata[placeholder_name] = metadata
            log.debug(f"Created global metadata for regex placeholder '{placeholder_name}': pattern='{regex_pattern}'")
        else:
            log.debug(f"Created local metadata for regex placeholder '{placeholder_name}': pattern='{regex_pattern}'")

        return metadata

    def _create_timestamp_tolerance_metadata(self, placeholder_name: str, var: 'Variable', local_only: bool = False):
        """Create placeholder metadata for timestamp variable with tolerance."""
        # Get base timestamp value
        if isinstance(var.value, datetime.datetime):
            base_value = var.value.isoformat()
        elif isinstance(var.value, (int, float)):
            # Unix timestamp - keep as numeric string for VM processing
            base_value = str(var.value)
        else:
            base_value = str(var.value)

        # Extract tolerance information
        tolerance = None
        if var.structured_metadata and isinstance(var.structured_metadata, TimestampMetadata):
            metadata_obj = var.structured_metadata
            if metadata_obj.tolerance_upper != 0 or metadata_obj.tolerance_lower != 0:
                tolerance = [metadata_obj.tolerance_upper, metadata_obj.tolerance_lower]
        elif var.metadata and 'tolerance' in var.metadata:
            tolerance = var.metadata['tolerance']

        # Create metadata in same format as existing placeholder system
        metadata = {
            'raw_value': base_value,
            'resolved_value': base_value,
            'type': 'timestamp',
            'tolerance': tolerance
        }

        # Use timezone from Variable metadata if available, otherwise default to 'utc'
        if isinstance(var.value, (int, float)):
            # Check if Variable already has timezone metadata
            var_timezone = var.metadata.get('timezone', 'utc')
            metadata['timezone'] = var_timezone
            log.debug(f"Added timezone '{var_timezone}' metadata for Unix timestamp variable '{var.name}'")

        if not local_only:
            # Store globally (original behavior)
            if not hasattr(self, '_placeholder_metadata'):
                self._placeholder_metadata = {}
            self._placeholder_metadata[placeholder_name] = metadata
            log.debug(f"Created global metadata for tolerance placeholder '{placeholder_name}': base_value='{base_value}', tolerance={tolerance}")
        else:
            log.debug(f"Created local metadata for tolerance placeholder '{placeholder_name}': base_value='{base_value}', tolerance={tolerance}")

        return metadata

    def _get_variable_resolved_value(self, var: 'Variable', resolution_context: Dict[str, str] = None) -> Any:
        """Get fully resolved value for variable (apply timezone, format, and template resolution).

        Args:
            var: The variable to resolve
            resolution_context: Optional context dict for resolving nested templates
        """

        # Note: Regex variables are handled by placeholder system in to_execution_context()

        # Handle TIMESTAMP variables
        if var.type == VariableType.TIMESTAMP:
            log.info(f"CLAUDE: Processing timestamp variable '{var.name}' - value='{var.value}', metadata={var.metadata}")

            # Handle both Unix timestamps (float) and datetime objects
            if isinstance(var.value, (int, float)):
                # Unix timestamp - convert to UTC datetime for processing
                result = datetime.datetime.fromtimestamp(var.value, datetime.timezone.utc)
                log.debug(f"Converted Unix timestamp {var.value} to UTC datetime: {result}")
            elif isinstance(var.value, datetime.datetime):
                result = var.value
                log.debug(f"Using datetime object: {result}")
            else:
                # String timestamp - parse and apply timezone if available
                try:
                    result = dateutil.parser.parse(str(var.value))
                    log.debug(f"Parsed timestamp string: {result}")

                    # Apply timezone conversion if timezone metadata is available
                    timezone_str = None
                    if var.structured_metadata and isinstance(var.structured_metadata, TimestampMetadata):
                        timezone_str = var.structured_metadata.timezone
                    elif var.metadata and 'timezone' in var.metadata:
                        timezone_str = var.metadata['timezone']

                    if timezone_str and result.tzinfo is None:
                        log.info(f"CLAUDE: Applying timezone '{timezone_str}' to naive timestamp")
                        try:
                            # Apply timezone to naive datetime
                            if timezone_str.startswith(('+', '-')):
                                # Parse timezone offset (e.g., "+04:00", "-05:00")
                                import re
                                log.info(f"CLAUDE: Parsing timezone offset '{timezone_str}'")
                                offset_match = re.match(r'([+-])(\d{2}):?(\d{2})', timezone_str)
                                if offset_match:
                                    sign, hours, minutes = offset_match.groups()
                                    log.info(f"CLAUDE: Regex matched - sign={sign}, hours={hours}, minutes={minutes}")
                                    offset_hours = int(hours) + int(minutes) / 60
                                    if sign == '-':
                                        offset_hours = -offset_hours
                                    log.info(f"CLAUDE: Calculated offset_hours: {offset_hours}")

                                    # Create timezone object from offset
                                    tz = datetime.timezone(datetime.timedelta(hours=offset_hours))
                                    result = result.replace(tzinfo=tz)
                                    log.info(f"CLAUDE: Applied timezone offset '{timezone_str}': {result}")
                                    log.info(f"CLAUDE: result.tzinfo after applying timezone: {result.tzinfo}")
                                else:
                                    log.warning(f"CLAUDE: Failed to parse timezone offset '{timezone_str}' - regex didn't match")
                            else:
                                # Named timezone (e.g., "UTC", "US/Eastern")
                                tz = dateutil.tz.gettz(timezone_str)
                                if tz:
                                    result = result.replace(tzinfo=tz)
                                    log.info(f"CLAUDE: Applied named timezone '{timezone_str}': {result}")

                            # Convert to UTC Unix timestamp for consistent storage
                            log.info(f"CLAUDE: Checking if result has timezone: {result.tzinfo is not None}")
                            if result.tzinfo is not None:
                                unix_timestamp = result.timestamp()
                                log.info(f"CLAUDE: SUCCESS! Converted timezone-aware timestamp to UTC Unix timestamp: {unix_timestamp}")
                                return unix_timestamp
                            else:
                                log.warning(f"CLAUDE: No timezone info available after conversion attempt")

                        except Exception as e:
                            log.warning(f"CLAUDE: Exception during timezone conversion: {e}")
                            import traceback
                            log.warning(f"CLAUDE: Traceback: {traceback.format_exc()}")

                except Exception as e:
                    log.warning(f"Failed to parse timestamp value '{var.value}': {e}")
                    return str(var.value)

            # Note: Timestamp variables with tolerance are handled by placeholder system in to_execution_context()

            # Apply variable-level transformations (not test-specific ones)
            if var.structured_metadata and isinstance(var.structured_metadata, TimestampMetadata):
                metadata = var.structured_metadata

                # Skip timezone conversion for Unix timestamps since they're already UTC
                # Only apply format if specified
                if metadata.format_str:
                    try:
                        return result.strftime(metadata.format_str)
                    except Exception as e:
                        log.warning(f"Failed to apply format '{metadata.format_str}': {e}")

            # For Unix timestamp variables (already UTC), return the timestamp directly
            # This matches the save_timestamp behavior
            if isinstance(var.value, (int, float)):
                return var.value

            # For datetime objects, return as ISO string if no format specified
            return result.isoformat()
        else:
            # For non-timestamp variables, get string value and apply template resolution
            base_value = var.get_string_value()

            # Apply template resolution to resolve nested variables like {{username}}
            resolved_value = self._resolve_nested_templates(base_value, resolution_context)
            return resolved_value
    
    def _resolve_nested_templates(self, text: str, context: Dict[str, Any] = None) -> str:
        """Resolve nested template variables in a string value.

        Args:
            text: The template string to resolve
            context: Optional pre-built context dict. If None, builds from self.variables
        """
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

                # Use provided context or build from registry
                if context is not None:
                    # Use provided context (already resolved)
                    simple_context = context
                    log.debug(f"Using provided context with {len(context)} variables: {list(context.keys())}")
                else:
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
        for variable in self.variables.values():
            if variable.structured_metadata and hasattr(variable.structured_metadata, 'get_jinja_filters'):
                var_filters = variable.structured_metadata.get_jinja_filters(self)
                for filter_name, filter_func in var_filters.items():
                    if filter_name in all_filters:
                        log.debug(f"Filter '{filter_name}' already exists from type-based registration")
                    all_filters[filter_name] = filter_func
        

        # Add general path utility filters
        all_filters.update({
            'win_path': lambda x: str(x).replace('/', '\\'),
            'posix_path': lambda x: str(x).replace('\\', '/'),
            'double_backslash': lambda x: str(x).replace('\\', '\\\\'),
        })

        return all_filters
    
    @classmethod
    def from_dict(cls, var_dict: Dict[str, Any]) -> 'VariableRegistry':
        """Create registry from mixed variable definitions."""
        log.info(f"CLAUDE: VariableRegistry.from_dict called with: {var_dict}")
        registry = cls()

        for name, value in var_dict.items():
            log.info(f"CLAUDE: Processing variable '{name}' with value: {value} (type: {type(value)})")
            if isinstance(value, Variable):
                log.info(f"CLAUDE: '{name}' is already a Variable object")
                registry.add(name, value)
            elif isinstance(value, dict) and "type" in value:
                # Explicit type definition
                log.info(f"CLAUDE: '{name}' is dict with type, calling Variable.from_dict")
                registry.add(name, Variable.from_dict(value))
            elif hasattr(value, 'yaml_tag'):  # YAML custom tag
                log.info(f"CLAUDE: '{name}' has yaml_tag, calling Variable.from_yaml_tag")
                registry.add(name, Variable.from_yaml_tag(value))
            else:
                # Auto-infer type
                log.info(f"CLAUDE: '{name}' auto-inferring type")
                registry.add(name, Variable.auto_infer(value))

        log.info(f"CLAUDE: VariableRegistry.from_dict created registry with {len(registry.variables)} variables")
        return registry


def parse_variables(var_dict: Dict[str, Any]) -> VariableRegistry:
    """Parse mixed format variables into a VariableRegistry."""
    return VariableRegistry.from_dict(var_dict)