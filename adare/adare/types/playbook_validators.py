"""
Playbook Validation Module

Provides extensible validation framework for playbooks loaded from YAML files.
Validates variable usage, definitions, and other playbook constraints before
serialization to database.
"""

from __future__ import annotations
import re
from abc import ABC, abstractmethod
from typing import List, Set, Dict, Any, Optional
from dataclasses import dataclass, field
import attrs
import logging

from adare.types.playbook import (
    Playbook, ActionType, ClickAction, DragAction, KeyboardAction,
    CommandAction, SaveTimestampAction, PullAction, ActionTestAction,
    GotoAction, BlockAction, WaitUntilAction, Target,
    StopAction, ContinueAction
)

log = logging.getLogger(__name__)


@dataclass
class ValidationError:
    """Represents a validation error with context."""
    message: str
    action_index: Optional[int] = None
    action_type: Optional[str] = None
    field_name: Optional[str] = None
    variable_name: Optional[str] = None

    def __str__(self) -> str:
        parts = [f"Validation Error: {self.message}"]
        if self.action_index is not None:
            parts.append(f"at action index {self.action_index}")
        if self.action_type:
            parts.append(f"({self.action_type})")
        if self.field_name:
            parts.append(f"in field '{self.field_name}'")
        return " ".join(parts)


@dataclass
class ValidationResult:
    """Result of playbook validation."""
    errors: List[ValidationError] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)

    @property
    def is_valid(self) -> bool:
        """Check if validation passed (no errors)."""
        return len(self.errors) == 0

    def add_error(self, message: str, action_index: Optional[int] = None,
                  action_type: Optional[str] = None, field_name: Optional[str] = None,
                  variable_name: Optional[str] = None):
        """Add a validation error."""
        self.errors.append(ValidationError(
            message=message,
            action_index=action_index,
            action_type=action_type,
            field_name=field_name,
            variable_name=variable_name
        ))

    def add_warning(self, message: str):
        """Add a validation warning."""
        self.warnings.append(message)

    def merge(self, other: ValidationResult):
        """Merge another validation result into this one."""
        self.errors.extend(other.errors)
        self.warnings.extend(other.warnings)


class PlaybookValidator(ABC):
    """Base class for playbook validators."""

    @abstractmethod
    def validate(self, playbook: Playbook) -> ValidationResult:
        """
        Validate the playbook and return results.

        Args:
            playbook: Playbook to validate

        Returns:
            ValidationResult with errors and warnings
        """
        pass


class VariableUsageValidator(PlaybookValidator):
    """Extracts all variable references from playbook actions."""

    # Pattern to match {{variable_name}} with optional filters
    VARIABLE_PATTERN = re.compile(r'\{\{\s*(\w+)(?:\s*\|[^}]*)?\s*\}\}')

    def validate(self, playbook: Playbook) -> ValidationResult:
        """
        Extract all variable references from the playbook.

        This validator doesn't produce errors itself, but collects
        variable usage information for other validators.
        """
        result = ValidationResult()
        self.variable_references = self._extract_all_references(playbook)
        log.debug(f"Found variable references: {self.variable_references}")
        return result

    def _extract_all_references(self, playbook: Playbook) -> Dict[str, List[tuple]]:
        """
        Extract all variable references from playbook.

        Returns:
            Dict mapping variable names to list of (action_index, action_type, field_name) tuples
        """
        references: Dict[str, List[tuple]] = {}

        for idx, action in enumerate(playbook.actions):
            action_type = action.__class__.__name__
            action_refs = self._extract_from_action(action, idx, action_type)

            for var_name, locations in action_refs.items():
                if var_name not in references:
                    references[var_name] = []
                references[var_name].extend(locations)

        return references

    def _extract_from_action(self, action: ActionType, action_index: int,
                            action_type: str) -> Dict[str, List[tuple]]:
        """Extract variable references from a single action."""
        references: Dict[str, List[tuple]] = {}

        # Check description (common to all actions)
        if hasattr(action, 'description') and action.description:
            self._extract_from_string(action.description, 'description',
                                     action_index, action_type, references)

        # Check target fields (ClickAction, GotoAction, etc.)
        if hasattr(action, 'target') and action.target:
            self._extract_from_target(action.target, 'target',
                                     action_index, action_type, references)

        # Check drag action src/dst targets
        if isinstance(action, DragAction):
            if action.src:
                self._extract_from_target(action.src, 'src',
                                         action_index, action_type, references)
            if action.dst:
                self._extract_from_target(action.dst, 'dst',
                                         action_index, action_type, references)

        # Check keyboard text
        if isinstance(action, KeyboardAction) and action.text:
            self._extract_from_string(action.text, 'text',
                                     action_index, action_type, references)

        # Check command fields
        if isinstance(action, CommandAction):
            if action.command:
                self._extract_from_string(action.command, 'command',
                                         action_index, action_type, references)
            if action.cwd:
                self._extract_from_string(action.cwd, 'cwd',
                                         action_index, action_type, references)
            if action.env:
                for key, value in action.env.items():
                    self._extract_from_string(str(value), f'env.{key}',
                                             action_index, action_type, references)

        # Check pull action paths
        if isinstance(action, PullAction):
            if action.src:
                # Handle both string and list of strings
                if isinstance(action.src, list):
                    for src_item in action.src:
                        self._extract_from_string(src_item, 'src',
                                                 action_index, action_type, references)
                else:
                    self._extract_from_string(action.src, 'src',
                                             action_index, action_type, references)
            if action.dst:
                self._extract_from_string(action.dst, 'dst',
                                         action_index, action_type, references)

        # Check test name
        if isinstance(action, ActionTestAction) and action.name:
            self._extract_from_string(action.name, 'name',
                                     action_index, action_type, references)

        # Check block actions recursively
        if isinstance(action, BlockAction):
            for nested_idx, nested_action in enumerate(action.actions):
                nested_type = nested_action.__class__.__name__
                nested_refs = self._extract_from_action(
                    nested_action, action_index, f"{action_type}.block[{nested_idx}]"
                )
                for var_name, locations in nested_refs.items():
                    if var_name not in references:
                        references[var_name] = []
                    references[var_name].extend(locations)

        # Check WaitUntilAction condition targets
        if isinstance(action, WaitUntilAction):
            self._extract_from_wait_condition(action.condition, 'condition',
                                             action_index, action_type, references)

        # Check StopAction and ContinueAction conditions
        if isinstance(action, (StopAction, ContinueAction)) and action.condition:
            # Variable condition references the variable being tested
            var_name = action.condition.variable
            if var_name not in references:
                references[var_name] = []
            references[var_name].append((action_index, action_type, 'condition.variable'))

        return references

    def _extract_from_target(self, target: Target, field_prefix: str,
                            action_index: int, action_type: str,
                            references: Dict[str, List[tuple]]):
        """Extract variables from Target object."""
        if target.text:
            self._extract_from_string(target.text, f'{field_prefix}.text',
                                     action_index, action_type, references)
        if target.image:
            self._extract_from_string(target.image, f'{field_prefix}.image',
                                     action_index, action_type, references)

    def _extract_from_wait_condition(self, condition, field_prefix: str,
                                    action_index: int, action_type: str,
                                    references: Dict[str, List[tuple]]):
        """Extract variables from WaitCondition recursively."""
        if condition.exists:
            self._extract_from_target(condition.exists, f'{field_prefix}.exists',
                                     action_index, action_type, references)
        elif condition.not_exists:
            self._extract_from_target(condition.not_exists, f'{field_prefix}.not_exists',
                                     action_index, action_type, references)
        elif condition.all:
            for idx, subcond in enumerate(condition.all):
                self._extract_from_wait_condition(subcond, f'{field_prefix}.all[{idx}]',
                                                 action_index, action_type, references)
        elif condition.any:
            for idx, subcond in enumerate(condition.any):
                self._extract_from_wait_condition(subcond, f'{field_prefix}.any[{idx}]',
                                                 action_index, action_type, references)
        elif condition.negate:
            self._extract_from_wait_condition(condition.negate, f'{field_prefix}.negate',
                                             action_index, action_type, references)

    def _extract_from_string(self, text: str, field_name: str,
                           action_index: int, action_type: str,
                           references: Dict[str, List[tuple]]):
        """Extract variable names from string using regex pattern."""
        matches = self.VARIABLE_PATTERN.findall(text)
        for var_name in matches:
            if var_name not in references:
                references[var_name] = []
            references[var_name].append((action_index, action_type, field_name))


class FilterValidator(PlaybookValidator):
    """Validates that filters used on variables are valid for their types."""

    # Map variable types to their allowed filters
    TYPE_FILTERS = {
        'TIMESTAMP': {'timezone', 'format', 'tolerance', 'localtime'},
        'STRING': set(),
        'REGEX': set(),
        'PATH': set(),
        'INTEGER': set(),
        'FLOAT': set(),
        'BOOLEAN': set(),
        'LIST': set(),
        'DICT': set(),
    }

    # Pattern to extract filter names from filter chain: | filter_name(...) or | filter_name
    FILTER_PATTERN = re.compile(r'\|\s*(\w+)(?:\s*\([^)]*\))?')

    def __init__(self, usage_validator: VariableUsageValidator):
        """
        Initialize validator.

        Args:
            usage_validator: VariableUsageValidator to get variable references from
        """
        self.usage_validator = usage_validator

    def validate(self, playbook: Playbook) -> ValidationResult:
        """
        Validate that filters used on variables match their types.

        Checks:
        1. Filters are known/valid
        2. Filters are compatible with variable type
        """
        result = ValidationResult()

        # Get variable types from playbook
        variable_types = self._get_variable_types(playbook)
        log.debug(f"Variable types: {variable_types}")

        # Check filters for each variable reference
        for var_name, locations in self.usage_validator.variable_references.items():
            var_type = variable_types.get(var_name)
            if not var_type:
                # Variable not defined - VariableDefinitionValidator will catch this
                continue

            # Extract and validate filters for this variable
            for action_index, action_type, field_name in locations:
                filters = self._extract_filters_from_action(
                    playbook, action_index, field_name, var_name
                )

                for filter_name in filters:
                    # Check if filter is valid for this variable type
                    allowed_filters = self.TYPE_FILTERS.get(var_type, set())

                    if filter_name not in allowed_filters:
                        # Check if filter is completely unknown
                        all_known_filters = set()
                        for filters_set in self.TYPE_FILTERS.values():
                            all_known_filters.update(filters_set)

                        if filter_name not in all_known_filters:
                            result.add_error(
                                message=f"Unknown filter '{filter_name}' used on variable '{var_name}'",
                                action_index=action_index,
                                action_type=action_type,
                                field_name=field_name,
                                variable_name=var_name
                            )
                        else:
                            result.add_error(
                                message=f"Filter '{filter_name}' cannot be used on {var_type} variable '{var_name}'. "
                                       f"Valid filters for {var_type}: {', '.join(sorted(allowed_filters)) if allowed_filters else 'none'}",
                                action_index=action_index,
                                action_type=action_type,
                                field_name=field_name,
                                variable_name=var_name
                            )

        return result

    def _get_variable_types(self, playbook: Playbook) -> Dict[str, str]:
        """
        Get mapping of variable names to their types.

        Returns:
            Dict mapping variable name to type string (e.g., 'TIMESTAMP', 'STRING')
        """
        types = {}

        # Get types from variables section
        if playbook.variables:
            for var_name, variable in playbook.variables.variables.items():
                types[var_name] = variable.type.name

        # Automatic variables are all PATH or STRING types
        # Most are PATH, but some are STRING
        automatic_vars = {
            'adare_user_home': 'PATH',
            'adare_username': 'STRING',
            'adare_user_documents': 'PATH',
            'adare_user_desktop': 'PATH',
            'adare_user_downloads': 'PATH',
            'adare_os': 'STRING',
            'adare_temp_dir': 'PATH',
            'adare_system_drive': 'PATH',
            'adare_root_dir': 'PATH',
            'adare_shared': 'PATH',
            'adare_shared_tools': 'PATH',
            'adare_shared_data': 'PATH',
            'adare_run_dir': 'PATH',
        }
        types.update(automatic_vars)

        # Variables created by save_timestamp are TIMESTAMP type
        for action in playbook.actions:
            if isinstance(action, SaveTimestampAction):
                var_name = self._extract_variable_name(action.variable)
                if var_name:
                    types[var_name] = 'TIMESTAMP'

            # Variables created by command capture use auto-inference (STRING by default)
            # We can't statically determine their type, so mark as STRING
            if isinstance(action, CommandAction) and action.capture:
                var_name = self._extract_variable_name(action.capture.variable)
                if var_name:
                    # Default to STRING for captured command output
                    # The actual type will be determined at runtime
                    types[var_name] = 'STRING'

            # Check nested actions in blocks
            if isinstance(action, BlockAction):
                types.update(self._get_types_from_block(action))

        return types

    def _get_types_from_block(self, block_action: BlockAction) -> Dict[str, str]:
        """Get variable types from block actions."""
        types = {}
        for action in block_action.actions:
            if isinstance(action, SaveTimestampAction):
                var_name = self._extract_variable_name(action.variable)
                if var_name:
                    types[var_name] = 'TIMESTAMP'
            if isinstance(action, CommandAction) and action.capture:
                var_name = self._extract_variable_name(action.capture.variable)
                if var_name:
                    types[var_name] = 'STRING'
            if isinstance(action, BlockAction):
                types.update(self._get_types_from_block(action))
        return types

    def _extract_variable_name(self, variable_field: str) -> Optional[str]:
        """Extract variable name from save_timestamp variable field."""
        if not variable_field:
            return None
        # If it contains templates, we can't statically determine the name
        if '{{' in variable_field and '}}' in variable_field:
            return None
        return variable_field

    def _extract_filters_from_action(self, playbook: Playbook, action_index: int,
                                     field_name: str, var_name: str) -> List[str]:
        """
        Extract filter names used on a specific variable in a specific action field.

        Returns:
            List of filter names (e.g., ['format', 'tolerance'])
        """
        action = playbook.actions[action_index]

        # Get the string value for the field
        field_value = self._get_field_value(action, field_name)
        if not field_value:
            return []

        # Find variable references with this name in the field value
        # Pattern: {{var_name | filter1 | filter2(...)}}
        var_pattern = re.compile(
            r'\{\{\s*' + re.escape(var_name) + r'\s*(\|[^}]*)?\s*\}\}'
        )

        filters = []
        for match in var_pattern.finditer(field_value):
            filter_chain = match.group(1)  # The | filter1 | filter2 part
            if filter_chain:
                # Extract individual filter names
                filter_matches = self.FILTER_PATTERN.findall(filter_chain)
                filters.extend(filter_matches)

        return filters

    def _get_field_value(self, action: ActionType, field_name: str) -> Optional[str]:
        """Get string value of a field from an action."""
        # Handle nested field names like 'target.text', 'env.PATH', etc.
        parts = field_name.split('.')

        current = action
        for part in parts:
            # Handle array indexing in field names like 'block[0]'
            if '[' in part:
                # For now, skip array indexing in blocks
                # This would require more complex traversal
                return None

            if not hasattr(current, part):
                return None
            current = getattr(current, part)

        return str(current) if current is not None else None


class DuplicateVariableValidator(PlaybookValidator):
    """Validates that variable names are not duplicated."""

    def validate(self, playbook: Playbook) -> ValidationResult:
        """
        Validate that variable names are unique across all sources.

        Checks:
        1. No duplicate variable definitions in the variables section
        2. save_timestamp actions don't create variables that already exist
        3. Multiple save_timestamp actions don't use the same variable name
        """
        result = ValidationResult()

        # Track all variable definitions with their sources
        variable_sources: Dict[str, List[tuple]] = {}  # var_name -> [(source, location)]

        # Check variables section (note: YAML will already merge duplicates,
        # but we can detect if someone redefines a variable)
        if playbook.variables:
            for var_name in playbook.variables.variables.keys():
                if var_name not in variable_sources:
                    variable_sources[var_name] = []
                variable_sources[var_name].append(('variables_section', None, None))

        # Check save_timestamp actions
        self._collect_save_timestamp_variables(
            playbook.actions, variable_sources
        )

        # Find duplicates - warn but don't error (later definition wins)
        for var_name, sources in variable_sources.items():
            if len(sources) > 1:
                # Report duplicate definitions as warnings
                source_descriptions = []
                for source_type, action_idx, action_type in sources:
                    if source_type == 'variables_section':
                        source_descriptions.append("variables section")
                    elif source_type == 'save_timestamp':
                        source_descriptions.append(
                            f"save_timestamp at action index {action_idx} ({action_type})"
                        )
                    elif source_type == 'command_capture':
                        source_descriptions.append(
                            f"command capture at action index {action_idx} ({action_type})"
                        )

                # Check if it's an automatic variable being overridden
                if self._is_automatic_variable(var_name):
                    result.add_warning(
                        f"Variable '{var_name}' is defined multiple times: "
                        f"{', '.join(source_descriptions)}. "
                        f"This overrides an automatic variable. The later definition will be used."
                    )
                else:
                    result.add_warning(
                        f"Variable '{var_name}' is defined multiple times: "
                        f"{', '.join(source_descriptions)}. "
                        f"The later definition will be used."
                    )

        return result

    def _collect_save_timestamp_variables(
        self,
        actions: List[ActionType],
        variable_sources: Dict[str, List[tuple]],
        action_offset: int = 0
    ) -> None:
        """
        Collect variable names from save_timestamp and command capture actions recursively.

        Args:
            actions: List of actions to scan
            variable_sources: Dict to populate with variable sources
            action_offset: Offset for action indices (for nested blocks)
        """
        for idx, action in enumerate(actions):
            action_index = action_offset + idx

            if isinstance(action, SaveTimestampAction):
                var_name = self._extract_variable_name(action.variable)
                if var_name:
                    if var_name not in variable_sources:
                        variable_sources[var_name] = []
                    variable_sources[var_name].append((
                        'save_timestamp',
                        action_index,
                        action.__class__.__name__
                    ))

            # Check command capture actions
            if isinstance(action, CommandAction) and action.capture:
                var_name = self._extract_variable_name(action.capture.variable)
                if var_name:
                    if var_name not in variable_sources:
                        variable_sources[var_name] = []
                    variable_sources[var_name].append((
                        'command_capture',
                        action_index,
                        action.__class__.__name__
                    ))

            # Recursively check block actions
            if isinstance(action, BlockAction):
                self._collect_save_timestamp_variables(
                    action.actions,
                    variable_sources,
                    action_offset=action_index
                )

    def _extract_variable_name(self, variable_field: str) -> Optional[str]:
        """Extract variable name from save_timestamp variable field."""
        if not variable_field:
            return None
        # If it contains templates, we can't statically determine the name
        if '{{' in variable_field and '}}' in variable_field:
            return None
        return variable_field

    def _is_automatic_variable(self, var_name: str) -> bool:
        """Check if a variable name is an automatic variable."""
        automatic_vars = {
            'adare_user_home',
            'adare_username',
            'adare_user_documents',
            'adare_user_desktop',
            'adare_user_downloads',
            'adare_os',
            'adare_temp_dir',
            'adare_system_drive',
            'adare_root_dir',
            'adare_shared',
            'adare_shared_tools',
            'adare_shared_data',
            'adare_run_dir',
        }
        return var_name in automatic_vars


class VariableDefinitionValidator(PlaybookValidator):
    """Validates that all referenced variables are defined."""

    def __init__(self, usage_validator: VariableUsageValidator):
        """
        Initialize validator.

        Args:
            usage_validator: VariableUsageValidator to get variable references from
        """
        self.usage_validator = usage_validator

    def validate(self, playbook: Playbook) -> ValidationResult:
        """
        Validate that all referenced variables are defined.

        Variables can be defined in:
        1. The 'variables' section of the playbook
        2. SaveTimestampAction actions (create variables at runtime)
        """
        result = ValidationResult()

        # Collect defined variables
        defined_vars = self._collect_defined_variables(playbook)
        log.debug(f"Defined variables: {defined_vars}")

        # Check each referenced variable
        for var_name, locations in self.usage_validator.variable_references.items():
            if var_name not in defined_vars:
                # Variable is used but not defined
                for action_index, action_type, field_name in locations:
                    result.add_error(
                        message=f"Variable '{var_name}' is used but not defined",
                        action_index=action_index,
                        action_type=action_type,
                        field_name=field_name,
                        variable_name=var_name
                    )

        return result

    def _collect_defined_variables(self, playbook: Playbook) -> Set[str]:
        """
        Collect all defined variable names.

        Returns:
            Set of variable names that are defined
        """
        defined = set()

        # Variables from the 'variables' section
        if playbook.variables:
            defined.update(playbook.variables.variables.keys())

        # Automatic variables (always available)
        defined.update(self._get_automatic_variable_names())

        # Variables created by save_timestamp actions
        for action in playbook.actions:
            if isinstance(action, SaveTimestampAction):
                # Extract variable name (might contain templates)
                var_name = self._extract_variable_name(action.variable)
                if var_name:
                    defined.add(var_name)

            # Variables created by command capture
            if isinstance(action, CommandAction) and action.capture:
                var_name = self._extract_variable_name(action.capture.variable)
                if var_name:
                    defined.add(var_name)

            # Check nested actions in blocks
            if isinstance(action, BlockAction):
                defined.update(self._collect_from_block(action))

        return defined

    def _get_automatic_variable_names(self) -> Set[str]:
        """
        Get names of automatic variables that are always available.

        These are defined in adarelib.common.automatic_variables.AutomaticVariables.

        Returns:
            Set of automatic variable names
        """
        return {
            # User-related automatic variables
            'adare_user_home',
            'adare_username',
            'adare_user_documents',
            'adare_user_desktop',
            'adare_user_downloads',
            # System-related automatic variables
            'adare_os',
            'adare_temp_dir',
            'adare_system_drive',  # Windows only
            'adare_root_dir',      # Linux only
            # Shared mount variables
            'adare_shared',
            'adare_shared_tools',
            'adare_shared_data',
            'adare_run_dir',
        }

    def _collect_from_block(self, block_action: BlockAction) -> Set[str]:
        """Collect variables defined within a block action."""
        defined = set()
        for action in block_action.actions:
            if isinstance(action, SaveTimestampAction):
                var_name = self._extract_variable_name(action.variable)
                if var_name:
                    defined.add(var_name)
            if isinstance(action, CommandAction) and action.capture:
                var_name = self._extract_variable_name(action.capture.variable)
                if var_name:
                    defined.add(var_name)
            if isinstance(action, BlockAction):
                defined.update(self._collect_from_block(action))
        return defined

    def _extract_variable_name(self, variable_field: str) -> Optional[str]:
        """
        Extract base variable name from save_timestamp variable field.

        Handles cases like:
        - "my_timestamp" -> "my_timestamp"
        - "{{prefix}}_timestamp" -> None (contains templates, will be resolved at runtime)

        Returns:
            Variable name if it's a simple string, None if it contains templates
        """
        if not variable_field:
            return None

        # If it contains templates, we can't statically determine the name
        if '{{' in variable_field and '}}' in variable_field:
            return None

        return variable_field


def validate_playbook(playbook: Playbook) -> None:
    """
    Validate playbook and raise ValueError if validation fails.

    Args:
        playbook: Playbook to validate

    Raises:
        ValueError: If validation fails with detailed error messages
    """
    # Run all validators
    usage_validator = VariableUsageValidator()
    duplicate_validator = DuplicateVariableValidator()
    definition_validator = VariableDefinitionValidator(usage_validator)
    filter_validator = FilterValidator(usage_validator)

    validators = [
        usage_validator,
        duplicate_validator,  # Check for duplicates before checking definitions
        definition_validator,
        filter_validator,
    ]

    # Collect all validation results
    combined_result = ValidationResult()
    for validator in validators:
        result = validator.validate(playbook)
        combined_result.merge(result)

    # Log warnings
    for warning in combined_result.warnings:
        log.warning(f"Playbook validation warning: {warning}")

    # Raise error if validation failed
    if not combined_result.is_valid:
        error_messages = [str(error) for error in combined_result.errors]
        error_summary = "\n".join(error_messages)
        raise ValueError(f"Playbook validation failed:\n{error_summary}")

    log.info(f"Playbook validation passed ({len(combined_result.warnings)} warnings)")
