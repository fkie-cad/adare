"""Convert YAML custom tags in test data (``!re``, ``!timestamp``) into placeholders.

The test compares a tagged value by type (regex match, timestamp within a
tolerance or interval), so the host replaces the tag with ``{{ name_resolved }}``
and records how to compare it in the placeholder metadata (see ``placeholders``).
A ``!timestamp`` without tolerance or interval is just a value and is resolved.
"""

import logging
from collections.abc import Callable
from typing import Any

from adare.backend.experiment.placeholders import MetadataManager, ToleranceDetector
from adare.backend.experiment.timestamp_interval import tag_metadata

log = logging.getLogger(__name__)

TemplateResolver = Callable[[str, dict[str, Any]], str]


class YamlTagProcessor:
    """Processes YAML custom tags by converting them to variable placeholders."""

    def __init__(self, metadata_manager: MetadataManager, tolerance_detector: ToleranceDetector):
        """
        Initialize YAML tag processor.

        Args:
            metadata_manager: MetadataManager instance for storing metadata
            tolerance_detector: ToleranceDetector instance for analyzing tolerance
        """
        self.metadata_manager = metadata_manager
        self.tolerance_detector = tolerance_detector
        self._placeholder_counter = 0
        self._names_in_use: set[str] = set()

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
        self._names_in_use.add(placeholder_name)
        return placeholder_name

    def process_yaml_tags(
        self,
        data: Any,
        template_context: dict[str, Any] | None = None,
        template_resolver: TemplateResolver | None = None,
    ) -> Any:
        """Replace every tag anywhere in ``data`` (mappings and lists at any depth); returns a new structure."""
        self._names_in_use = set()  # placeholder names only need to be unique within one test
        return self._process(data, template_context, template_resolver)

    def _process(self, data: Any, template_context: dict[str, Any] | None, template_resolver) -> Any:
        from adarelib.testset.yaml.customtags import YamlRegexString, YamlTimestamp

        if isinstance(data, dict):
            return {key: self._process(value, template_context, template_resolver) for key, value in data.items()}
        if isinstance(data, list):
            return [self._process(item, template_context, template_resolver) for item in data]
        if isinstance(data, YamlRegexString):
            placeholder_name = self.create_placeholder_name('regex')
            self.metadata_manager.add_regex_metadata(placeholder_name, data.string, template_context)
            log.debug(f"Converted !re '{data.string}' to placeholder '{placeholder_name}'")
            return f'{{{{ {placeholder_name} }}}}'
        if isinstance(data, YamlTimestamp):
            return self._convert_timestamp(data, template_context, template_resolver)
        return data

    def _convert_timestamp(self, tag, template_context: dict[str, Any] | None, template_resolver) -> Any:
        value = tag.string
        if not self.tolerance_detector.has_yaml_tolerance(tag):
            # Compared exactly: the tag is just a value.
            return _render(value, template_context, template_resolver, keep_unset=False)

        resolved = _render(value, template_context, template_resolver, keep_unset=True)
        placeholder_name = self._timestamp_placeholder_name(value)
        self.metadata_manager.add_timestamp_metadata(
            placeholder_name,
            resolved,
            tag.tolerance,
            template_context,
            tag_metadata(tag, template_resolver, template_context),
        )
        log.debug(f"Converted !timestamp '{value}' to placeholder '{placeholder_name}' (value '{resolved}')")
        return f'{{{{ {placeholder_name} }}}}'

    def _timestamp_placeholder_name(self, value: Any) -> str:
        """``<variable>_resolved`` for a templated timestamp (readable in reports), else a numbered name."""
        variable = (
            self.tolerance_detector.analyze_jinja_template(str(value)).variable_name if _is_template(value) else None
        )
        name = f'{variable}_resolved' if variable else None
        if name is None or name in self._names_in_use:
            return self.create_placeholder_name('timestamp')
        self._names_in_use.add(name)
        return name


def _is_template(value: Any) -> bool:
    return '{{' in str(value) and '}}' in str(value)


def _render(value: Any, template_context: dict[str, Any] | None, template_resolver, keep_unset: bool) -> Any:
    """Resolve a templated value; with ``keep_unset``, an empty result keeps the template.

    Empty means the variable is only set later in the run (``save_timestamp``); the
    test is resolved again with the runtime context then.
    """
    if not _is_template(value) or not (template_resolver and template_context):
        return value
    rendered = template_resolver(value, template_context)
    if keep_unset and (not rendered or rendered.isspace()):
        return value
    return rendered
