"""``adare chat`` — an embedded agentic REPL over the shared tool registry.

Owns the agent loop: read a natural-language request, ask the :class:`ChatBrain`
which tools to call, execute them against the Phase-1 registry in-process, feed
results back, and repeat until the brain answers. Tool calls and results stream
to the terminal with ``rich``. Same registry as the MCP control server — the
brain is the only difference.

Tool execution is sequential within a turn, so live-VM (``serialized_vm``) tools
never overlap — the one-VM/one-focus constraint holds without extra locking.
"""

from __future__ import annotations

import json
import logging
from typing import Any

log = logging.getLogger(__name__)

_QUIT = {'exit', 'quit', ':q', '/exit', '/quit'}

SYSTEM_PROMPT = """You are the ADARE console: a conversational control plane for \
ADARE, the Automated Desktop Analysis framework for Reproducible Experiments.

You drive ADARE by calling the provided tools — the full lifecycle: projects, \
environments, experiments, runs, VMs, dev-mode sessions, and LLM playbook \
authoring. Prefer acting via tools over describing what the user could type.

Guidance:
- Inspect before you mutate: list/get to confirm names and current state, then act.
- Tools return a uniform envelope: {"ok": true, "data": ...} on success, or \
{"ok": false, "error": {code, message, solutions}} on failure. Read the error \
and adapt or report it — do not silently retry the same call.
- Live-VM operations (running an experiment, driving a dev session, authoring a \
playbook, executing a playbook) boot or drive a real VM and can take minutes. \
Only one may touch the VM at a time. Set them up deliberately.
- When a run or authored playbook completes, report the concrete result \
(run ULID, best model, output path) so the user can cross-check with the CLI.
- Be concise. Report outcomes plainly; if a step failed, say so with the error."""


class ChatREPL:
    """A terminal agent loop feeding the shared tool registry to a brain."""

    def __init__(self, brain, tools, console=None):
        from adare.backend.chat.tools import call_tool

        if console is None:
            from adare.console import console as default_console
            console = default_console
        self._brain = brain
        self._console = console
        self._call_tool = call_tool
        self._tools = {t.name: t for t in tools}
        self._tool_list = list(tools)

    # -- public entry -------------------------------------------------------

    def run(self) -> None:
        """Run the interactive REPL until EOF / quit."""
        c = self._console
        self._brain.start(SYSTEM_PROMPT, self._tool_list)
        c.print(f"[bold cyan]ADARE chat[/bold cyan] — brain: {self._brain.name}, "
                f"{len(self._tool_list)} tools. Type 'exit' to quit.\n")
        while True:
            try:
                user = c.input('[bold green]adare[/bold green] › ').strip()
            except (EOFError, KeyboardInterrupt):
                c.print('\n[dim]bye[/dim]')
                return
            if not user:
                continue
            if user.lower() in _QUIT:
                c.print('[dim]bye[/dim]')
                return
            try:
                with c.status('[dim]thinking…[/dim]', spinner='dots'):
                    resp = self._brain.send_user(user)
                self._drive(resp)
            except KeyboardInterrupt:
                c.print('\n[yellow]interrupted[/yellow]')
            except (RuntimeError, ValueError, ConnectionError, TimeoutError, OSError) as exc:
                c.print(f'[red]error:[/red] {exc}')

    # -- agent loop ---------------------------------------------------------

    def _drive(self, resp, max_turns: int = 50) -> None:
        """Execute tool calls and re-prompt the brain until it answers."""
        c = self._console
        for _ in range(max_turns):
            if resp.text.strip():
                c.print(resp.text.strip())
            if not resp.tool_calls:
                return
            results = [self._run_one(tc) for tc in resp.tool_calls]
            with c.status('[dim]thinking…[/dim]', spinner='dots'):
                resp = self._brain.send_tool_results(results)
        c.print('[yellow]Reached the turn limit for this request.[/yellow]')

    def _run_one(self, tc):
        """Execute one tool call, stream it, and build its ToolResult."""
        from adare.backend.chat.brain import ToolResult

        c = self._console
        arg_preview = ', '.join(f'{k}={v!r}' for k, v in (tc.input or {}).items())
        c.print(f'  [magenta]→ {tc.name}[/magenta]([dim]{arg_preview}[/dim])')

        tool = self._tools.get(tc.name)
        if tool is None:
            out = {'ok': False, 'error': {'code': 'UNKNOWN_TOOL',
                                          'message': f'No such tool: {tc.name}', 'solutions': []}}
        else:
            if tool.serialized_vm:
                c.print('    [dim](live VM — this can take a while)[/dim]')
            out = self._call_tool(tool, tc.input)

        ok = out.get('ok')
        if ok:
            c.print('    [green]✓[/green] [dim]' + _summarize(out.get('data')) + '[/dim]')
        else:
            err = out.get('error', {})
            c.print(f'    [red]✗ {err.get("code", "ERROR")}[/red] '
                    f'[dim]{err.get("message", "")}[/dim]')
        return ToolResult(id=tc.id, name=tc.name, output=out, is_error=not ok)


def _summarize(data: Any, limit: int = 200) -> str:
    """One-line, length-capped preview of a tool's returned data."""
    if isinstance(data, list):
        return f'{len(data)} item(s)'
    text = json.dumps(data, default=str) if not isinstance(data, str) else data
    text = ' '.join(text.split())
    return text[:limit] + ('…' if len(text) > limit else '')
