"""Live terminal status for the playbook creator.

While a playbook drives the guest, one status block at the bottom of the
terminal shows the current step, how long it has run and what it is waiting
for (OCR attempt, screen text, elapsed / timeout). It redraws in place, so the
scrollback keeps one line per finished step instead of a line per retry or
heartbeat. Off a terminal (CI, a redirected log) the block is never drawn and
the creator prints its periodic progress lines instead.
"""

from __future__ import annotations

import time
from collections.abc import Iterator
from contextlib import contextmanager

from rich.console import Group, RenderableType
from rich.live import Live
from rich.panel import Panel
from rich.spinner import Spinner
from rich.text import Text

from adare.console import console


def fmt_duration(seconds: float) -> str:
    m, sec = divmod(int(seconds), 60)
    return f'{m}m{sec:02d}s' if m else f'{sec}s'


class LiveView:
    """The status block; ``session()`` shows it, ``step()``/``detail()`` update it."""

    def __init__(self) -> None:
        self._live: Live | None = None
        self._depth = 0
        self._started = 0.0
        self._step_started = 0.0
        self.title = ''
        self.window = ''
        self._step = ''
        self._detail = ''

    @property
    def active(self) -> bool:
        """True while the block is on screen (a session on a real terminal)."""
        return self._live is not None

    @contextmanager
    def session(self, title: str) -> Iterator[LiveView]:
        """Show the block for the duration; nested sessions share the outer one."""
        self._depth += 1
        if self._depth == 1:
            self.title, self.window = title, ''
            self._started = time.time()
            self.step('starting')
            if console.is_terminal:
                self._live = Live(self, console=console, transient=True, refresh_per_second=4)
                self._live.start()
        try:
            yield self
        finally:
            self._depth -= 1
            if self._depth == 0 and self._live is not None:
                self._live.stop()
                self._live = None

    def step(self, label: str) -> None:
        """Start timing a new step; clears the previous step's detail."""
        self._step = label
        self._step_started = time.time()
        self._detail = ''

    def detail(self, markup: str) -> None:
        """What the current step is doing right now (Rich markup, escaped by the caller)."""
        self._detail = markup

    def __rich__(self) -> RenderableType:
        now = time.time()
        head = Text.from_markup(f'{self._step}  [dim]{fmt_duration(now - self._step_started)}[/dim]')
        head.no_wrap, head.overflow = True, 'ellipsis'
        lines: list[RenderableType] = [Spinner('dots', text=head, style='cyan')]
        for markup in (self._detail, self.window):
            if markup:
                line = Text.from_markup(f'  {markup}', style='dim')
                line.no_wrap, line.overflow = True, 'ellipsis'
                lines.append(line)
        return Panel(
            Group(*lines),
            title=f'[b]{self.title}[/b] [dim]· {fmt_duration(now - self._started)}[/dim]',
            title_align='left',
            border_style='blue',
            padding=(0, 1),
        )


live = LiveView()
