"""``adare tui``: the Textual command browser from trogon, imported lazily.

Drop-in for ``trogon.tui``: registers the same ``tui`` command on the group it
decorates, but imports trogon (and textual under it, ~75 ms) only when the TUI
is actually opened instead of on every ``adare`` invocation, ``--help`` included.
"""

import click


def tui(name: str | None = None, command: str = 'tui', help: str = 'Open Textual TUI.'):
    def decorator(app: click.Group):
        @click.pass_context
        def wrapped_tui(ctx, *args, **kwargs):
            from trogon import Trogon

            Trogon(app, app_name=name, command_name=command, click_context=ctx).run()

        app.command(name=command, help=help)(wrapped_tui)
        return app

    return decorator
