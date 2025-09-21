"""
Output formatting system for ADARE CLI.

Provides consistent JSON/YAML output generation with shared data preparation logic.
"""
import json
import re
import yaml
from datetime import datetime, timedelta
from enum import Enum
from typing import Any, Dict, Union
from pathlib import Path

import attrs
from rich.console import Console
from rich.table import Table
from rich.panel import Panel

# setup logging
import logging
log = logging.getLogger(__name__)


class OutputFormat(Enum):
    """Supported output formats."""
    RICH = "rich"
    JSON = "json"
    YAML = "yaml"


class StructuredOutputFormatter:
    """
    Handles data preparation and serialization for structured formats (JSON/YAML).

    This class provides shared functionality for converting Rich objects and
    complex data structures into serializable dictionaries.
    """

    def prepare_data(self, data: Any) -> Any:
        """
        Convert Rich objects and complex data structures to serializable format.

        :param data: Input data that may contain Rich objects, dataclasses, etc.
        :return: Cleaned data suitable for JSON/YAML serialization
        """
        if data is None:
            return None
        elif isinstance(data, (str, int, float, bool)):
            # Clean Rich markup from strings
            if isinstance(data, str):
                return self._strip_rich_markup(data)
            return data
        elif isinstance(data, datetime):
            return data.isoformat()
        elif isinstance(data, timedelta):
            return data.total_seconds()
        elif isinstance(data, Path):
            return str(data)
        elif hasattr(data, '__attrs_attrs__'):
            # Handle attrs/dataclass objects
            return self._attrs_to_dict(data)
        elif hasattr(data, '__dataclass_fields__'):
            # Handle dataclass objects
            return self._dataclass_to_dict(data)
        elif hasattr(data, 'to_dict'):
            # Handle objects with explicit to_dict method
            return self.prepare_data(data.to_dict())
        elif isinstance(data, dict):
            return {key: self.prepare_data(value) for key, value in data.items()}
        elif isinstance(data, (list, tuple)):
            return [self.prepare_data(item) for item in data]
        elif isinstance(data, (Table, Panel)):
            # Convert Rich objects to basic representations
            return self._rich_object_to_dict(data)
        else:
            # Fallback: convert to string and clean markup
            return self._strip_rich_markup(str(data))

    def _strip_rich_markup(self, text: str) -> str:
        """Remove Rich markup from text."""
        # Remove Rich style tags like [bold], [red], etc.
        clean_text = re.sub(r'\[[^\]]*\]', '', text)
        # Remove Rich emoji codes like :white_check_mark:
        clean_text = re.sub(r':[a-zA-Z_]+:', '', clean_text)
        return clean_text.strip()

    def _attrs_to_dict(self, obj) -> Dict[str, Any]:
        """Convert attrs object to dictionary."""
        result = {}
        for field in attrs.fields(obj.__class__):
            value = getattr(obj, field.name)
            result[field.name] = self.prepare_data(value)
        return result

    def _dataclass_to_dict(self, obj) -> Dict[str, Any]:
        """Convert dataclass object to dictionary."""
        result = {}
        for field_name in obj.__dataclass_fields__:
            value = getattr(obj, field_name)
            result[field_name] = self.prepare_data(value)
        return result

    def _rich_object_to_dict(self, obj) -> Dict[str, Any]:
        """Convert Rich objects to basic dictionary representation."""
        if isinstance(obj, Table):
            return self._table_to_dict(obj)
        elif isinstance(obj, Panel):
            return self._panel_to_dict(obj)
        else:
            return {"type": obj.__class__.__name__, "content": str(obj)}

    def _table_to_dict(self, table: Table) -> Dict[str, Any]:
        """Convert Rich Table to dictionary."""
        # Note: This is a simplified conversion
        # Full table structure extraction would require more complex logic
        return {
            "type": "table",
            "title": getattr(table, 'title', None),
            "columns": [col.header for col in table.columns] if table.columns else [],
            "note": "Rich table content - use rich format for full display"
        }

    def _panel_to_dict(self, panel: Panel) -> Dict[str, Any]:
        """Convert Rich Panel to dictionary."""
        return {
            "type": "panel",
            "title": getattr(panel, 'title', None),
            "content": self._strip_rich_markup(str(panel.renderable)) if panel.renderable else None
        }

    def serialize_json(self, data: Any, indent: int = 2) -> str:
        """
        Serialize data to JSON format.

        :param data: Prepared data to serialize
        :param indent: JSON indentation level
        :return: JSON string
        """
        try:
            return json.dumps(data, indent=indent, ensure_ascii=False)
        except TypeError as e:
            log.error(f"JSON serialization error: {e}")
            # Fallback: convert problematic objects to strings
            safe_data = self._make_json_safe(data)
            return json.dumps(safe_data, indent=indent, ensure_ascii=False)

    def serialize_yaml(self, data: Any) -> str:
        """
        Serialize data to YAML format.

        :param data: Prepared data to serialize
        :return: YAML string
        """
        try:
            return yaml.dump(
                data,
                default_flow_style=False,
                allow_unicode=True,
                sort_keys=False,
                indent=2
            )
        except yaml.YAMLError as e:
            log.error(f"YAML serialization error: {e}")
            # Fallback: convert problematic objects to strings
            safe_data = self._make_json_safe(data)
            return yaml.dump(safe_data, default_flow_style=False, allow_unicode=True)

    def _make_json_safe(self, data: Any) -> Any:
        """Convert any remaining non-serializable objects to strings."""
        if isinstance(data, dict):
            return {key: self._make_json_safe(value) for key, value in data.items()}
        elif isinstance(data, (list, tuple)):
            return [self._make_json_safe(item) for item in data]
        elif isinstance(data, (str, int, float, bool, type(None))):
            return data
        else:
            return str(data)


class OutputFormatter:
    """
    Main output formatter that delegates to appropriate format handlers.
    """

    def __init__(self, format_type: OutputFormat = OutputFormat.RICH):
        self.format_type = format_type
        self.structured_formatter = StructuredOutputFormatter()

    def format(self, data: Any) -> str:
        """
        Format data according to the specified output format.

        :param data: Data to format
        :return: Formatted string
        """
        if self.format_type == OutputFormat.RICH:
            return self._format_rich(data)
        else:
            # Prepare data for structured formats
            clean_data = self.structured_formatter.prepare_data(data)

            if self.format_type == OutputFormat.JSON:
                return self.structured_formatter.serialize_json(clean_data)
            elif self.format_type == OutputFormat.YAML:
                return self.structured_formatter.serialize_yaml(clean_data)
            else:
                raise ValueError(f"Unsupported output format: {self.format_type}")

    def _format_rich(self, data: Any) -> str:
        """
        Format data using Rich console (existing behavior).

        :param data: Data to format with Rich
        :return: Rich-formatted string
        """
        # For Rich format, we return the data as-is and let the calling code
        # handle Rich console printing. This maintains backward compatibility.
        return data

    def print_or_save(self, data: Any, output_file: str = None, dual_output: bool = False):
        """
        Print formatted data to console or save to file.

        :param data: Data to format and output
        :param output_file: Optional file path to save output
        :param dual_output: If True, show Rich on console AND save structured to file
        """
        if dual_output and output_file:
            # Dual output mode: Rich to console + structured to file
            # Only show Rich output on console if we have Rich-renderable data
            if hasattr(data, '__rich__'):
                console = Console()
                console.print(data)
            # If data is just a dict/plain data, don't print anything to console
            # (the Rich output has already been shown during the command execution)

            # Save structured data to file (use format specified or default to JSON)
            if self.format_type == OutputFormat.RICH:
                # When Rich is specified but we need structured output, default to JSON
                json_formatter = StructuredOutputFormatter()
                clean_data = json_formatter.prepare_data(data)
                file_output = json_formatter.serialize_json(clean_data)
            else:
                # Use the specified structured format
                file_output = self.format(data)

            with open(output_file, 'w', encoding='utf-8') as f:
                f.write(file_output)
            log.info(f"Structured data saved to {output_file}")

        elif self.format_type == OutputFormat.RICH:
            # Rich format only
            console = Console()
            if hasattr(data, '__rich__'):
                console.print(data)
            else:
                console.print(str(data))
        else:
            # Structured format (JSON/YAML)
            formatted_output = self.format(data)

            if output_file:
                # Save to file
                with open(output_file, 'w', encoding='utf-8') as f:
                    f.write(formatted_output)
                log.info(f"Output saved to {output_file}")
            else:
                # Print to console
                print(formatted_output)


def get_formatter(format_type: Union[OutputFormat, str] = OutputFormat.RICH) -> OutputFormatter:
    """
    Factory function to create an OutputFormatter.

    :param format_type: Output format (enum or string)
    :return: Configured OutputFormatter instance
    """
    if isinstance(format_type, str):
        try:
            format_type = OutputFormat(format_type.lower())
        except ValueError:
            log.warning(f"Unknown output format '{format_type}', using Rich")
            format_type = OutputFormat.RICH

    return OutputFormatter(format_type)