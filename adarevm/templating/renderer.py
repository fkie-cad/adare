"""Simple server-side template rendering."""

import logging
from typing import Any

from jinja2 import BaseLoader, Environment

log = logging.getLogger(__name__)


class TemplateRenderer:
    """Simple Jinja2 renderer for enriched templates."""

    def __init__(self):
        """Initialize basic Jinja2 environment."""
        self.env = Environment(
            loader=BaseLoader(),
            autoescape=False  # Plain text templates
        )

    def render(self, template_str: str, variables: dict[str, Any]) -> str:
        """Render template with enriched variables.
        
        Args:
            template_str: Template with simple {{ TIMESTAMP_VAR }} placeholders
            variables: Dict with enriched variable values
            
        Returns:
            Rendered string
        """
        try:
            template = self.env.from_string(template_str)
            return template.render(**variables)
        except Exception as e:
            log.error(f"Template rendering failed: {e}")
            log.error(f"Template: {template_str}")
            log.error(f"Variables: {variables}")
            return template_str  # Return original on error
