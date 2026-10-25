"""Jinja2 template resolution with filter-aware placeholders (tolerance) and client-side formatting."""

import datetime
import logging
import re
from typing import Any

import dateutil.parser
import jinja2
import pytz

from adare.backend.experiment.placeholders import FilterAnalysis, MetadataManager, ToleranceDetector

log = logging.getLogger(__name__)


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
        self.jinja_env = jinja_env
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
        """
        if not template_context:
            log.warning(f"No template context available to resolve '{template_string}'")
            return template_string

        try:
            if self.jinja_env:
                template = self.jinja_env.from_string(template_string)
                resolved = template.render(template_context)
            else:
                import jinja2

                template = jinja2.Template(template_string)
                resolved = template.render(template_context)
            log.debug(f"Resolved template '{template_string}' to '{resolved}'")
            return resolved
        except (jinja2.TemplateError, jinja2.UndefinedError, TypeError, ValueError) as e:
            log.warning(f"Template resolution error for '{template_string}': {e}")
            return template_string
        except (KeyError, AttributeError) as e:
            log.warning(f"Unexpected error resolving template '{template_string}': {e}", exc_info=True)
            return template_string

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
                    except (jinja2.TemplateError, jinja2.UndefinedError, KeyError, TypeError, ValueError) as e:
                        log.warning(f"Failed to resolve template '{template_expr}': {e}")
                        replacement = template_expr  # Keep original if resolution fails

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
        try:
            variable_name = filter_analysis.variable_name
            format_string = filter_analysis.format_string

            if not variable_name or not format_string:
                log.warning(f"Missing variable name or format string for template: {template_expr}")
                return template_expr

            if variable_name not in template_context:
                log.warning(f"Variable '{variable_name}' not found in template context for formatting")
                return template_expr

            timestamp_value = template_context[variable_name]
            log.debug(
                f"Formatting timestamp '{variable_name}' with value '{timestamp_value}' using format '{format_string}'"
            )

            # Convert to datetime and apply timezone if needed
            dt = self._parse_timestamp_value(timestamp_value)
            dt = self._apply_timezone_conversion(dt, variable_name)

            # Apply format string
            formatted = dt.strftime(format_string)
            log.info(f"Successfully formatted timestamp '{variable_name}' -> '{formatted}'")
            return formatted

        except (ValueError, TypeError, KeyError, AttributeError, OverflowError) as e:
            log.warning(f"Failed to apply format filter to '{template_expr}': {e}")
            return template_expr

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

        try:
            source_var = self.metadata_manager.variable_registry.get(variable_name)
            if not (source_var and hasattr(source_var, 'structured_metadata') and source_var.structured_metadata):
                return dt

            tz_str = source_var.structured_metadata.timezone
            if not tz_str:
                return dt

            target_tz = self._parse_timezone(tz_str)
            return dt.astimezone(target_tz)

        except (ValueError, TypeError, KeyError, AttributeError, pytz.exceptions.UnknownTimeZoneError) as e:
            log.debug(f"Could not apply timezone conversion: {e}")
            return dt

    def _parse_timezone(self, tz_str: str) -> datetime.timezone:
        """Parse timezone string into timezone object."""
        if tz_str.startswith(('+', '-')):
            # Parse offset format like "+04:00"
            sign = 1 if tz_str[0] == '+' else -1
            hours, minutes = map(int, tz_str[1:].split(':'))
            offset = sign * (hours * 60 + minutes)
            return datetime.timezone(datetime.timedelta(minutes=offset))
        # Named timezone
        return pytz.timezone(tz_str)
