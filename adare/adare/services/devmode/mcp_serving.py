"""DevMode service mixin: serve a session's VM as a GUI-automation MCP server.

Exposes ``serve_mcp``, which binds a long-lived :class:`GuiMcpServer` to an
already-running dev-session VM (``session.experiment_ctx.vm``), its CV/OCR
server (``session.experiment_ctx.mcp_server.server_url``), a fresh
:class:`PlaybookRecorder`, and the project's testfunction catalog. An external
harness (OpenCode / Claude Code / any MCP client, model-agnostic) then connects
and authors deterministic, replayable playbooks by natural language — ADARE
grounds and records; the harness is the agentic loop.

Everything (session restore, VM/QMP connections, and the server) runs on one
event loop so the QMP-backed executor stays valid for tool calls.
"""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from typing import Any

from adare.core.dto.devmode import DevServeMcpRequest
from adare.core.result import Result

log = logging.getLogger(__name__)


def shape_testfunction_catalog(testfunctions: list[Any]) -> list[dict[str, Any]]:
    """Shape ``get_testfunctions_structured`` output into MCP catalog entries.

    There is no dedicated ``category`` in the schema, so we group by the
    testfunction file (the natural grouping). Host-mode compatibility is not
    filtered here — it is validated at replay by ``GuestToHostTestExecutor``.
    """
    catalog: list[dict[str, Any]] = []
    for tf in testfunctions:
        catalog.append({
            'name': tf.name,
            'dotnotation': tf.dotnotation,
            'description': tf.description,
            'parameters': tf.parameters,
            'category': getattr(tf, 'file_name', '') or getattr(tf, 'file_path', ''),
        })
    return catalog


class McpServingMixin:
    """Adds ``serve_mcp`` to :class:`DevModeService`."""

    def serve_mcp(self, request: DevServeMcpRequest) -> Result[None]:
        """Serve the session VM as an MCP server (blocks until interrupted)."""
        try:
            asyncio.run(self._serve_mcp_async(request))
            return Result.ok(None)
        except KeyboardInterrupt:
            log.info('ADARE GUI MCP server stopped')
            return Result.ok(None)
        except RuntimeError as exc:  # session/VM not found
            return Result.fail(
                'SESSION_NOT_FOUND', str(exc),
                ['Check active sessions with: adare dev list',
                 'Start one with: adare dev start <experiment> -e <environment>'],
            )

    async def _serve_mcp_async(self, request: DevServeMcpRequest) -> None:
        from adare.backend.experiment.execution.qemu_host_gui_executor import QEMUHostGUIExecutor
        from adare.backend.experiment.target_resolver import MCPTargetResolver
        from adare.backend.experiment.vlm import GuiMcpServer
        from adare.config.server import GUI_MCP_HOST, GUI_MCP_PORT

        session = await self._manager.get_or_restore_session(request.session_id)
        if not session:
            raise RuntimeError(
                f"Dev session '{request.session_id}' not found or could not be restored"
            )
        ctx = session.experiment_ctx
        vm = getattr(ctx, 'vm', None) if ctx else None
        if vm is None:
            raise RuntimeError(f"Dev session '{request.session_id}' has no running VM")

        cv_url = 'http://localhost:13109/mcp'
        mcp_server = getattr(ctx, 'mcp_server', None) if ctx else None
        if mcp_server is not None and getattr(mcp_server, 'server_url', None):
            cv_url = mcp_server.server_url

        output_dir = Path(request.output_dir) if request.output_dir else (
            Path(request.project_path) if request.project_path else Path.cwd()
        )
        output_dir.mkdir(parents=True, exist_ok=True)

        catalog = self._load_testfunction_catalog(request.project_path)

        executor = QEMUHostGUIExecutor(vm=vm)
        resolver = MCPTargetResolver(
            experiment_dir=output_dir, mcp_gui_url=cv_url,
            vm_client=None, os_key='linux',
        )
        server = GuiMcpServer(
            executor=executor, resolver=resolver, catalog=catalog,
            base_dir=output_dir, cv_url=cv_url,
        )

        host = request.host or GUI_MCP_HOST
        port = request.port or GUI_MCP_PORT
        log.info(
            'Serving session %s as GUI MCP server on %s:%d (%d testfunctions, recordings -> %s)',
            request.session_id, host, port, len(catalog), output_dir,
        )
        await server.serve_async(host, port)

    def _load_testfunction_catalog(self, project_path: Path | None) -> list[dict[str, Any]]:
        """Shape the project's testfunctions into ``list_testfunctions`` entries."""
        from adare.config.database import get_project_database_location
        from adare.database.api.structured_data import StructuredDataApi

        if not project_path:
            log.warning('No project path for MCP catalog — list_testfunctions will be empty')
            return []
        db_path = get_project_database_location(Path(project_path))
        if not db_path.exists():
            log.warning('Project database not found (%s) — empty testfunction catalog', db_path)
            return []

        with StructuredDataApi(db_path=db_path) as api:
            return shape_testfunction_catalog(
                api.get_testfunctions_structured(include_parameters=True)
            )
