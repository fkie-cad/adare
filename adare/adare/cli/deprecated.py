"""Hidden aliases that keep moved commands working under their old names."""

import copy
import functools

import click


def deprecated_alias(cmd: click.Command, old_name: str, new_path: str) -> click.Command:
    """Return a hidden copy of ``cmd`` named ``old_name`` that points users at ``new_path``.

    The copy shares params (and, for a group, its subcommands) with ``cmd``, so
    behaviour stays identical; it only adds a one-line notice on stderr, which
    keeps ``--json`` output on stdout parseable.
    """
    alias = copy.copy(cmd)
    alias.name = old_name
    alias.hidden = True
    alias.help = f'Deprecated: moved to `{new_path}`.'
    alias.short_help = None
    original = cmd.callback

    def notify():
        old_path = click.get_current_context().command_path
        click.echo(f'Note: `{old_path}` has moved to `{new_path}`; the old name will be removed.', err=True)

    if original is None:
        alias.callback = notify
    else:

        @functools.wraps(original)
        def callback(*args, **kwargs):
            notify()
            return original(*args, **kwargs)

        alias.callback = callback
    return alias
