"""
Variable Resolver

Handles conversion of YAML custom tags to variable placeholders for VM processing
and provides template processing functionality for playbook actions.
This module provides clean separation between execution logic and variable resolution.
"""

from typing import Dict, Any, List, Optional, Tuple
import logging
import re
import copy
import jinja2
from dataclasses import dataclass

log = logging.getLogger(__name__)


@dataclass
class FilterAnalysis:
    """Analysis of filters applied to a Jinja2 template"""
    has_tolerance: bool = False
    has_format: bool = False
    has_localtime: bool = False
    tolerance_values: Optional[Tuple[int, int]] = None
    format_string: Optional[str] = None
    original_template: str = ""
    variable_name: Optional[str] = None


@dataclass
class ItemInfo:
    """Information about an item being processed"""
    type: str  # 'timestamp', 'regex', 'string'
    value: Any
    metadata: Dict[str, Any]
    filters_applied: FilterAnalysis
    source: str  # 'yaml_tag' or 'jinja_template'


class MetadataManager:
    """Handles placeholder metadata creation and management."""

    def __init__(self, variable_registry=None):
        """
        Initialize metadata manager.

        Args:
            variable_registry: Variable registry to store metadata in
        """
        self.variable_registry = variable_registry

    def add_regex_metadata(self, placeholder_name: str, regex_pattern: str, template_context: Optional[Dict[str, Any]] = None):
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
            'type': 'regex'
        }
        log.debug(f"Added regex metadata for '{placeholder_name}': pattern='{regex_pattern}'")

        # Add placeholder to current template context for subsequent Jinja resolution
        if template_context is not None:
            template_context[placeholder_name] = regex_pattern
            log.debug(f"CLAUDE: Added regex placeholder '{placeholder_name}' to template context with value '{regex_pattern}'")

    def add_timestamp_metadata(self, placeholder_name: str, timestamp_value: str, tolerance: Optional[Any] = None, template_context: Optional[Dict[str, Any]] = None, yaml_metadata: Optional[Dict[str, Any]] = None):
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

        metadata = {
            'raw_value': timestamp_value,
            'resolved_value': timestamp_value,
            'type': 'timestamp'
        }

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
        log.debug(f"Added timestamp metadata for '{placeholder_name}': value='{timestamp_value}', tolerance={tolerance}")

        # Only add placeholder to template context if it does NOT have tolerance
        # Tolerance placeholders should remain as placeholders for VM-side processing
        if template_context is not None and tolerance is None:
            template_context[placeholder_name] = timestamp_value
            log.debug(f"CLAUDE: Added non-tolerance placeholder '{placeholder_name}' to template context with value '{timestamp_value}'")
        elif tolerance is not None:
            log.debug(f"CLAUDE: Skipping template context addition for tolerance placeholder '{placeholder_name}' (tolerance={tolerance})")

    def add_tolerance_metadata_from_analysis(self, placeholder_name: str, analysis: FilterAnalysis, template_context: Dict[str, Any]):
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
            'type': 'timestamp'
        }

        if analysis.tolerance_values:
            metadata['tolerance'] = list(analysis.tolerance_values)
        if analysis.has_localtime:
            metadata['localtime'] = True

        self.variable_registry._placeholder_metadata[placeholder_name] = metadata
        log.debug(f"Added tolerance metadata for '{placeholder_name}': {metadata}")

        # Do NOT add tolerance placeholders to template context
        # They should remain as placeholders for VM-side processing
        log.debug(f"CLAUDE: Skipping template context addition for tolerance placeholder '{placeholder_name}' (has tolerance)")

    def get_placeholder_metadata(self) -> Dict[str, Any]:
        """
        Get all placeholder metadata created during processing.

        Returns:
            Dictionary of placeholder metadata
        """
        if (self.variable_registry and
            hasattr(self.variable_registry, '_placeholder_metadata')):
            return self.variable_registry._placeholder_metadata
        return {}


class YamlTagProcessor:
    """Processes YAML custom tags by converting them to variable placeholders."""

    def __init__(self, metadata_manager: MetadataManager, tolerance_detector: 'ToleranceDetector'):
        """
        Initialize YAML tag processor.

        Args:
            metadata_manager: MetadataManager instance for storing metadata
            tolerance_detector: ToleranceDetector instance for analyzing tolerance
        """
        self.metadata_manager = metadata_manager
        self.tolerance_detector = tolerance_detector
        self._placeholder_counter = 0

    def create_placeholder_name(self, tag_type: str) -> str:
        """
        Create a unique placeholder name.

        Args:
            tag_type: Type of tag ('regex', 'timestamp', etc.)

        Returns:
            Unique placeholder name like 'regex_0_resolved'
        """
        placeholder_name = f'{tag_type}_{self._placeholder_counter}_resolved'
        self._placeholder_counter += 1
        return placeholder_name

    def process_yaml_tags(self, data: Dict[str, Any], template_context: Optional[Dict[str, Any]] = None, template_resolver=None) -> Dict[str, Any]:
        """
        Process YAML custom tags (existing logic, renamed for clarity).

        Args:
            data: Data containing potential YAML custom tags
            template_context: Current template context
            template_resolver: Template resolver function for resolving templates
        """
        # Process parameter.entry specially for CSV tests and similar structures
        if (isinstance(data, dict) and
            'parameter' in data and
            isinstance(data['parameter'], dict) and
            'entry' in data['parameter']):

            original_entry = data['parameter']['entry']
            processed_entry = self.process_entry_list(original_entry, template_context, template_resolver)

            if processed_entry != original_entry:
                log.info(f"Processed entry list: {original_entry} -> {processed_entry}")
                # Make a copy to avoid modifying original
                import copy
                processed_data = copy.deepcopy(data)
                processed_data['parameter']['entry'] = processed_entry
                return processed_data

        # For other cases, recursively process all data
        return self.process_recursive(data, template_context, template_resolver)

    def process_entry_list(self, entry_list, template_context: Optional[Dict[str, Any]] = None, template_resolver=None) -> List[Any]:
        """
        Process an entry list containing potential YAML custom tag objects.

        Args:
            entry_list: List that may contain YamlRegexString, YamlTimestamp objects
            template_context: Current template context
            template_resolver: Template resolver function for resolving templates

        Returns:
            Processed list with placeholders replacing custom tag objects
        """
        if not isinstance(entry_list, list):
            return entry_list

        from adarelib.testset.yaml.customtags import YamlRegexString, YamlTimestamp

        processed_list = []

        for item in entry_list:
            if isinstance(item, YamlRegexString):
                # Convert regex object to placeholder
                placeholder_name = self.create_placeholder_name('regex')
                self.metadata_manager.add_regex_metadata(placeholder_name, item.string, template_context)
                processed_list.append(f'{{{{ {placeholder_name} }}}}')
                log.info(f"Converted YamlRegexString('{item.string}') to placeholder '{placeholder_name}'")

            elif isinstance(item, YamlTimestamp):
                # Apply smart resolution logic for YAML timestamps
                has_tolerance = self.tolerance_detector.has_yaml_tolerance(item)
                log.info(f"CLAUDE: Processing YamlTimestamp '{item.string}', has_tolerance={has_tolerance}, tolerance={getattr(item, 'tolerance', None)}")
                log.info(f"CLAUDE: YamlTimestamp object attributes: {[attr for attr in dir(item) if not attr.startswith('_')]}")
                log.info(f"CLAUDE: YamlTimestamp hasattr tolerance: {hasattr(item, 'tolerance')}, value: {getattr(item, 'tolerance', 'NOT_FOUND')}")

                if has_tolerance:
                    # Has tolerance - create placeholder, try to extract variable name from template
                    placeholder_name = None
                    timestamp_value = item.string
                    if '{{' in str(timestamp_value) and '}}' in str(timestamp_value):
                        # Extract variable name from template if possible
                        filter_analysis = self.tolerance_detector.analyze_jinja_template(str(timestamp_value))
                        if filter_analysis.variable_name:
                            placeholder_name = f"{filter_analysis.variable_name}_resolved"

                    if not placeholder_name:
                        placeholder_name = self.create_placeholder_name('timestamp')

                    # Resolve any templates within the timestamp value
                    if '{{' in str(timestamp_value) and '}}' in str(timestamp_value):
                        if template_resolver and template_context:
                            resolved_timestamp = template_resolver(timestamp_value, template_context)
                            # Check if resolution resulted in empty/blank value - this indicates the variable will be populated later
                            if not resolved_timestamp or resolved_timestamp.isspace():
                                log.info(f"CLAUDE: Timestamp template '{timestamp_value}' resolved to empty value - likely populated during execution")
                                # Store the original template for runtime resolution during test execution
                                resolved_timestamp = timestamp_value  # Keep original template for test-time resolution
                        else:
                            resolved_timestamp = timestamp_value
                        log.debug(f"Resolved timestamp template '{timestamp_value}' to '{resolved_timestamp}'")
                    else:
                        resolved_timestamp = timestamp_value

                    yaml_metadata = getattr(item, 'metadata', {})
                    self.metadata_manager.add_timestamp_metadata(placeholder_name, resolved_timestamp, getattr(item, 'tolerance', None), template_context, yaml_metadata)
                    processed_list.append(f'{{{{ {placeholder_name} }}}}')
                    log.info(f"CLAUDE: Converted YamlTimestamp with tolerance to placeholder '{placeholder_name}' (resolved_timestamp='{resolved_timestamp}')")
                else:
                    # No tolerance - resolve directly
                    timestamp_value = item.string
                    if '{{' in str(timestamp_value) and '}}' in str(timestamp_value):
                        if template_resolver and template_context:
                            resolved_timestamp = template_resolver(timestamp_value, template_context)
                        else:
                            resolved_timestamp = timestamp_value
                        log.info(f"CLAUDE: Resolved YamlTimestamp WITHOUT tolerance '{timestamp_value}' to '{resolved_timestamp}'")
                        processed_list.append(resolved_timestamp)
                    else:
                        log.info(f"Using YamlTimestamp value directly: '{timestamp_value}'")
                        processed_list.append(timestamp_value)
            else:
                # Regular item - keep as-is
                processed_list.append(item)

        return processed_list

    def process_recursive(self, data: Any, template_context: Optional[Dict[str, Any]] = None, template_resolver=None) -> Any:
        """
        Recursively process data structure for YAML custom tags.

        Args:
            data: Any data that might contain custom tags
            template_context: Current template context
            template_resolver: Template resolver function for resolving templates

        Returns:
            Processed data with placeholders
        """
        from adarelib.testset.yaml.customtags import YamlRegexString, YamlTimestamp

        if isinstance(data, dict):
            return {key: self.process_recursive(value, template_context, template_resolver) for key, value in data.items()}
        elif isinstance(data, list):
            return self.process_entry_list(data, template_context, template_resolver)  # Use specialized entry list processing
        elif isinstance(data, YamlRegexString):
            # Convert single regex object to placeholder
            placeholder_name = self.create_placeholder_name('regex')
            self.metadata_manager.add_regex_metadata(placeholder_name, data.string, template_context)
            log.info(f"Converted single YamlRegexString('{data.string}') to placeholder '{placeholder_name}'")
            return f'{{{{ {placeholder_name} }}}}'
        elif isinstance(data, YamlTimestamp):
            # Handle single timestamp objects (similar to list processing logic)
            has_tolerance = self.tolerance_detector.has_yaml_tolerance(data)
            log.info(f"CLAUDE: Processing single YamlTimestamp '{data.string}', has_tolerance={has_tolerance}")

            if has_tolerance:
                placeholder_name = self.create_placeholder_name('timestamp')
                timestamp_value = data.string
                # Resolve any templates within the timestamp value
                if '{{' in str(timestamp_value) and '}}' in str(timestamp_value):
                    if template_resolver and template_context:
                        resolved_timestamp = template_resolver(timestamp_value, template_context)
                        if not resolved_timestamp or resolved_timestamp.isspace():
                            resolved_timestamp = timestamp_value
                    else:
                        resolved_timestamp = timestamp_value
                else:
                    resolved_timestamp = timestamp_value

                yaml_metadata = getattr(data, 'metadata', {})
                self.metadata_manager.add_timestamp_metadata(placeholder_name, resolved_timestamp, getattr(data, 'tolerance', None), template_context, yaml_metadata)
                log.info(f"CLAUDE: Converted single YamlTimestamp with tolerance to placeholder '{placeholder_name}'")
                return f'{{{{ {placeholder_name} }}}}'
            else:
                # No tolerance - resolve directly
                timestamp_value = data.string
                if '{{' in str(timestamp_value) and '}}' in str(timestamp_value):
                    if template_resolver and template_context:
                        resolved_timestamp = template_resolver(timestamp_value, template_context)
                    else:
                        resolved_timestamp = timestamp_value
                    log.info(f"CLAUDE: Resolved single YamlTimestamp WITHOUT tolerance to '{resolved_timestamp}'")
                    return resolved_timestamp
                else:
                    log.info(f"Using single YamlTimestamp value directly: '{timestamp_value}'")
                    return timestamp_value
        else:
            return data


class JinjaTemplateResolver:
    """Handles all Jinja2 template processing and resolution."""

    def __init__(self, jinja_env=None, tolerance_detector: 'ToleranceDetector' = None,
                 metadata_manager: MetadataManager = None, yaml_tag_processor: YamlTagProcessor = None):
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
        import re
        return bool(re.match(r'^\{\{\s*\w+_resolved\s*\}\}$', text.strip()))

    def resolve_template_with_context(self, template_string: str, template_context: Dict[str, Any]) -> str:
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
        except Exception as e:
            log.warning(f"Failed to resolve template '{template_string}': {e}")
            return template_string

    def resolve_template(self, template_string: str, template_context: Dict[str, Any]) -> str:
        """
        Resolve a Jinja2 template string using the provided template context.

        Args:
            template_string: String containing {{}} templates
            template_context: Template context for resolution

        Returns:
            Resolved string with variables substituted
        """
        if not template_context:
            log.warning(f"No template context available to resolve '{template_string}'")
            return template_string

        try:
            import jinja2
            template = jinja2.Template(str(template_string))
            resolved = template.render(template_context)
            log.debug(f"Resolved template '{template_string}' to '{resolved}'")
            return resolved
        except Exception as e:
            log.warning(f"Failed to resolve template '{template_string}': {e}")
            return template_string

    def process_mixed_template_content(self, content: str, template_context: Dict[str, Any]) -> str:
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
        import re

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
                self.metadata_manager.add_tolerance_metadata_from_analysis(placeholder_name, filter_analysis, template_context)
                replacement = f'{{{{ {placeholder_name} }}}}'
                log.info(f"Created tolerance placeholder '{placeholder_name}' for template '{template_expr}' in mixed content")
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

    def process_jinja_templates(self, data: Any, template_context: Dict[str, Any]) -> Any:
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

        elif isinstance(data, dict):
            return {key: self.process_jinja_templates(value, template_context)
                    for key, value in data.items()}
        elif isinstance(data, list):
            return [self.process_jinja_templates(item, template_context)
                    for item in data]

        return data

    def _apply_format_filter(self, template_expr: str, filter_analysis: FilterAnalysis, template_context: Dict[str, Any]) -> str:
        """
        Apply timestamp formatting for format-only cases (no tolerance).

        Args:
            template_expr: Original template expression like "{{fixed_timestamp | format('%Y-%m-%dT%H:%M:%S')}}"
            filter_analysis: Analysis result containing format string and variable name
            template_context: Context containing variable values

        Returns:
            Formatted timestamp string
        """
        import datetime
        import dateutil.parser
        import pytz

        try:
            variable_name = filter_analysis.variable_name
            format_string = filter_analysis.format_string

            if not variable_name or not format_string:
                log.warning(f"Missing variable name or format string for template: {template_expr}")
                return template_expr

            # Get the timestamp value from context
            if variable_name not in template_context:
                log.warning(f"Variable '{variable_name}' not found in template context for formatting")
                return template_expr

            timestamp_value = template_context[variable_name]
            log.debug(f"CLAUDE: Formatting timestamp '{variable_name}' with value '{timestamp_value}' using format '{format_string}'")

            # Convert to datetime object
            if isinstance(timestamp_value, (int, float)):
                # Unix timestamp
                dt = datetime.datetime.fromtimestamp(timestamp_value, tz=pytz.UTC)
                log.debug(f"CLAUDE: Converted Unix timestamp {timestamp_value} to UTC datetime: {dt}")
            elif isinstance(timestamp_value, str):
                # Try to parse string timestamp
                try:
                    # First try as Unix timestamp string
                    unix_ts = float(timestamp_value)
                    dt = datetime.datetime.fromtimestamp(unix_ts, tz=pytz.UTC)
                    log.debug(f"CLAUDE: Converted Unix timestamp string '{timestamp_value}' to UTC datetime: {dt}")
                except ValueError:
                    # Parse as date string
                    dt = dateutil.parser.parse(timestamp_value)
                    if dt.tzinfo is None:
                        dt = dt.replace(tzinfo=pytz.UTC)
                    log.debug(f"CLAUDE: Parsed timestamp string '{timestamp_value}' to datetime: {dt}")
            else:
                log.warning(f"Unsupported timestamp type: {type(timestamp_value)}")
                return template_expr

            # Check for timezone metadata and apply timezone conversion if needed
            # Look up the variable in the registry to get timezone metadata
            if hasattr(self, 'metadata_manager') and self.metadata_manager.variable_registry:
                try:
                    source_var = self.metadata_manager.variable_registry.get(variable_name)
                    if source_var and hasattr(source_var, 'structured_metadata') and source_var.structured_metadata:
                        if source_var.structured_metadata.timezone:
                            # Parse timezone offset like "+04:00"
                            tz_str = source_var.structured_metadata.timezone
                            if tz_str.startswith(('+', '-')):
                                # Parse offset format like "+04:00"
                                sign = 1 if tz_str[0] == '+' else -1
                                hours, minutes = map(int, tz_str[1:].split(':'))
                                offset = sign * (hours * 60 + minutes)
                                target_tz = datetime.timezone(datetime.timedelta(minutes=offset))
                                dt = dt.astimezone(target_tz)
                                log.debug(f"CLAUDE: Converted to timezone {tz_str}: {dt}")
                            else:
                                # Try as named timezone
                                target_tz = pytz.timezone(tz_str)
                                dt = dt.astimezone(target_tz)
                                log.debug(f"CLAUDE: Converted to timezone {tz_str}: {dt}")
                except Exception as e:
                    log.debug(f"CLAUDE: Could not apply timezone conversion: {e}")

            # Apply format string
            formatted = dt.strftime(format_string)
            log.info(f"CLAUDE: Successfully formatted timestamp '{variable_name}' -> '{formatted}'")
            return formatted

        except Exception as e:
            log.warning(f"Failed to apply format filter to '{template_expr}': {e}")
            return template_expr


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
            log.debug(f"Found localtime filter")

        return analysis
    
    def has_yaml_tolerance(self, yaml_obj) -> bool:
        """Check if YAML object has explicitly defined tolerance"""
        return hasattr(yaml_obj, 'tolerance') and yaml_obj.tolerance is not None


class VariableResolver:
    """
    Resolves YAML custom tags in data by converting them to variable placeholders
    with associated metadata for VM-side processing.
    
    This follows the same pattern as timestamp tolerance handling:
    - Client: Convert custom tag objects to {{ placeholder_resolved }} + metadata
    - VM: Use metadata type to recreate appropriate objects for comparison
    """
    
    def __init__(self, variable_registry=None, jinja_env=None):
        """
        Initialize resolver with optional variable registry and Jinja environment.

        Args:
            variable_registry: Variable registry to store placeholder metadata
            jinja_env: Jinja2 environment with filters for template processing
        """
        self.variable_registry = variable_registry
        self.jinja_env = jinja_env
        self._tolerance_detector = ToleranceDetector()
        self._metadata_manager = MetadataManager(variable_registry)
        self._yaml_tag_processor = YamlTagProcessor(self._metadata_manager, self._tolerance_detector)
        self._jinja_resolver = JinjaTemplateResolver(jinja_env, self._tolerance_detector, self._metadata_manager, self._yaml_tag_processor)
    
    def process_data(self, data: Dict[str, Any], template_context: Dict[str, Any] = None) -> Dict[str, Any]:
        """
        Unified processing of both YAML tags and Jinja2 templates.
        
        Args:
            data: Raw data containing potential YAML custom tag objects and Jinja templates
            template_context: Context for resolving Jinja2 templates
            
        Returns:
            Processed data with placeholders and metadata
        """
        log.debug(f"Starting unified variable resolution for: {data}")
        
        # Store template context for use in helper methods
        self._current_template_context = template_context or {}
        
        # Phase 1: Process YAML custom tags (existing logic)
        data = self._yaml_tag_processor.process_yaml_tags(data, template_context, self._jinja_resolver.resolve_template_with_context)

        # Phase 2: Process Jinja2 templates with filter analysis
        if template_context and self.jinja_env:
            data = self._jinja_resolver.process_jinja_templates(data, self._current_template_context)
        
        return data
    
    def get_placeholder_metadata(self) -> Dict[str, Any]:
        """
        Get all placeholder metadata created during processing.

        Returns:
            Dictionary of placeholder metadata
        """
        return self._metadata_manager.get_placeholder_metadata()
    
    # Template Processing Methods (moved from PlaybookController)
    
    def resolve_action_variables(self, action, execution_context: Dict[str, Any]):
        """Resolve variables in action fields that support templating.
        
        Returns a copy of the action with variables resolved in applicable fields.
        """
        from adare.types.playbook import (
            CommandAction, KeyboardAction, ActionTestAction, SaveTimestampAction, DragAction, PullAction
        )
        
        # Create a deep copy to avoid modifying the original
        resolved_action = copy.deepcopy(action)
        
        # Resolve description for all actions
        if hasattr(resolved_action, 'description') and resolved_action.description:
            resolved_action.description = self.replace_variables(resolved_action.description, execution_context)
        
        # Resolve fields specific to each action type
        if isinstance(action, CommandAction):
            if resolved_action.command:
                resolved_action.command = self.replace_variables(resolved_action.command, execution_context)
            if resolved_action.cwd:
                resolved_action.cwd = self.replace_variables(resolved_action.cwd, execution_context)
            if resolved_action.env:
                resolved_action.env = {k: self.replace_variables(str(v), execution_context) for k, v in resolved_action.env.items()}
        
        elif isinstance(action, KeyboardAction):
            if resolved_action.text:
                resolved_action.text = self.replace_variables(resolved_action.text, execution_context)
        
        elif isinstance(action, ActionTestAction):
            if resolved_action.name:
                resolved_action.name = self.replace_variables(resolved_action.name, execution_context)
        
        elif isinstance(action, SaveTimestampAction):
            if resolved_action.variable:
                resolved_action.variable = self.replace_variables(resolved_action.variable, execution_context)

        elif isinstance(action, PullAction):
            if resolved_action.src:
                resolved_action.src = self.replace_variables(resolved_action.src, execution_context)
            if resolved_action.dst:
                resolved_action.dst = self.replace_variables(resolved_action.dst, execution_context)

        # Resolve Target fields for actions that have targets
        if hasattr(resolved_action, 'target') and resolved_action.target:
            resolved_action.target = self.resolve_target_variables(resolved_action.target, execution_context)
        
        # Resolve Source/Destination targets for DragAction
        if isinstance(action, DragAction):
            if resolved_action.src:
                resolved_action.src = self.resolve_target_variables(resolved_action.src, execution_context)
            if resolved_action.dst:
                resolved_action.dst = self.resolve_target_variables(resolved_action.dst, execution_context)
        
        return resolved_action
    
    def resolve_target_variables(self, target, execution_context: Dict[str, Any]):
        """Resolve variables in Target fields."""
        resolved_target = copy.deepcopy(target)
        
        if resolved_target.image:
            resolved_target.image = self.replace_variables(resolved_target.image, execution_context)
        if resolved_target.text:
            resolved_target.text = self.replace_variables(resolved_target.text, execution_context)
        
        return resolved_target

    def replace_variables(self, text: str, execution_context: Dict[str, Any]) -> str:
        """Replace Jinja2 template variables in text with values or metadata placeholders.

        Variables with metadata are resolved to placeholders (e.g., VARTIMESTAMP_RESOLVED)
        and the metadata is captured for server-side processing.
        """
        if not text or '{{' not in text:
            return text

        try:
            result = text
            max_iterations = 10  # Prevent infinite loops
            previous_results = set()  # Track previous results to detect cycles

            for i in range(max_iterations):
                # If no more variables to replace, we're done
                if '{{' not in result:
                    break

                # Check for cycles (same result appearing again)
                if result in previous_results:
                    log.warning(f"Circular variable reference detected in: {text}")
                    break

                previous_results.add(result)

                # Create formatted context with metadata-aware variable handling
                formatted_context = self.get_formatted_context(execution_context, for_tests=False)

                # CLAUDE: Add debug logging for adare_user_home specifically
                if 'adare_user_home' in result:
                    log.info(f"CLAUDE: Processing adare_user_home template '{result}'")
                    log.info(f"CLAUDE: Execution context keys: {list(execution_context.keys())}")
                    log.info(f"CLAUDE: Formatted context keys: {list(formatted_context.keys())}")
                    if 'adare_user_home' in formatted_context:
                        log.info(f"CLAUDE: adare_user_home value: '{formatted_context['adare_user_home']}'")
                    else:
                        log.info("CLAUDE: adare_user_home NOT found in formatted context!")
                        # Check if variable registry has it
                        if hasattr(self, 'variable_registry') and self.variable_registry:
                            registry_vars = self.variable_registry.variables
                            log.info(f"CLAUDE: Variable registry has keys: {list(registry_vars.keys())}")
                            if 'adare_user_home' in registry_vars:
                                log.info(f"CLAUDE: Registry adare_user_home value: '{registry_vars['adare_user_home'].value}'")

                # Perform template replacement with metadata capture
                log.debug(f"Processing template: '{result}' with context keys: {list(formatted_context.keys())}")
                if 'username' in result:
                    log.info(f"CLAUDE: Processing username template '{result}' with context: {formatted_context}")
                template = jinja2.Template(result)

                # Add custom filters for metadata capture
                template.environment.filters.update(self.get_custom_filters())

                new_result = template.render(formatted_context)
                log.debug(f"Template result: '{new_result}'")
                if 'username' in result:
                    log.info(f"CLAUDE: Username template result: '{result}' -> '{new_result}'")

                # CLAUDE: Add debug logging for adare_user_home result
                if 'adare_user_home' in result:
                    log.info(f"CLAUDE: adare_user_home template result: '{result}' -> '{new_result}'")

                # If no change occurred, break to avoid infinite loops
                if new_result == result:
                    break

                result = new_result

            # Warn if we hit max iterations (possible infinite loop)
            if i == max_iterations - 1 and '{{' in result:
                log.warning(f"Variable replacement hit max iterations for: {text}")

            return result
        except (jinja2.TemplateError, jinja2.UndefinedError, KeyError, TypeError, ValueError) as e:
            if 'username' in text:
                log.warning(f"CLAUDE: Failed to replace username variables in '{text}': {e}")
            elif 'adare_user_home' in text:
                log.warning(f"CLAUDE: Failed to replace adare_user_home variables in '{text}': {e}")
            else:
                log.warning(f"Failed to replace variables in '{text}': {e}")
            return text
    
    def get_formatted_context(self, execution_context: Dict[str, Any] = None, for_tests: bool = False) -> Dict[str, Any]:
        """Get execution context with smart variable handling based on usage."""
        # If we have a variable registry, use its smart execution context
        if hasattr(self, 'variable_registry') and self.variable_registry:
            registry_context = self.variable_registry.to_execution_context(for_tests=for_tests)
            # Merge with existing execution context
            merged_context = (execution_context or {}).copy()
            merged_context.update(registry_context)
            return merged_context
        
        # Fallback to simple execution context copy
        return (execution_context or {}).copy()
    
    def get_custom_filters(self) -> Dict[str, Any]:
        """Get custom Jinja2 filters from variable registry metadata."""
        # Get filters from variable registry if available
        if hasattr(self, 'variable_registry') and self.variable_registry:
            registry_filters = self.variable_registry.get_all_jinja_filters()
            if registry_filters:
                log.debug(f"Using {len(registry_filters)} filters from variable registry: {list(registry_filters.keys())}")
                return registry_filters
        
        # Fallback to empty dict - no custom filters available
        log.debug("No variable registry filters available, using no custom filters")
        return {}