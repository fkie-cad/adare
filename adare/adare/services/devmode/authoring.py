"""DevMode service mixin: LLM-author a UI-action playbook for a session's VM.

Wraps the ``author_playbook.py`` harness (a cloud vision model authors an
``actions:`` playbook from a screenshot → ``parse_playbook`` validates → replay
verifies → repair) as a first-class :class:`~adare.core.result.Result`-returning
API method, so any brain (MCP client or ``adare chat``) can invoke it as a tool.

Serialization (per ``vlm/authoring/FLOW.md``): a VM has one screen and one input
focus, so every live-VM touch must be serialized. Model reasoning + validation
(blocking ``urllib`` / ``parse_playbook``) run in a worker thread via
``asyncio.to_thread``; the harness's ``replay_cb`` bounces each replay back onto
the single event loop that owns the VM/QMP connections with
``run_coroutine_threadsafe``, so replays never overlap and the loop stays the
sole driver of the VM.
"""

from __future__ import annotations

import asyncio
import logging
import tempfile
from pathlib import Path

from adare.core.dto.devmode import (
    DevAuthorPlaybookRequest,
    DevAuthorPlaybookResult,
    DevAuthorRoundInfo,
)
from adare.core.result import Result

log = logging.getLogger(__name__)


class AuthoringMixin:
    """Adds LLM playbook authoring to :class:`DevModeService`."""

    def author_playbook(
        self, request: DevAuthorPlaybookRequest,
    ) -> Result[DevAuthorPlaybookResult]:
        """Author a UI-action playbook for ``request.goal`` on the session VM."""
        from adare.backend.experiment.vlm.authoring.author_playbook import (
            AuthoringError,
            OllamaError,
        )

        try:
            result = asyncio.run(self._author_playbook_async(request))
            return Result.ok(result)
        except RuntimeError as exc:  # session / VM not found
            return Result.fail(
                'SESSION_NOT_FOUND', str(exc),
                ['Check active sessions with: adare dev list',
                 'Start one with: adare dev start -e <environment>'],
            )
        except OllamaError as exc:
            return Result.fail(
                'AUTHORING_MODEL_ERROR', str(exc),
                ['Verify the Ollama daemon is reachable (default http://localhost:11434)',
                 'Confirm the author models are pulled and vision-capable',
                 'Raise the read timeout with --read-timeout for slow cloud reasoning'],
            )
        except AuthoringError as exc:
            return Result.fail(
                'AUTHORING_ERROR', str(exc),
                ['The model produced no usable playbook — retry or refine the --goal',
                 'Inspect the per-round summary for the parse/replay failure'],
            )

    async def _author_playbook_async(
        self, request: DevAuthorPlaybookRequest,
    ) -> DevAuthorPlaybookResult:
        from adare.backend.experiment.execution.qemu_host_gui_executor import (
            QEMUHostGUIExecutor,
        )
        from adare.backend.experiment.vlm.authoring.author_playbook import (
            DEFAULT_MODELS,
            OLLAMA_HOST,
            OLLAMA_READ_TIMEOUT,
            author_verify_repair_loop,
            extract_schema,
        )

        session = await self._manager.get_or_restore_session(request.session_id)
        if not session:
            raise RuntimeError(
                f"Dev session '{request.session_id}' not found or could not be restored"
            )
        ctx = session.experiment_ctx
        vm = getattr(ctx, 'vm', None) if ctx else None
        if vm is None:
            raise RuntimeError(f"Dev session '{request.session_id}' has no running VM")

        # CV/OCR grounding server URL for replay (same resolution as serve_mcp).
        cv_url = 'http://localhost:13109/mcp'
        mcp_server = getattr(ctx, 'mcp_server', None) if ctx else None
        if mcp_server is not None and getattr(mcp_server, 'server_url', None):
            cv_url = mcp_server.server_url

        executor = QEMUHostGUIExecutor(vm=vm)
        screenshot_b64 = await self._capture_screenshot_b64(executor)

        models = list(request.models) if request.models else list(DEFAULT_MODELS)
        schema = extract_schema()
        host = request.host or OLLAMA_HOST
        read_timeout = request.read_timeout or OLLAMA_READ_TIMEOUT

        # Serialized live replay: the blocking harness runs in a worker thread and
        # bounces each replay onto this loop (the sole VM driver) and waits.
        replay_cb = None
        if request.replay:
            loop = asyncio.get_running_loop()

            def replay_cb(playbook_yaml: str) -> tuple[bool, str]:  # noqa: E306
                future = asyncio.run_coroutine_threadsafe(
                    self._replay_yaml(vm, playbook_yaml, cv_url, request.os_key), loop,
                )
                return future.result()

        outcome = await asyncio.to_thread(
            author_verify_repair_loop,
            request.goal, models, request.rounds, screenshot_b64, schema,
            replay_cb=replay_cb, host=host, read_timeout=read_timeout,
        )

        output_file: str | None = None
        if outcome.best_yaml and request.output_file:
            out = Path(request.output_file)
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_text(outcome.best_yaml)
            output_file = str(out)

        return DevAuthorPlaybookResult(
            success=outcome.succeeded,
            best_model=outcome.best_model,
            best_passing=outcome.best_passing,
            playbook_yaml=outcome.best_yaml,
            rounds=[
                DevAuthorRoundInfo(
                    model=r.model, round=r.round, valid=r.valid,
                    replayed=r.replayed, passing=r.passing, error=r.error,
                )
                for r in outcome.rounds
            ],
            output_file=output_file,
        )

    @staticmethod
    async def _capture_screenshot_b64(executor) -> str:
        """Capture the VM screen via the host executor; return base64 PNG."""
        res = await executor.screenshot()
        if res.get('status') != 'success':
            raise RuntimeError(res.get('message', 'screenshot capture failed'))
        return res['image']['data']

    @staticmethod
    async def _replay_yaml(vm, playbook_yaml: str, cv_url: str, os_key: str) -> tuple[bool, str]:
        """Write the authored YAML to a temp file and replay it on the live VM.

        Runs on the event loop that owns the VM (never concurrently with another
        replay), matching the serialized-VM contract in ``FLOW.md``.
        """
        from adare.backend.experiment.vlm.replay import run_playbook

        tmp_path: Path | None = None
        try:
            with tempfile.NamedTemporaryFile('w', suffix='.play.yaml', delete=False) as handle:
                handle.write(playbook_yaml)
                tmp_path = Path(handle.name)
            result = await run_playbook(vm, tmp_path, mcp_gui_url=cv_url, os_key=os_key)
            summary = (
                f'replayed {result.executed}/{result.total} actions; '
                f"healed={list(result.healed)}; failures={list(result.failures)}"
            )
            return result.success, summary
        finally:
            if tmp_path is not None:
                tmp_path.unlink(missing_ok=True)
