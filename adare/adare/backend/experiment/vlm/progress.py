"""Live per-step progress display for the GUI agent.

:class:`AgentProgressReporter` renders a ``rich.Live`` display: a table that
grows one row per agent step (step #, action kind, description, grounded/click
coords, status) plus, below it, a "chat" panel showing the *full* reasoning the
model gave for the latest step (toggle with ``show_reasoning``). It follows the
``rich.Live`` precedent in :mod:`adare.backend.experiment.print`.

The reporter is driven by a single synchronous callback, :meth:`on_event`, wired
into :class:`~adare.backend.experiment.vlm.agent.GuiAgent` via its ``progress``
hook. The agent emits one event when it *decides* an action and one after it
*executes* it; it also emits ``pause`` / ``resume`` events around the
interactive approve/skip/quit gate so the ``input()`` prompt is not clobbered by
the live-refreshing table. The reporter never raises out of ``on_event`` — a
display glitch must never abort a run.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from rich.console import Console, Group, RenderableType
from rich.live import Live
from rich.markup import escape
from rich.panel import Panel
from rich.table import Table

log = logging.getLogger(__name__)

# Action statuses the executor reports that count as a clean step (green tick);
# 'skipped' is the user's skip (yellow); anything else is treated as a failure.
_OK_STATUSES = frozenset({
    'success', 'waited', 'noted', 'done', 'step_done', 'unknown',
})


@dataclass
class _Row:
    index: int
    kind: str
    describe: str
    coords: str
    reasoning: str = ''
    status: str = 'running'


class AgentProgressReporter:
    """A ``rich.Live`` table that shows the agent's per-step progress.

    Use as a context manager around the run so the live display starts and
    stops cleanly::

        reporter = AgentProgressReporter(goal)
        with reporter:
            ...  # agent runs, calling reporter.on_event(...)
    """

    def __init__(
        self, goal: str, console: Console | None = None, *,
        show_reasoning: bool = True,
    ):
        self.goal = goal
        self._console = console or Console()
        self._show_reasoning = show_reasoning
        self._rows: dict[int, _Row] = {}
        self._latest: int | None = None  # newest step index, for the reasoning panel
        self._live: Live | None = None
        self._paused = False

    # -- lifecycle ----------------------------------------------------------

    def __enter__(self) -> AgentProgressReporter:
        self._live = Live(
            self._render(), console=self._console,
            refresh_per_second=8, transient=False,
        )
        self._live.start()
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        if self._live is not None:
            # One final render so the completed table is what stays on screen.
            try:
                self._live.update(self._render())
            except (ValueError, RuntimeError) as err:
                log.debug('progress final render failed: %s', err)
            self._live.stop()
            self._live = None

    # -- event sink ---------------------------------------------------------

    def on_event(self, event: dict) -> None:
        """Handle one progress event; never raises.

        Event ``type`` is one of ``decided`` (a new step was chosen),
        ``executed`` (its result is known), ``pause`` / ``resume`` (suspend the
        live display around the interactive ``input()`` gate).
        """
        try:
            kind = event.get('type')
            if kind == 'decided':
                self._on_decided(event)
            elif kind == 'executed':
                self._on_executed(event)
            elif kind == 'pause':
                self._pause()
            elif kind == 'resume':
                self._resume()
            self._refresh()
        except (ValueError, RuntimeError, KeyError, TypeError) as err:
            # A display problem must never break the agent loop.
            log.debug('progress on_event ignored error: %s', err)

    def _on_decided(self, event: dict) -> None:
        index = int(event['index'])
        coords = event.get('coords')
        grounded = bool(event.get('grounded'))
        if coords is not None:
            marker = f'({coords[0]},{coords[1]})'
            if grounded:
                marker += ' ✓'  # grounded to an element box
        else:
            marker = '—'  # em dash — not a positional action
        self._rows[index] = _Row(
            index=index,
            kind=str(event.get('kind', '')),
            describe=_trim(event.get('describe') or ''),
            coords=marker,
            reasoning=str(event.get('reasoning') or ''),
        )
        self._latest = index

    def _on_executed(self, event: dict) -> None:
        index = int(event['index'])
        row = self._rows.get(index)
        if row is not None:
            row.status = str(event.get('status', 'unknown'))

    # -- pause / resume around input() --------------------------------------

    def _pause(self) -> None:
        if self._live is not None and not self._paused:
            self._live.stop()
            self._paused = True

    def _resume(self) -> None:
        if self._live is not None and self._paused:
            self._live.start(refresh=True)
            self._paused = False

    # -- rendering ----------------------------------------------------------

    def _refresh(self) -> None:
        if self._live is not None and not self._paused:
            self._live.update(self._render())

    def _render(self) -> RenderableType:
        table = Table(
            title=f'GUI agent — {_trim(self.goal, 80)}',
            title_justify='left', expand=True,
        )
        table.add_column('#', justify='right', style='dim', no_wrap=True)
        table.add_column('action', no_wrap=True)
        table.add_column('describe', overflow='fold')
        table.add_column('coords', no_wrap=True)
        table.add_column('status', no_wrap=True)
        for index in sorted(self._rows):
            row = self._rows[index]
            table.add_row(
                str(row.index), row.kind, row.describe, row.coords,
                _status_cell(row.status),
            )
        if not self._show_reasoning:
            return table
        return Group(table, self._reasoning_panel())

    def _reasoning_panel(self) -> Panel:
        """A panel showing the latest step's full reasoning ('chat' view).

        Unlike the table cells (trimmed via ``_trim``), the reasoning text is
        shown in full and wraps/folds to the panel width.
        """
        row = self._rows.get(self._latest) if self._latest is not None else None
        if row is None:
            body = '[dim]waiting for the first model decision…[/dim]'
            title = 'reasoning'
        else:
            body = (escape(row.reasoning.strip())
                    or '[dim](no reasoning provided for this step)[/dim]')
            title = f'reasoning — step {row.index} ({row.kind})'
        return Panel(body, title=title, title_align='left', border_style='cyan')


def _status_cell(status: str) -> str:
    if status == 'running':
        return '[cyan]… running[/cyan]'
    if status == 'skipped':
        return '[yellow]skip[/yellow]'
    if status in _OK_STATUSES:
        return f'[green]✓ {status}[/green]'
    return f'[red]✗ {status}[/red]'


def _trim(text: str, limit: int = 60) -> str:
    text = ' '.join(text.split())
    return text if len(text) <= limit else text[: limit - 1] + '…'
