"""Error reporting and exit codes for the ADARE CLI.

Every failure that reaches the CLI boundary is reported the same way:

* exactly ONE concise message on **stderr** (stdout carries only data):
  ``Error: <message>`` plus ``Hint: ...`` when the exception carries solutions;
* in ``json``/``yaml`` mode the message is a document instead::

      {"error": {"code": "TESTFUNCTION_NOT_FOUND", "message": "...",
                 "hint": "...", "solutions": ["..."]}}

  ``code`` is derived from the exception class (``TestFunctionNotFoundError`` ->
  ``TESTFUNCTION_NOT_FOUND``), ``hint`` is the first solution or null, and
  ``solutions`` is always a list;
* the traceback only with ``--very-verbose``;
* a stable exit code (see ``EXIT_*``).
"""

from __future__ import annotations

import json
import logging
import re
import sys
import traceback
from collections.abc import Iterable

import click

log = logging.getLogger(__name__)

EXIT_OK = 0
EXIT_ERROR = 1
EXIT_USAGE = 2
EXIT_NOT_FOUND = 3

# Code fragments that mean "the thing you named does not exist".
_NOT_FOUND_MARKERS = ('NOT_FOUND', 'DOES_NOT_EXIST', 'NOT_EXIST')
# Codes that mean "you called the command wrongly".
_USAGE_CODES = frozenset({'ARGUMENTS', 'INVALID_PATH', 'USAGE', 'INVALID_ARGUMENT'})
# Spelling normalisations so one concept has one code whatever the class name.
_CODE_ALIASES = (('TEST_FUNCTION', 'TESTFUNCTION'),)
# Fallback hint for a not-found error that carries no solutions of its own.
_DEFAULT_HINTS = {
    'ENVIRONMENT_NOT_FOUND': 'Run `adare env list` to see available environments',
    'EXPERIMENT_NOT_FOUND': 'Run `adare experiment list` to see available experiments',
    'RUN_NOT_FOUND': 'Run `adare runs list` to see available runs',
    'PROJECT_NOT_FOUND': 'Run `adare project list` to see available projects',
    'VM_NOT_FOUND': 'Run `adare vm list` to see available VMs and instances',
    'TESTFUNCTION_NOT_FOUND': 'Run `adare test list` to see available testfunctions',
}


def error_code_for(name: str | type | BaseException) -> str:
    """Derive a SCREAMING_SNAKE error code from an exception (class) or a code.

    ``TestFunctionNotFoundError`` -> ``TESTFUNCTION_NOT_FOUND``,
    ``VMNotFoundError`` -> ``VM_NOT_FOUND``, ``RunNotFoundError`` -> ``RUN_NOT_FOUND``.
    An already upper-case code (``SESSION_NOT_FOUND``) is returned unchanged.
    """
    if isinstance(name, BaseException):
        name = type(name).__name__
    elif isinstance(name, type):
        name = name.__name__
    name = (name or 'ERROR').strip()
    if re.fullmatch(r'[A-Z0-9_]+', name):
        code = name
    else:
        snake = re.sub(r'(?<=[a-z0-9])(?=[A-Z])|(?<=[A-Z])(?=[A-Z][a-z])', '_', name)
        code = snake.upper()
        for suffix in ('_EXCEPTION', '_ERROR'):
            if code.endswith(suffix) and code != suffix.lstrip('_'):
                code = code[: -len(suffix)]
                break
    for old, new in _CODE_ALIASES:
        code = code.replace(old, new)
    return code or 'ERROR'


def exit_code_for(code: str) -> int:
    """Map an error code to the CLI exit code (3 not found, 2 usage, 1 otherwise)."""
    if any(marker in code for marker in _NOT_FOUND_MARKERS):
        return EXIT_NOT_FOUND
    if code in _USAGE_CODES:
        return EXIT_USAGE
    return EXIT_ERROR


def _clean(text: str) -> str:
    from adare.helperfunctions.text import clean_rich_inline_str

    return clean_rich_inline_str(str(text)).strip()


def _verbose_traceback_enabled() -> bool:
    ctx = click.get_current_context(silent=True)
    obj = ctx.find_root().obj if ctx is not None else None
    return bool(getattr(obj, 'very_verbose', False))


def report_error(code: str, message: str, solutions: Iterable[str] | None = None, exit_code: int | None = None) -> int:
    """Print one error to stderr in the active format and return its exit code."""
    from rich.console import Console

    from adare.cli.output import is_machine_output, resolve_output_format

    code = error_code_for(code)
    message = _clean(message)
    solutions = [_clean(s) for s in (solutions or []) if s and _clean(s)]
    if not solutions and code in _DEFAULT_HINTS:
        solutions = [_DEFAULT_HINTS[code]]
    hint = solutions[0] if solutions else None
    if exit_code is None:
        exit_code = exit_code_for(code)

    if is_machine_output():
        payload = {'error': {'code': code, 'message': message, 'hint': hint, 'solutions': solutions}}
        if resolve_output_format() == 'yaml':
            import yaml

            sys.stderr.write(yaml.safe_dump(payload, sort_keys=False, allow_unicode=True))
        else:
            sys.stderr.write(json.dumps(payload, ensure_ascii=False) + '\n')
        sys.stderr.flush()
        return exit_code

    console = Console(stderr=True, highlight=False)
    console.print('[bold red]Error:[/bold red] ', end='')
    console.print(message, markup=False)
    if len(solutions) == 1:
        console.print('[cyan]Hint:[/cyan] ', end='')
        console.print(hint, markup=False)
    elif solutions:
        console.print('[cyan]Hints:[/cyan]')
        for solution in solutions:
            console.print(f'  - {solution}', markup=False)
    return exit_code


def report_exception(exc: BaseException) -> int:
    """Report a ``LoggedException`` at the CLI boundary; return the exit code.

    Informational ``LoggedException`` subclasses (``informational = True``, e.g.
    "no projects found") print their message to stderr and exit 0. Everything
    else is an error.
    """
    if _verbose_traceback_enabled():
        traceback.print_exception(type(exc), exc, exc.__traceback__, file=sys.stderr)

    message = getattr(exc, 'message', None) or str(exc)
    if getattr(exc, 'informational', False):
        from rich.console import Console

        Console(stderr=True, highlight=False).print(_clean(message), markup=False)
        return EXIT_OK

    code = getattr(exc, 'error_code', None) or error_code_for(exc)
    if code in ('LOGGED', 'LOGGED_ERROR'):
        # A bare LoggedException/LoggedErrorException names no specific failure.
        code = 'ERROR'
    solutions = getattr(exc, 'possible_solutions', None) or []
    hint = getattr(exc, 'hint', None)
    if hint and hint not in solutions:
        solutions = [hint, *solutions]
    return report_error(code, message, solutions, getattr(exc, 'exit_code', None))


def fail(code: str, message: str, solutions: Iterable[str] | None = None, exit_code: int | None = None) -> None:
    """Report an error and exit (for CLI code that has no exception to raise)."""
    sys.exit(report_error(code, message, solutions, exit_code))
