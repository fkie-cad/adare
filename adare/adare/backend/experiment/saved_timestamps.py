"""A saved timestamp as the expected value of an ordered comparison stays a point in time.

``save_timestamp`` puts Unix seconds into the execution context, and the runtime resolution of a
test fills ``{{ started }}`` in with that number. An ordered comparison (``comparison_type:
greater``, ``timestamp_epoch: 1601``, ...) would then read the number with the *field's*
epoch, unit or ``time_format``: a millisecond or FILETIME field compared with seconds. So for a
test with ordered parameters whose ``expected_value`` is exactly one timestamp variable (no
tolerance or interval), the expected value is passed as a placeholder with timestamp metadata
instead; the testfunction reads it as a point in time (``valuecompare.saved_value``).

Tests without ordered parameters are resolved as before.
"""

import re
from typing import Any

from adarelib.common.variables import VariableRegistry, VariableType
from adarelib.testset.valuecompare import is_ordered

_LONE_PLACEHOLDER = re.compile(r'\{\{\s*([A-Za-z_][A-Za-z0-9_]*)\s*\}\}')
PLACEHOLDER_SUFFIX = '_point_in_time'


def saved_timestamp_variable(test: dict[str, Any], registry: VariableRegistry | None) -> str | None:
    """The timestamp variable a test's ordered comparison expects, or ``None``.

    ``test`` is the raw playbook test (before variables are filled in).
    """
    parameters = test.get('parameter')
    if registry is None or not isinstance(parameters, dict) or not is_ordered(parameters):
        return None
    expected = parameters.get('expected_value')
    match = _LONE_PLACEHOLDER.fullmatch(expected.strip()) if isinstance(expected, str) else None
    if match is None:
        return None
    variable = registry.get(match.group(1))
    if variable is None or variable.type != VariableType.TIMESTAMP:
        return None
    return match.group(1)


def keep_point_in_time(resolved_test: dict[str, Any], name: str, registry: VariableRegistry) -> None:
    """Replace the filled-in ``expected_value`` of ``resolved_test`` by a placeholder for ``name``.

    The placeholder's metadata is the one the registry gives timestamp placeholders
    (``resolved_value``, ``tolerance``, ``timezone``). A variable with a tolerance keeps it, and
    the testfunction reports that it cannot be compared in order.
    """
    placeholder = f'{name}{PLACEHOLDER_SUFFIX}'
    metadata = registry._create_timestamp_tolerance_metadata(placeholder, registry.get(name), local_only=True)
    resolved_test['parameter']['expected_value'] = f'{{{{ {placeholder} }}}}'
    resolved_test.setdefault('_VARIABLE_METADATA', {})[placeholder] = metadata
