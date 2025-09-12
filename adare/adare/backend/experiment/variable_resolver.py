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


class ToleranceDetector:
    """Detects tolerance usage in templates and YAML."""
    
    TOLERANCE_PATTERN = re.compile(r'\|\s*tolerance\s*\(\s*([^,\)]+)(?:\s*,\s*([^,\)]+))?\s*\)')
    FORMAT_PATTERN = re.compile(r'\|\s*format\s*\(\s*["\']([^"\']+)["\']')
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
        self._placeholder_counter = 0
        self._tolerance_detector = ToleranceDetector()
    
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
        data = self._process_yaml_tags(data)
        
        # Phase 2: Process Jinja2 templates with filter analysis
        if template_context and self.jinja_env:
            data = self._process_jinja_templates(data, self._current_template_context)
        
        return data
    
    def _process_yaml_tags(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Process YAML custom tags (existing logic, renamed for clarity).
        """
        # Process parameter.entry specially for CSV tests and similar structures
        if (isinstance(data, dict) and 
            'parameter' in data and 
            isinstance(data['parameter'], dict) and
            'entry' in data['parameter']):
            
            original_entry = data['parameter']['entry']
            processed_entry = self._process_entry_list(original_entry)
            
            if processed_entry != original_entry:
                log.info(f"Processed entry list: {original_entry} -> {processed_entry}")
                # Make a copy to avoid modifying original
                import copy
                processed_data = copy.deepcopy(data)
                processed_data['parameter']['entry'] = processed_entry
                return processed_data
        
        # For other cases, recursively process all data
        return self._process_recursive(data)
    
    def _process_entry_list(self, entry_list) -> List[Any]:
        """
        Process an entry list containing potential YAML custom tag objects.
        
        Args:
            entry_list: List that may contain YamlRegexString, YamlTimestamp objects
            
        Returns:
            Processed list with placeholders replacing custom tag objects
        """
        if not isinstance(entry_list, list):
            return entry_list
            
        from adarelib.testset.yaml.customtags import YamlRegexString, YamlTimestamp
        
        processed_list = []
        has_changes = False
        
        for item in entry_list:
            if isinstance(item, YamlRegexString):
                # Convert regex object to placeholder
                placeholder_name = self._create_placeholder_name('regex')
                self._add_regex_metadata(placeholder_name, item.string)
                processed_list.append(f'{{{{ {placeholder_name} }}}}')
                log.info(f"Converted YamlRegexString('{item.string}') to placeholder '{placeholder_name}'")
                has_changes = True
                
            elif isinstance(item, YamlTimestamp):
                # Apply smart resolution logic for YAML timestamps
                has_tolerance = self._tolerance_detector.has_yaml_tolerance(item)
                log.info(f"CLAUDE: Processing YamlTimestamp '{item.string}', has_tolerance={has_tolerance}, tolerance={getattr(item, 'tolerance', None)}")
                log.info(f"CLAUDE: YamlTimestamp object attributes: {[attr for attr in dir(item) if not attr.startswith('_')]}")
                log.info(f"CLAUDE: YamlTimestamp hasattr tolerance: {hasattr(item, 'tolerance')}, value: {getattr(item, 'tolerance', 'NOT_FOUND')}")
                
                if has_tolerance:
                    # Has tolerance - create placeholder, try to extract variable name from template
                    placeholder_name = None
                    timestamp_value = item.string
                    if '{{' in str(timestamp_value) and '}}' in str(timestamp_value):
                        # Extract variable name from template if possible
                        filter_analysis = self._tolerance_detector.analyze_jinja_template(str(timestamp_value))
                        if filter_analysis.variable_name:
                            placeholder_name = f"{filter_analysis.variable_name}_resolved"
                    
                    if not placeholder_name:
                        placeholder_name = self._create_placeholder_name('timestamp')
                    
                    # Resolve any templates within the timestamp value
                    if '{{' in str(timestamp_value) and '}}' in str(timestamp_value):
                        if hasattr(self, '_current_template_context'):
                            resolved_timestamp = self._resolve_template_with_context(timestamp_value, self._current_template_context)
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
                    
                    self._add_timestamp_metadata(placeholder_name, resolved_timestamp, getattr(item, 'tolerance', None))
                    processed_list.append(f'{{{{ {placeholder_name} }}}}')
                    log.info(f"CLAUDE: Converted YamlTimestamp with tolerance to placeholder '{placeholder_name}' (resolved_timestamp='{resolved_timestamp}')")
                    has_changes = True
                else:
                    # No tolerance - resolve directly
                    timestamp_value = item.string
                    if '{{' in str(timestamp_value) and '}}' in str(timestamp_value):
                        if hasattr(self, '_current_template_context'):
                            resolved_timestamp = self._resolve_template_with_context(timestamp_value, self._current_template_context)
                        else:
                            resolved_timestamp = timestamp_value
                        log.info(f"CLAUDE: Resolved YamlTimestamp WITHOUT tolerance '{timestamp_value}' to '{resolved_timestamp}'")
                        processed_list.append(resolved_timestamp)
                    else:
                        log.info(f"Using YamlTimestamp value directly: '{timestamp_value}'")
                        processed_list.append(timestamp_value)
                    has_changes = True
                
            else:
                # Regular item - keep as-is
                processed_list.append(item)
        
        return processed_list
    
    def _process_recursive(self, data: Any) -> Any:
        """
        Recursively process data structure for YAML custom tags.
        
        Args:
            data: Any data that might contain custom tags
            
        Returns:
            Processed data with placeholders
        """
        if isinstance(data, dict):
            return {key: self._process_recursive(value) for key, value in data.items()}
        elif isinstance(data, list):
            return self._process_entry_list(data)  # Use specialized entry list processing
        else:
            return data
    
    def _create_placeholder_name(self, tag_type: str) -> str:
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
    
    def _resolve_template(self, template_string: str) -> str:
        """
        Resolve a Jinja2 template string using the provided template context.
        
        Args:
            template_string: String containing {{}} templates
            
        Returns:
            Resolved string with variables substituted
        """
        if not self.template_context:
            log.warning(f"No template context available to resolve '{template_string}'")
            return template_string
            
        try:
            import jinja2
            template = jinja2.Template(str(template_string))
            resolved = template.render(self.template_context)
            log.debug(f"Resolved template '{template_string}' to '{resolved}'")
            return resolved
        except Exception as e:
            log.warning(f"Failed to resolve template '{template_string}': {e}")
            return template_string
    
    def _add_regex_metadata(self, placeholder_name: str, regex_pattern: str):
        """
        Add regex metadata following the same structure as timestamp tolerance.
        
        Args:
            placeholder_name: Name of the placeholder
            regex_pattern: The regex pattern to store
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
        
        # CLAUDE: Add placeholder to current template context for subsequent Jinja resolution
        if hasattr(self, '_current_template_context') and self._current_template_context is not None:
            self._current_template_context[placeholder_name] = regex_pattern
            log.debug(f"CLAUDE: Added regex placeholder '{placeholder_name}' to template context with value '{regex_pattern}'")
    
    def _add_timestamp_metadata(self, placeholder_name: str, timestamp_value: str, tolerance: Optional[Any] = None):
        """
        Add timestamp metadata following the existing structure.
        
        Args:
            placeholder_name: Name of the placeholder
            timestamp_value: The timestamp value
            tolerance: Optional tolerance information
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
        
        if tolerance is not None:
            metadata['tolerance'] = tolerance
        
        self.variable_registry._placeholder_metadata[placeholder_name] = metadata
        log.debug(f"Added timestamp metadata for '{placeholder_name}': value='{timestamp_value}', tolerance={tolerance}")
        
        # CLAUDE: Only add placeholder to template context if it does NOT have tolerance
        # Tolerance placeholders should remain as placeholders for VM-side processing
        if hasattr(self, '_current_template_context') and self._current_template_context is not None and tolerance is None:
            self._current_template_context[placeholder_name] = timestamp_value
            log.debug(f"CLAUDE: Added non-tolerance placeholder '{placeholder_name}' to template context with value '{timestamp_value}'")
        elif tolerance is not None:
            log.debug(f"CLAUDE: Skipping template context addition for tolerance placeholder '{placeholder_name}' (tolerance={tolerance})")
    
    def _process_jinja_templates(self, data: Any, template_context: Dict[str, Any]) -> Any:
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
            if '_resolved' in data and self._is_our_placeholder(data):
                log.debug(f"Skipping processing of our own placeholder: '{data}'")
                return data
            
            # Use new method to handle mixed content (templates embedded in larger text)
            return self._process_mixed_template_content(data, template_context)
                    
        elif isinstance(data, dict):
            return {key: self._process_jinja_templates(value, template_context) 
                    for key, value in data.items()}
        elif isinstance(data, list):
            return [self._process_jinja_templates(item, template_context) 
                    for item in data]
        
        return data
    
    def _process_mixed_template_content(self, content: str, template_context: Dict[str, Any]) -> str:
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
            filter_analysis = self._tolerance_detector.analyze_jinja_template(template_expr)
            
            if filter_analysis.has_tolerance:
                # Has tolerance - create placeholder + metadata using variable name
                if filter_analysis.variable_name:
                    placeholder_name = f"{filter_analysis.variable_name}_resolved"
                else:
                    placeholder_name = self._create_placeholder_name('timestamp')
                self._add_tolerance_metadata_from_analysis(placeholder_name, filter_analysis, template_context)
                replacement = f'{{{{ {placeholder_name} }}}}'
                log.info(f"Created tolerance placeholder '{placeholder_name}' for template '{template_expr}' in mixed content")
            else:
                # No tolerance - resolve directly
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

    def _is_our_placeholder(self, text: str) -> bool:
        """Check if text is one of our generated placeholders."""
        import re
        return bool(re.match(r'^\{\{\s*\w+_resolved\s*\}\}$', text.strip()))
    
    def _add_tolerance_metadata_from_analysis(self, placeholder_name: str, analysis: FilterAnalysis, template_context: Dict[str, Any]):
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
        
        # Apply format filter if present
        resolved_value = base_timestamp_value
        if analysis.has_format and resolved_value:
            try:
                # Apply format filter manually
                import datetime
                if isinstance(resolved_value, str):
                    # Parse timestamp string first
                    import dateutil.parser
                    dt = dateutil.parser.parse(resolved_value)
                elif hasattr(resolved_value, 'strftime'):
                    dt = resolved_value
                else:
                    dt = datetime.datetime.fromtimestamp(float(resolved_value))
                
                resolved_value = dt.strftime(analysis.format_string)
                log.debug(f"Applied format '{analysis.format_string}' to get '{resolved_value}'")
            except Exception as e:
                log.warning(f"Failed to apply format '{analysis.format_string}': {e}")
        
        # Create metadata
        metadata = {
            'raw_value': str(base_timestamp_value) if base_timestamp_value else analysis.original_template,
            'resolved_value': str(resolved_value) if resolved_value else analysis.original_template,
            'type': 'timestamp'
        }
        
        if analysis.tolerance_values:
            metadata['tolerance'] = list(analysis.tolerance_values)
        
        self.variable_registry._placeholder_metadata[placeholder_name] = metadata
        log.debug(f"Added tolerance metadata for '{placeholder_name}': {metadata}")
        
        # CLAUDE: Do NOT add tolerance placeholders to template context 
        # They should remain as placeholders for VM-side processing
        log.debug(f"CLAUDE: Skipping template context addition for tolerance placeholder '{placeholder_name}' (has tolerance)")
    
    def _resolve_template_with_context(self, template_string: str, template_context: Dict[str, Any]) -> str:
        """
        Resolve a Jinja2 template string using the provided template context.
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
    
    # Template Processing Methods (moved from PlaybookController)
    
    def resolve_action_variables(self, action, execution_context: Dict[str, Any]):
        """Resolve variables in action fields that support templating.
        
        Returns a copy of the action with variables resolved in applicable fields.
        """
        from adare.types.playbook import (
            CommandAction, KeyboardAction, ActionTestAction, SaveTimestampAction, DragAction
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