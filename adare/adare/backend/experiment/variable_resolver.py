"""
Variable Resolver

Turns test data and playbook actions into what runs: YAML custom tags and filtered
templates become placeholders with metadata (see ``placeholders``), plain templates
are resolved against the execution context.
"""

import copy
import logging
from typing import Any

import jinja2

from adare.backend.experiment.jinja_template_resolver import JinjaTemplateResolver
from adare.backend.experiment.placeholders import MetadataManager, ToleranceDetector
from adare.backend.experiment.yaml_tag_processor import YamlTagProcessor

log = logging.getLogger(__name__)


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
        self._jinja_resolver = JinjaTemplateResolver(
            jinja_env, self._tolerance_detector, self._metadata_manager, self._yaml_tag_processor
        )

    def process_data(self, data: dict[str, Any], template_context: dict[str, Any] = None) -> dict[str, Any]:
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
        data = self._yaml_tag_processor.process_yaml_tags(
            data, template_context, self._jinja_resolver.resolve_template_with_context
        )

        # Phase 2: Process Jinja2 templates with filter analysis
        if template_context and self.jinja_env:
            data = self._jinja_resolver.process_jinja_templates(data, self._current_template_context)

        return data

    def get_placeholder_metadata(self) -> dict[str, Any]:
        """
        Get all placeholder metadata created during processing.

        Returns:
            Dictionary of placeholder metadata
        """
        return self._metadata_manager.get_placeholder_metadata()

    # Template Processing Methods (moved from PlaybookController)

    def resolve_action_variables(self, action, execution_context: dict[str, Any]):
        """Resolve variables in action fields that support templating.

        Returns a copy of the action with variables resolved in applicable fields.
        """
        from adare.types.playbook import DragAction

        resolved_action = copy.deepcopy(action)

        for field in ('description', *_templated_fields(action)):
            value = getattr(resolved_action, field, None)
            if value:
                setattr(resolved_action, field, self._resolve_field(value, execution_context))

        if getattr(resolved_action, 'target', None):
            resolved_action.target = self.resolve_target_variables(resolved_action.target, execution_context)

        # ClickAction.verify keeps its Target inside a small exists/not_exists holder.
        click_verify = getattr(resolved_action, 'verify', None)
        if click_verify is not None:
            if click_verify.exists is not None:
                click_verify.exists = self.resolve_target_variables(click_verify.exists, execution_context)
            if click_verify.not_exists is not None:
                click_verify.not_exists = self.resolve_target_variables(click_verify.not_exists, execution_context)

        # WaitUntilAction keeps its Targets inside a recursive `condition` tree rather than
        # a flat `target` attribute, so the branch above never reached them and the guest
        # was asked to wait for a literal "{{ filename }}".
        if getattr(resolved_action, 'condition', None):
            resolved_action.condition = self._resolve_condition_variables(resolved_action.condition, execution_context)

        # DragAction's src/dst are Targets (PullAction's are paths, handled above).
        if isinstance(action, DragAction):
            if resolved_action.src:
                resolved_action.src = self.resolve_target_variables(resolved_action.src, execution_context)
            if resolved_action.dst:
                resolved_action.dst = self.resolve_target_variables(resolved_action.dst, execution_context)

        return resolved_action

    def _resolve_field(self, value: Any, execution_context: dict[str, Any]) -> Any:
        """Resolve a templated action field: a string, a list of strings (PullAction.src) or env values."""
        # replace_variables on a list would be a silent no-op ('{{' in <list> tests element
        # equality, not substrings), so the guest would get literal "{{ out_dir }}/..." paths.
        if isinstance(value, list):
            return [self.replace_variables(entry, execution_context) for entry in value]
        if isinstance(value, dict):
            return {key: self.replace_variables(str(entry), execution_context) for key, entry in value.items()}
        return self.replace_variables(value, execution_context)

    def _resolve_condition_variables(self, condition, execution_context: dict[str, Any]):
        """Resolve variables in a WaitCondition tree, in place on an already-copied action.

        WaitCondition is recursive: `exists`/`not_exists` hold Targets, while
        `all`/`any`/`negate` hold nested conditions. Exactly one field is set (enforced by
        WaitCondition.__attrs_post_init__), so each branch is mutually exclusive.
        """
        if getattr(condition, 'exists', None):
            condition.exists = self.resolve_target_variables(condition.exists, execution_context)
        if getattr(condition, 'not_exists', None):
            condition.not_exists = self.resolve_target_variables(condition.not_exists, execution_context)
        for group in ('all', 'any'):
            nested = getattr(condition, group, None)
            if nested:
                setattr(
                    condition, group, [self._resolve_condition_variables(child, execution_context) for child in nested]
                )
        if getattr(condition, 'negate', None):
            condition.negate = self._resolve_condition_variables(condition.negate, execution_context)
        return condition

    def resolve_target_variables(self, target, execution_context: dict[str, Any]):
        """Resolve variables in Target fields."""
        resolved_target = copy.deepcopy(target)

        if resolved_target.image:
            resolved_target.image = self.replace_variables(resolved_target.image, execution_context)
        if resolved_target.text:
            resolved_target.text = self.replace_variables(resolved_target.text, execution_context)

        return resolved_target

    def _is_raw_string_literal(self, text: str) -> bool:
        """Check if text is a Python-style raw string literal (e.g. r"..." or r'...')."""
        if not text:
            return False

        # Check for r"..." prefix/suffix
        if text.startswith('r"') and text.endswith('"') and len(text) >= 3:
            return True

        # Check for r'...' prefix/suffix
        return bool(text.startswith("r'") and text.endswith("'") and len(text) >= 3)

    def replace_variables(self, text: str, execution_context: dict[str, Any]) -> str:
        """Replace Jinja2 template variables in text with values or metadata placeholders.

        Variables with metadata are resolved to placeholders (e.g., VARTIMESTAMP_RESOLVED)
        and the metadata is captured for server-side processing.

        Raises:
            jinja2.UndefinedError: If a referenced variable is not defined in the context
        """
        if not text or '{{' not in text:
            return text

        result = text

        # Handle Python-style raw string literals commonly used in playbooks
        # e.g., r"C:\Path\To\File" -> C:\Path\To\File
        if self._is_raw_string_literal(result):
            # Strip the r" or r' prefix and corresponding suffix
            stripped = result[2:-1]
            log.debug(f"Detected raw string literal: '{result}' -> '{stripped}'")
            result = stripped

        max_iterations = 10  # Prevent infinite loops
        previous_results = set()  # Track previous results to detect cycles

        for _ in range(max_iterations):
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

            # Perform template replacement with StrictUndefined to catch missing variables
            log.debug(f"Processing template: '{result}' with context keys: {list(formatted_context.keys())}")

            # Use StrictUndefined to raise error on missing variables
            env = jinja2.Environment(undefined=jinja2.StrictUndefined)

            # Add custom filters for metadata capture
            env.filters.update(self.get_custom_filters())

            template = env.from_string(result)
            new_result = template.render(formatted_context)
            log.debug(f"Template result: '{new_result}'")

            # If no change occurred, break to avoid infinite loops
            if new_result == result:
                break

            result = new_result

        else:
            if '{{' in result:
                log.warning(f"Variable replacement hit max iterations for: {text}")

        return result

    def get_formatted_context(
        self, execution_context: dict[str, Any] = None, for_tests: bool = False
    ) -> dict[str, Any]:
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

    def get_custom_filters(self) -> dict[str, Any]:
        """Get custom Jinja2 filters from variable registry metadata."""
        # Get filters from variable registry if available
        if hasattr(self, 'variable_registry') and self.variable_registry:
            registry_filters = self.variable_registry.get_all_jinja_filters()
            if registry_filters:
                log.debug(
                    f"Using {len(registry_filters)} filters from variable registry: {list(registry_filters.keys())}"
                )
                return registry_filters

        # Fallback to empty dict - no custom filters available
        log.debug("No variable registry filters available, using no custom filters")
        return {}


def _templated_fields(action) -> tuple[str, ...]:
    """The fields of an action, beside ``description``, that may contain templates."""
    from adare.types.playbook import ActionTestAction, CommandAction, KeyboardAction, PullAction, SaveTimestampAction

    fields = {
        CommandAction: ('command', 'cwd', 'env'),
        KeyboardAction: ('text',),
        ActionTestAction: ('name',),
        SaveTimestampAction: ('variable',),
        PullAction: ('src', 'dst'),
    }
    return next((names for cls, names in fields.items() if isinstance(action, cls)), ())
