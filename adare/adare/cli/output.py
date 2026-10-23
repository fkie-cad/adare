"""Output-format selection for the ADARE CLI.

One place decides how a command renders its data, so every read-only command
behaves the same for humans, scripts and AI agents:

* ``--json`` / ``--format [rich|plain|json|yaml]`` after the subcommand
  (added by :func:`output_options`), e.g. ``adare env list --json``;
* the global ``adare --format ...`` / ``--output-format ...`` before it;
* the ``ADARE_FORMAT`` environment variable;
* otherwise auto: ``rich`` on a terminal, ``plain`` (TSV) when stdout is piped.

Precedence is exactly that order: subcommand flag > global flag > env var > auto.

How a command uses it::

    @group.command(name='list')
    @output_options
    def list_things():
        exec_with_error_printing(exec_list_things, SimpleNamespace())

    def exec_list_things(arguments):
        items = ...
        emit({'things': [item.to_dict() for item in items]},
             rich=lambda: ThingTablePanel(items))

A command that cannot produce structured data declares
``@output_options(structured=False)``: it still gets ``--format rich|plain``, but
asking it for ``json``/``yaml`` exits with a usage error instead of printing a
table that a JSON parser would choke on.
"""

from __future__ import annotations

import functools
import logging
import os
import sys
from collections.abc import Callable
from types import SimpleNamespace
from typing import Any

import click

log = logging.getLogger(__name__)

FORMAT_CHOICES = ('rich', 'plain', 'json', 'yaml')
STRUCTURED_FORMATS = ('json', 'yaml')
FORMAT_ENV_VAR = 'ADARE_FORMAT'

# Help footer for every command decorated with ``output_options``. It is attached
# by ``AliasedGroup.add_command`` (see run.py) because the Click command object
# does not exist yet when the decorator runs.
OUTPUT_EPILOG = (
    'Output: --json (or --format json|yaml) prints machine-readable data on stdout; '
    'piped output defaults to plain tab-separated text. Also: adare --format, '
    '$ADARE_FORMAT. Exit codes: 0 ok, 1 error, 2 usage, 3 not found.'
)

# Attribute set on decorated callbacks so the group can find them.
_MARKER = '__adare_output_options__'


def _ctx_obj(ctx: click.Context | None):
    """The shared CLI state object (lives on the root context)."""
    if ctx is None:
        return None
    return ctx.find_root().obj


def _env_format() -> str | None:
    """The ``ADARE_FORMAT`` value, or None when unset/invalid (invalid warns once)."""
    raw = os.environ.get(FORMAT_ENV_VAR, '').strip().lower()
    if not raw:
        return None
    if raw not in FORMAT_CHOICES:
        log.warning(f'Ignoring {FORMAT_ENV_VAR}={raw!r}: expected one of {", ".join(FORMAT_CHOICES)}')
        return None
    return raw


def _stdout_is_tty() -> bool:
    isatty = getattr(sys.stdout, 'isatty', None)
    return bool(isatty and isatty())


def resolve_output_format(ctx: click.Context | None = None) -> str:
    """Resolve the effective output format for the running command.

    Order: subcommand ``--json/--format`` > global ``--format`` > ``$ADARE_FORMAT``
    > auto (``rich`` on a TTY, ``plain`` otherwise).

    Without a Click context (the exec functions reused by the MCP/chat tools) the
    historic ``rich`` default is kept, so those callers render exactly as before.
    """
    if ctx is None:
        ctx = click.get_current_context(silent=True)
        if ctx is None:
            return 'rich'
    obj = _ctx_obj(ctx)
    command_format = getattr(obj, 'command_output_format', None)
    if command_format:
        return command_format
    global_format = getattr(obj, 'output_format', None)
    if global_format:
        return global_format.lower()
    env_format = _env_format()
    if env_format:
        return env_format
    return 'rich' if _stdout_is_tty() else 'plain'


def is_structured_output(ctx: click.Context | None = None) -> bool:
    """True when the command must print data (plain/json/yaml) instead of Rich."""
    return resolve_output_format(ctx) != 'rich'


def is_machine_output(ctx: click.Context | None = None) -> bool:
    """True for json/yaml: the formats whose stdout must parse as a document."""
    return resolve_output_format(ctx) in STRUCTURED_FORMATS


def get_formatter_from_context():
    """``(formatter, output_file, dual_output)`` for the running command.

    ``dual_output`` means ``--output-file`` was given: Rich on the console plus a
    structured file.
    """
    from adare.helperfunctions.output_formatter import get_formatter

    ctx = click.get_current_context(silent=True)
    obj = _ctx_obj(ctx)
    output_file = getattr(obj, 'output_file', None)
    return get_formatter(resolve_output_format(ctx)), output_file, output_file is not None


def emit(data: Any, rich: Any = None) -> None:
    """Print a command's result in the resolved format.

    :param data: the structured result (dicts/lists/DTOs) used for plain/json/yaml
        and for ``--output-file``.
    :param rich: what to show on a terminal in rich mode: a Rich renderable, or a
        zero-argument callable returning one (so expensive tables are only built
        when they are shown). Defaults to rendering ``data`` itself.
    """
    from rich.console import Console

    formatter, output_file, dual_output = get_formatter_from_context()
    if dual_output or formatter.format_type.is_structured:
        formatter.print_or_save(data, output_file, dual_output)
        if not dual_output:
            return
        if formatter.format_type.is_structured:
            return
    renderable = rich() if callable(rich) else rich
    if renderable is None:
        # No dedicated Rich view: fall back to the plain rendering, which is
        # still readable on a terminal.
        from adare.helperfunctions.output_formatter import get_formatter

        renderable = get_formatter('plain').format(data)
    Console().print(renderable)


def _apply(func: Callable, structured: bool) -> Callable:
    @click.option(
        '--format',
        'adare_command_format',
        default=None,
        type=click.Choice(FORMAT_CHOICES, case_sensitive=False),
        help='Output format for this command (overrides adare --format and '
        f'${FORMAT_ENV_VAR}; default: rich on a terminal, plain when piped).',
    )
    @click.option('--json', 'adare_command_json', is_flag=True, default=False, help='Shorthand for --format json.')
    @functools.wraps(func)
    def wrapper(*args, adare_command_json: bool = False, adare_command_format: str | None = None, **kwargs):
        ctx = click.get_current_context()
        requested = adare_command_format.lower() if adare_command_format else None
        if adare_command_json:
            if requested and requested != 'json':
                raise click.UsageError(f'--json conflicts with --format {requested}', ctx=ctx)
            requested = 'json'
        root = ctx.find_root()
        if root.obj is None:
            # Invoked without the `adare` root group (tests, embedding). Never
            # replace an existing object: it carries the global --format.
            root.obj = SimpleNamespace()
        root.obj.command_output_format = requested
        if not structured and resolve_output_format(ctx) in STRUCTURED_FORMATS:
            raise click.UsageError(
                f"'{ctx.command_path}' does not support structured output "
                f"({resolve_output_format(ctx)}); use --format rich or plain",
                ctx=ctx,
            )
        return func(*args, **kwargs)

    setattr(wrapper, _MARKER, {'structured': structured})
    return wrapper


def output_options(func: Callable | None = None, *, structured: bool = True):
    """Add ``--json`` and ``--format [rich|plain|json|yaml]`` to a command.

    Usable bare (``@output_options``) or configured
    (``@output_options(structured=False)``). Place it *below* ``@group.command``.
    The selected format is stored on the root context object and read back by
    :func:`resolve_output_format` / :func:`get_formatter_from_context`.
    """
    if func is not None:
        return _apply(func, structured)
    return lambda f: _apply(f, structured)


def has_output_options(command: click.Command) -> bool:
    """True when ``command`` was decorated with :func:`output_options`."""
    return bool(getattr(command.callback, _MARKER, None))
