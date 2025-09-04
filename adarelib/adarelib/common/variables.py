from __future__ import annotations
from enum import Enum
from typing import Any, Dict, Union, Optional, Type
from abc import ABC, abstractmethod
import attrs
import re
import datetime
import dateutil.parser
from pathlib import Path

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
class Variable:
    """
    Typed variable with validation and conversion capabilities.
    
    Supports both explicit type definition and YAML tag inference.
    """
    value: Any
    type: VariableType
    description: str = ""
    
    def __post_init__(self):
        """Validate and coerce value on creation."""
        self.value = self._validate_and_coerce(self.value, self.type)
    
    @classmethod
    def from_dict(cls, data: dict) -> 'Variable':
        """Create Variable from explicit dict definition."""
        return cls(
            value=data["value"],
            type=VariableType(data["type"]), 
            description=data.get("description", "")
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
        
        return cls(yaml_obj.string, var_type)
    
    @classmethod
    def auto_infer(cls, value: Any, description: str = "") -> 'Variable':
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
        
        return cls(value, var_type, description)
    
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
    
    def to_execution_context(self) -> Dict[str, Any]:
        """Convert to execution context with special handling for timestamps."""
        context = {}
        for name, var in self.variables.items():
            if var.type == VariableType.TIMESTAMP and isinstance(var.value, datetime.datetime):
                # Keep datetime objects for template engine
                context[name] = var.value
            else:
                context[name] = var.value
        return context
    
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