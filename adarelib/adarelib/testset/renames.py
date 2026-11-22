"""Testfunctions and parameters that were renamed, so old playbooks get a precise message.

cattrs (host) ignores unknown keys and the guest agent raises a bare ``TypeError``, so a
playbook still using an old name would either silently lose the value or fail with an
unhelpful message. Every place that builds a test from playbook data asks
:func:`rename_problems` first: playbook validation, host-side structuring (host mode,
dry-run) and the guest agent.

Ships with the agent's adarelib wheel; standard library only, importable on Python 3.10.
"""

from typing import Any

#: old ``collection.function`` -> new one
RENAMED_FUNCTIONS: dict[str, str] = {
    'csv.line_count': 'csv.row_count',
}

#: ``collection.function`` -> {old parameter: new parameter}
RENAMED_PARAMETERS: dict[str, dict[str, str]] = {
    'text.occurrence_count': {'encodings': 'encoding'},
    'xml.element_text_matches': {'expected_text': 'expected_value'},
    'xml.xpath_result_matches': {'expected_result': 'expected_value'},
    'json.array_contains': {'expected_element': 'expected_value'},
    'jsonl.line_matches': {'match_mode': 'wildcard_mode'},
    'excel.sheet_exists': {'sheet_name': 'sheet'},
    'sqlite.query_result': {'expected_rows': 'expected_count'},
    'linux.log_entry_exists': {'log_file': 'dst', 'pattern': 'content'},
}


def _qualified(function: str) -> str:
    """``standard.x`` for a bare function name (the default collection)."""
    return function if '.' in function else f'standard.{function}'


def renamed_function(function: str) -> str | None:
    """The new name of a renamed testfunction, else None."""
    return RENAMED_FUNCTIONS.get(_qualified(function)) if isinstance(function, str) else None


def rename_problems(function: Any, parameters: Any) -> list[str]:
    """Messages for a renamed ``function`` or renamed keys in ``parameters``; empty when current."""
    if not isinstance(function, str):
        return []
    new_function = renamed_function(function)
    if new_function is not None:
        return [f'testfunction {function} was renamed to {new_function}']
    renamed = RENAMED_PARAMETERS.get(_qualified(function), {})
    if not isinstance(parameters, dict):
        return []
    return [
        f'{function}: parameter "{old}" was renamed to "{new}"' for old, new in renamed.items() if old in parameters
    ]
