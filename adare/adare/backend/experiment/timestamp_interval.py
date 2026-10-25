"""Host-side resolution of ``!timestamp {after: ..., before: ...}`` bounds.

The bounds are usually ``save_timestamp`` variables, which only get a value
during the run; until then a bound stays a template and is resolved again when
the test is re-processed with the runtime context (see TestLoader).
"""

from collections.abc import Callable
from typing import Any


def resolve_interval_bounds(
    yaml_metadata: dict[str, Any],
    template_resolver: Callable[[str, dict[str, Any]], str] | None,
    template_context: dict[str, Any] | None,
) -> dict[str, Any]:
    """Return a copy of a timestamp tag's metadata with its interval bounds resolved."""
    interval = yaml_metadata.get('interval')
    if not interval:
        return yaml_metadata
    resolved = []
    for bound in interval:
        value = str(bound)
        if '{{' in value and '}}' in value and template_resolver and template_context:
            rendered = template_resolver(value, template_context)
            # Empty: the variable is set later in the run; keep the template for then.
            value = rendered if rendered and not rendered.isspace() else value
        resolved.append(value)
    return {**yaml_metadata, 'interval': resolved}


def tag_metadata(
    tag: Any,
    template_resolver: Callable[[str, dict[str, Any]], str] | None,
    template_context: dict[str, Any] | None,
) -> dict[str, Any]:
    """A ``!timestamp`` tag's metadata (timezone, format, ...), with interval bounds resolved."""
    return resolve_interval_bounds(getattr(tag, 'metadata', {}), template_resolver, template_context)


def has_tolerance_or_interval(tag: Any) -> bool:
    """True if a ``!timestamp`` tag must stay a placeholder for the test to compare (not an exact value)."""
    return getattr(tag, 'has_interval', False) or getattr(tag, 'tolerance', None) is not None
