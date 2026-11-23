"""Jinja2 template resolution with filter-aware placeholders (tolerance) and client-side formatting."""

import datetime
import logging
import re
from typing import Any

import dateutil.parser
import jinja2
import pytz

from adare.backend.experiment.placeholders import FilterAnalysis, MetadataManager, ToleranceDetector
from adare.exceptions import TemplateResolutionError
from adarelib.common.timezones import _apply_timezone

log = logging.getLogger(__name__)

# What rendering a template (or applying a filter to its value) can raise. Never swallowed: a test
# resolved to the unrendered ``{{ ... }}`` text would run, and pass or fail, on a wrong value.
_RENDER_ERRORS = (jinja2.TemplateError, TypeError, ValueError, KeyError, AttributeError)


def _cannot_render(template: str, error: Exception) -> TemplateResolutionError:
    return TemplateResolutionError(log, f"Cannot render test template '{template}': {type(error).__name__}: {error}")


class JinjaTemplateResolver:
    """Handles all Jinja2 template processing and resolution."""

    def __init__(
        self,
        jinja_env=None,
        tolerance_detector: ToleranceDetector = None,
        metadata_manager: MetadataManager = None,
        yaml_tag_processor=None,
    ):
        """
        Initialize Jinja template resolver.

        Args:
            jinja_env: Jinja2 environment with filters for template processing
            tolerance_detector: ToleranceDetector instance for analyzing tolerance
            metadata_manager: MetadataManager instance for storing metadata
            yaml_tag_processor: YamlTagProcessor for creating placeholders
        """
        # Test templates are strict: an undefined variable is an error (the test is ERROR), never ''.
        # An overlay shares the filters of the given environment but not its (lenient) ``undefined``.
        self.jinja_env: Any = jinja_env.overlay(undefined=jinja2.StrictUndefined) if jinja_env else None
        self.tolerance_detector = tolerance_detector
        self.metadata_manager = metadata_manager
        self.yaml_tag_processor = yaml_tag_processor

    def is_our_placeholder(self, text: str) -> bool:
        """Check if text is one of our generated placeholders."""

        return bool(re.match(r'^\{\{\s*\w+_resolved\s*\}\}$', text.strip()))

    def resolve_template_with_context(self, template_string: str, template_context: dict[str, Any]) -> str:
        """
        Resolve a Jinja2 template string using the provided template context.

        Args:
            template_string: Template string to resolve
            template_context: Context dictionary for template resolution

        Returns:
            Resolved string with variables substituted

        Raises:
            TemplateResolutionError: the template cannot be rendered (undefined variable, unknown filter, syntax
                error, a filter rejecting its value, ...)
        """
        try:
            if self.jinja_env:
                template = self.jinja_env.from_string(template_string)
            else:
                template = jinja2.Template(template_string, undefined=jinja2.StrictUndefined)
            resolved = template.render(template_context or {})
        except _RENDER_ERRORS as e:
            raise _cannot_render(template_string, e) from e
        log.debug(f"Resolved template '{template_string}' to '{resolved}'")
        return resolved

    def process_mixed_template_content(self, content: str, template_context: dict[str, Any]) -> str:
        """
        Process content that may contain both regular text and Jinja2 templates.

        This method finds individual {{ }} template expressions and processes them
        based on their filter analysis, while preserving the surrounding text.

        Args:
            content: String containing mix of regular text and templates
            template_context: Context for resolving templates

        Returns:
            Processed content with templates resolved or converted to placeholders
        """

        # Find all {{ }} template expressions
        template_pattern = r'\{\{[^}]+\}\}'
        templates = re.finditer(template_pattern, content)

        result = content
        offset = 0  # Track offset due to replacements

        for match in templates:
            template_expr = match.group(0)
            start_pos = match.start() + offset
            end_pos = match.end() + offset

            # Analyze this specific template expression
            filter_analysis = self.tolerance_detector.analyze_jinja_template(template_expr)

            if filter_analysis.has_tolerance:
                # Has tolerance - create placeholder + metadata using variable name
                if filter_analysis.variable_name:
                    placeholder_name = f"{filter_analysis.variable_name}_resolved"
                else:
                    placeholder_name = self.yaml_tag_processor.create_placeholder_name('timestamp')
                self.metadata_manager.add_tolerance_metadata_from_analysis(
                    placeholder_name, filter_analysis, template_context
                )
                replacement = f'{{{{ {placeholder_name} }}}}'
                log.info(
                    f"Created tolerance placeholder '{placeholder_name}' for template '{template_expr}' in mixed content"
                )
            else:
                # No tolerance - check if format filter needs special handling
                if filter_analysis.has_format:
                    # Format-only case: Apply timestamp formatting client-side
                    replacement = self._apply_format_filter(template_expr, filter_analysis, template_context)
                    log.debug(f"Applied format filter to '{template_expr}' -> '{replacement}' in mixed content")
                else:
                    # Regular template - resolve directly
                    try:
                        template = self.jinja_env.from_string(template_expr)
                        replacement = template.render(template_context)
                        log.debug(f"Resolved template '{template_expr}' to '{replacement}' in mixed content")
                    except _RENDER_ERRORS as e:
                        raise _cannot_render(template_expr, e) from e

            # Replace this template in the result
            result = result[:start_pos] + replacement + result[end_pos:]

            # Update offset for next replacements
            offset += len(replacement) - len(template_expr)

        log.debug(f"Mixed content processing: '{content}' -> '{result}'")
        return result

    def process_jinja_templates(self, data: Any, template_context: dict[str, Any]) -> Any:
        """
        Process Jinja2 templates with smart resolution based on filter analysis.

        Args:
            data: Data that may contain Jinja2 templates
            template_context: Context for resolving templates

        Returns:
            Processed data with resolved values or placeholders
        """
        if isinstance(data, str) and '{{' in data and '}}' in data:
            # Skip processing our own placeholders that end with '_resolved'
            if '_resolved' in data and self.is_our_placeholder(data):
                log.debug(f"Skipping processing of our own placeholder: '{data}'")
                return data

            # Use new method to handle mixed content (templates embedded in larger text)
            return self.process_mixed_template_content(data, template_context)

        if isinstance(data, dict):
            return {key: self.process_jinja_templates(value, template_context) for key, value in data.items()}
        if isinstance(data, list):
            return [self.process_jinja_templates(item, template_context) for item in data]

        return data

    def _apply_format_filter(
        self, template_expr: str, filter_analysis: FilterAnalysis, template_context: dict[str, Any]
    ) -> str:
        """Apply timestamp formatting for format-only cases (no tolerance)."""
        variable_name = filter_analysis.variable_name
        format_string = filter_analysis.format_string

        if not variable_name or not format_string:
            raise TemplateResolutionError(
                log, f"Cannot render test template '{template_expr}': no variable or format string found in it"
            )
        if variable_name not in template_context:
            raise TemplateResolutionError(
                log,
                f"Cannot render test template '{template_expr}': variable '{variable_name}' "
                f"is not set (it must be defined before the test runs)",
            )

        timestamp_value = template_context[variable_name]
        log.debug(
            f"Formatting timestamp '{variable_name}' with value '{timestamp_value}' using format '{format_string}'"
        )
        try:
            # Convert to datetime and apply timezone if needed
            dt = self._parse_timestamp_value(timestamp_value)
            dt = self._apply_timezone_conversion(dt, variable_name)

            # Apply format string
            formatted = dt.strftime(format_string)
        except (*_RENDER_ERRORS, OverflowError, OSError) as e:
            raise _cannot_render(template_expr, e) from e
        log.info(f"Successfully formatted timestamp '{variable_name}' -> '{formatted}'")
        return formatted

    def _parse_timestamp_value(self, timestamp_value: Any) -> datetime.datetime:
        """Parse various timestamp formats into datetime object."""
        if isinstance(timestamp_value, (int, float)):
            return datetime.datetime.fromtimestamp(timestamp_value, tz=pytz.UTC)

        if isinstance(timestamp_value, str):
            try:
                # Try as Unix timestamp string first
                unix_ts = float(timestamp_value)
                return datetime.datetime.fromtimestamp(unix_ts, tz=pytz.UTC)
            except ValueError:
                # Parse as date string
                dt = dateutil.parser.parse(timestamp_value)
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=pytz.UTC)
                return dt

        raise ValueError(f"Unsupported timestamp type: {type(timestamp_value)}")

    def _apply_timezone_conversion(self, dt: datetime.datetime, variable_name: str) -> datetime.datetime:
        """Apply timezone conversion based on variable metadata."""
        if not (hasattr(self, 'metadata_manager') and self.metadata_manager.variable_registry):
            return dt

        source_var = self.metadata_manager.variable_registry.get(variable_name)
        if not (source_var and hasattr(source_var, 'structured_metadata') and source_var.structured_metadata):
            return dt

        tz_str = source_var.structured_metadata.timezone
        if not tz_str:
            return dt

        # adarelib parses the zone like everywhere else; a bad one raises ValidationError (a ValueError)
        return dt.astimezone(_apply_timezone(datetime.datetime(2000, 1, 1), tz_str).tzinfo)
