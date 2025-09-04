import re
from typing import Union

# internal imports
from adarelib.common.variables import VariableRegistry

import logging
log = logging.getLogger(__name__)


def resolve_variable_in_string(string: str, variables: Union[VariableRegistry, dict], regex: bool = False) -> str:
    """
    Resolve variables in string using {{variable_name}} syntax.
    
    Args:
        string: String containing variable references
        variables: VariableRegistry or legacy dict
        regex: Whether the string will be used as a regex pattern
    
    Returns:
        String with variables resolved
    """
    if isinstance(variables, VariableRegistry):
        return variables.resolve_in_string(string, for_regex=regex)
    
    # Legacy dict support - convert to VariableRegistry
    registry = VariableRegistry.from_dict(variables or {})
    return registry.resolve_in_string(string, for_regex=regex)
