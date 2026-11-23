"""Load-time checks of the Jinja templates in a playbook.

Templates are rendered while the run is going, so a wrong literal argument to a timestamp
filter (``{{ t | timezone('Europe/Berln') }}``) would otherwise only fail mid-run.
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

import jinja2
import yaml
from jinja2 import nodes

from adarelib.common.variables import ValidationError, check_timezone

_ENV = jinja2.Environment()


def _strings(value: Any) -> Iterator[str]:
    """Every string in the loaded YAML, including the fields of custom tags (``!timestamp`` ...)."""
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for entry in value.values():
            yield from _strings(entry)
    elif isinstance(value, (list, tuple)):
        for entry in value:
            yield from _strings(entry)
    elif isinstance(value, yaml.YAMLObject):
        yield from _strings(vars(value))


def _literal_timezones(template: str) -> Iterator[Any]:
    try:
        tree = _ENV.parse(template)
    except jinja2.TemplateSyntaxError:
        return  # reported where the template is rendered; this check is about filter arguments
    for node in tree.find_all(nodes.Filter):
        if node.name != 'timezone':
            continue
        args = list(node.args) + [kw.value for kw in node.kwargs if kw.key == 'tz_name']
        if args and isinstance(args[0], nodes.Const):
            yield args[0].value


def check_timestamp_filters(data: Any) -> None:
    """Check the literal zone of every ``timezone(...)`` filter in the loaded playbook data.

    :raises ValidationError: a zone is not a UTC offset or known zone name (the template is named)
    """
    for text in _strings(data):
        if '{{' not in text:
            continue
        for zone in _literal_timezones(text):
            try:
                check_timezone(zone)
            except ValidationError as e:
                raise ValidationError(f"Template {text!r}: {e}") from e
