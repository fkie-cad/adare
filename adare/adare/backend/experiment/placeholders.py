"""Placeholder metadata for test values that stay symbolic until the test compares them.

A ``!re`` or ``!timestamp`` tag, or a ``| tolerance(...)`` filter, cannot be turned
into a plain value on the host: the test needs to know *how* to compare. Such values
become a ``{{ name_resolved }}`` placeholder plus a metadata entry (type, raw value,
tolerance, interval, format, ...) that travels with the test as ``_VARIABLE_METADATA``.
"""

import logging
import re
from dataclasses import dataclass
from typing import Any

from adare.backend.experiment.timestamp_interval import has_tolerance_or_interval

log = logging.getLogger(__name__)


@dataclass
class FilterAnalysis:
    """Analysis of filters applied to a Jinja2 template"""

    has_tolerance: bool = False
    has_format: bool = False
    has_localtime: bool = False
    tolerance_values: tuple[int, int] | None = None
    format_string: str | None = None
    original_template: str = ""
    variable_name: str | None = None


class ToleranceDetector:
    """Detects tolerance usage in templates and YAML."""

    TOLERANCE_PATTERN = re.compile(r'\|\s*tolerance\s*\(\s*([^,\)]+)(?:\s*,\s*([^,\)]+))?\s*\)')
    FORMAT_PATTERN = re.compile(r'\|\s*format\s*\(\s*["\']([^"\']+)["\']')
    LOCALTIME_PATTERN = re.compile(r'\|\s*localtime\s*')
    VARIABLE_PATTERN = re.compile(r'{{\s*(\w+)')

    def analyze_jinja_template(self, template_str: str) -> FilterAnalysis:
        """Analyze a Jinja2 template for filters."""
        analysis = FilterAnalysis(original_template=template_str)

        # Extract variable name
        var_match = self.VARIABLE_PATTERN.search(template_str)
        if var_match:
            analysis.variable_name = var_match.group(1)

        # Check for tolerance filter
        tolerance_match = self.TOLERANCE_PATTERN.search(template_str)
        if tolerance_match:
            analysis.has_tolerance = True
            try:
                upper = int(tolerance_match.group(1))
                lower = int(tolerance_match.group(2)) if tolerance_match.group(2) else -upper
                analysis.tolerance_values = (upper, lower)
                log.debug(f"Found tolerance filter: upper={upper}, lower={lower}")
            except ValueError:
                log.warning(f"Could not parse tolerance values in: {template_str}")

        # Check for format filter
        format_match = self.FORMAT_PATTERN.search(template_str)
        if format_match:
            analysis.has_format = True
            analysis.format_string = format_match.group(1)
            log.debug(f"Found format filter: {analysis.format_string}")

        # Check for localtime filter
        localtime_match = self.LOCALTIME_PATTERN.search(template_str)
        if localtime_match:
            analysis.has_localtime = True
            log.debug("Found localtime filter")

        return analysis

    def has_yaml_tolerance(self, yaml_obj) -> bool:
        """Check if YAML object has explicitly defined tolerance (an interval counts as one)"""
        return has_tolerance_or_interval(yaml_obj)


class MetadataManager:
    """Handles placeholder metadata creation and management."""

    def __init__(self, variable_registry=None):
        """
        Initialize metadata manager.

        Args:
            variable_registry: Variable registry to store metadata in
        """
        self.variable_registry = variable_registry

    def add_regex_metadata(
        self, placeholder_name: str, regex_pattern: str, template_context: dict[str, Any] | None = None
    ):
        """
        Add regex metadata following the same structure as timestamp tolerance.

        Args:
            placeholder_name: Name of the placeholder
            regex_pattern: The regex pattern to store
            template_context: Current template context to update (optional)
        """
        if not self.variable_registry:
            log.warning(f"No variable registry available to store metadata for '{placeholder_name}'")
            return

        if not hasattr(self.variable_registry, '_placeholder_metadata'):
            self.variable_registry._placeholder_metadata = {}

        # Same structure as timestamp metadata
        self.variable_registry._placeholder_metadata[placeholder_name] = {
            'raw_value': regex_pattern,
            'resolved_value': regex_pattern,
            'type': 'regex',
        }
        log.debug(f"Added regex metadata for '{placeholder_name}': pattern='{regex_pattern}'")

        # Add placeholder to current template context for subsequent Jinja resolution
        if template_context is not None:
            template_context[placeholder_name] = regex_pattern
            log.debug(f"Added regex placeholder '{placeholder_name}' to template context with value '{regex_pattern}'")

    def add_timestamp_metadata(
        self,
        placeholder_name: str,
        timestamp_value: str,
        tolerance: Any | None = None,
        template_context: dict[str, Any] | None = None,
        yaml_metadata: dict[str, Any] | None = None,
    ):
        """
        Add timestamp metadata following the existing structure.

        Args:
            placeholder_name: Name of the placeholder
            timestamp_value: The timestamp value
            tolerance: Optional tolerance information
            template_context: Current template context to update (optional)
        """
        if not self.variable_registry:
            log.warning(f"No variable registry available to store metadata for '{placeholder_name}'")
            return

        if not hasattr(self.variable_registry, '_placeholder_metadata'):
            self.variable_registry._placeholder_metadata = {}

        metadata = {'raw_value': timestamp_value, 'resolved_value': timestamp_value, 'type': 'timestamp'}

        # If the timestamp value contains template syntax, mark it for runtime resolution
        if '{{' in str(timestamp_value) and '}}' in str(timestamp_value):
            metadata['needs_runtime_resolution'] = True
            log.debug(f"Marked timestamp '{timestamp_value}' for runtime resolution")

        # Include any YAML metadata (timezone, format, etc.)
        if yaml_metadata:
            metadata.update(yaml_metadata)
            log.debug(f"Added YAML metadata to placeholder '{placeholder_name}': {yaml_metadata}")

        # Tolerance parameter takes precedence over tolerance in yaml_metadata
        if tolerance is not None:
            metadata['tolerance'] = tolerance
            log.debug(f"Overriding tolerance from explicit parameter: {tolerance}")

        self.variable_registry._placeholder_metadata[placeholder_name] = metadata
        log.debug(
            f"Added timestamp metadata for '{placeholder_name}': value='{timestamp_value}', tolerance={tolerance}"
        )

        # Only add placeholder to template context if it does NOT have tolerance
        # Tolerance placeholders should remain as placeholders for VM-side processing
        if template_context is not None and tolerance is None and 'interval' not in metadata:
            template_context[placeholder_name] = timestamp_value
            log.debug(
                f"Added non-tolerance placeholder '{placeholder_name}' to template context with value '{timestamp_value}'"
            )
        elif tolerance is not None:
            log.debug(
                f"Skipping template context addition for tolerance placeholder '{placeholder_name}' (tolerance={tolerance})"
            )

    def add_tolerance_metadata_from_analysis(
        self, placeholder_name: str, analysis: FilterAnalysis, template_context: dict[str, Any]
    ):
        """
        Add metadata for a tolerance-based placeholder created from filter analysis.

        Args:
            placeholder_name: Name of the placeholder
            analysis: Analysis results from the template
            template_context: Context to resolve the base timestamp value
        """
        if not self.variable_registry:
            log.warning(f"No variable registry available to store metadata for '{placeholder_name}'")
            return

        if not hasattr(self.variable_registry, '_placeholder_metadata'):
            self.variable_registry._placeholder_metadata = {}

        # Resolve the base timestamp value (without tolerance filter)
        base_timestamp_value = None
        if analysis.variable_name and analysis.variable_name in template_context:
            base_timestamp_value = template_context[analysis.variable_name]

        # For tolerance placeholders, keep raw Unix timestamp - let VM handle all filtering
        resolved_value = base_timestamp_value
        log.debug(f"Keeping raw Unix timestamp for tolerance placeholder: '{resolved_value}'")

        # Create metadata
        metadata = {
            'raw_value': str(base_timestamp_value) if base_timestamp_value else analysis.original_template,
            'resolved_value': str(resolved_value) if resolved_value else analysis.original_template,
            'type': 'timestamp',
        }

        if analysis.tolerance_values:
            metadata['tolerance'] = list(analysis.tolerance_values)
        if analysis.has_localtime:
            metadata['localtime'] = True

        self.variable_registry._placeholder_metadata[placeholder_name] = metadata
        log.debug(f"Added tolerance metadata for '{placeholder_name}': {metadata}")

        # Do NOT add tolerance placeholders to template context
        # They should remain as placeholders for VM-side processing
        log.debug(f"Skipping template context addition for tolerance placeholder '{placeholder_name}' (has tolerance)")

    def get_placeholder_metadata(self) -> dict[str, Any]:
        """
        Get all placeholder metadata created during processing.

        Returns:
            Dictionary of placeholder metadata
        """
        if self.variable_registry and hasattr(self.variable_registry, '_placeholder_metadata'):
            return self.variable_registry._placeholder_metadata
        return {}
