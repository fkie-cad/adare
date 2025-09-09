"""
Variable Resolver

Handles conversion of YAML custom tags to variable placeholders for VM processing.
This module provides clean separation between execution logic and variable resolution.
"""

from typing import Dict, Any, List, Optional, Tuple
import logging
import re
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
            data = self._process_jinja_templates(data, template_context)
        
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
                
                if has_tolerance:
                    # Has tolerance - create placeholder
                    placeholder_name = self._create_placeholder_name('timestamp')
                    
                    # Resolve any templates within the timestamp value
                    timestamp_value = item.string
                    if '{{' in str(timestamp_value) and '}}' in str(timestamp_value):
                        if hasattr(self, '_current_template_context'):
                            resolved_timestamp = self._resolve_template_with_context(timestamp_value, self._current_template_context)
                        else:
                            resolved_timestamp = timestamp_value
                        log.debug(f"Resolved timestamp template '{timestamp_value}' to '{resolved_timestamp}'")
                    else:
                        resolved_timestamp = timestamp_value
                    
                    self._add_timestamp_metadata(placeholder_name, resolved_timestamp, getattr(item, 'tolerance', None))
                    processed_list.append(f'{{{{ {placeholder_name} }}}}')
                    log.info(f"Converted YamlTimestamp with tolerance to placeholder '{placeholder_name}'")
                    has_changes = True
                else:
                    # No tolerance - resolve directly
                    timestamp_value = item.string
                    if '{{' in str(timestamp_value) and '}}' in str(timestamp_value):
                        if hasattr(self, '_current_template_context'):
                            resolved_timestamp = self._resolve_template_with_context(timestamp_value, self._current_template_context)
                        else:
                            resolved_timestamp = timestamp_value
                        log.info(f"Resolved YamlTimestamp '{timestamp_value}' to '{resolved_timestamp}'")
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
        
        if tolerance is not None:
            metadata['tolerance'] = tolerance
        
        self.variable_registry._placeholder_metadata[placeholder_name] = metadata
        log.debug(f"Added timestamp metadata for '{placeholder_name}': value='{timestamp_value}', tolerance={tolerance}")
    
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
            
            # Analyze what filters are being applied
            filter_analysis = self._tolerance_detector.analyze_jinja_template(data)
            
            if filter_analysis.has_tolerance:
                # Has tolerance - create placeholder + metadata
                placeholder_name = self._create_placeholder_name('timestamp')
                self._add_tolerance_metadata_from_analysis(placeholder_name, filter_analysis, template_context)
                result = f'{{{{ {placeholder_name} }}}}'
                log.info(f"Created tolerance placeholder '{placeholder_name}' for template '{data}'")
                return result
            else:
                # No tolerance - can resolve directly
                try:
                    template = self.jinja_env.from_string(data)
                    resolved_value = template.render(template_context)
                    log.info(f"Resolved template '{data}' to '{resolved_value}'")
                    return resolved_value
                except Exception as e:
                    log.warning(f"Failed to resolve template '{data}': {e}")
                    return data
                    
        elif isinstance(data, dict):
            return {key: self._process_jinja_templates(value, template_context) 
                    for key, value in data.items()}
        elif isinstance(data, list):
            return [self._process_jinja_templates(item, template_context) 
                    for item in data]
        
        return data
    
    def _is_our_placeholder(self, text: str) -> bool:
        """Check if text is one of our generated placeholders."""
        import re
        return bool(re.match(r'^\{\{\s*(regex|timestamp)_\d+_resolved\s*\}\}$', text.strip()))
    
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