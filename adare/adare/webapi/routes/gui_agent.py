"""GUI-agent live-view endpoints.

Run the vision-LLM GUI agent against a dev session *inside the web-server
process* and stream its per-step activity to the browser over the existing
session websocket (``/ws/{session_id}``), plus serve the annotated per-step
screenshots the agent writes to disk.

The one real subtlety is the sync/async bridge: ``run_gui_agent`` calls
``asyncio.run`` internally, so it cannot be awaited on the server loop. The run
is launched with ``asyncio.to_thread`` and its progress ``event_sink`` — a plain
sync callable invoked from that worker thread — hops each event back onto the
server loop via ``run_coroutine_threadsafe`` so ``ws_manager`` (which lives on
the server loop) can broadcast it.
"""
from __future__ import annotations

import asyncio
import logging
from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel

from adare.webapi.websocket_manager import ws_manager

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/sessions", tags=["gui-agent"])

# session_id -> run directory that holds steps/step_NNN.png for the latest run.
# Populated by the progress sink from the service's one-off 'run_dir' event, and
# read by the image endpoint. Mutated only via dict assignment (GIL-atomic).
_RUN_DIRS: dict[str, Path] = {}


class AgentRunBody(BaseModel):
    """Body for POST .../agent/run."""
    goal: str
    max_steps: int | None = None
    stall_limit: int | None = None
    planning: bool | None = None
    grounding: bool | None = None
    video: bool | None = None


def _step_frame(event: dict) -> dict | None:
    """Map an agent progress event to an ``agent_step`` data payload, or None.

    Only the loop events (decided / executed / pause / resume) become frames;
    the internal ``run_dir`` event is handled by the sink itself.
    """
    phase = event.get("type")
    if phase not in ("decided", "executed", "pause", "resume"):
        return None
    coords = event.get("coords")
    return {
        "phase": phase,
        "index": event.get("index"),
        "kind": event.get("kind"),
        "describe": event.get("describe"),
        "reasoning": event.get("reasoning"),
        "coords": list(coords) if coords is not None else None,
        "grounded": event.get("grounded"),
        "status": event.get("status"),
        "screenshot": event.get("screenshot"),
    }


@router.post("/{session_id}/agent/run")
async def run_agent(session_id: str, body: AgentRunBody):
    """Launch a GUI-agent run against ``session_id`` and stream it over the WS.

    Returns immediately with ``{started: true}``; progress arrives as
    ``agent_step`` frames and the terminal state as an ``agent_status`` frame.
    """
    from adare.api import AdareAPI
    from adare.core.dto.devmode import DevGuiAgentRequest

    loop = asyncio.get_running_loop()

    def sink(event: dict) -> None:
        """Progress sink — called from the run's worker thread; never raises."""
        try:
            if event.get("type") == "run_dir":
                _RUN_DIRS[session_id] = Path(event["path"])
                return
            data = _step_frame(event)
            if data is not None:
                asyncio.run_coroutine_threadsafe(
                    ws_manager.send_agent_step(session_id, data), loop
                )
        except (ValueError, RuntimeError, TypeError, KeyError, OSError) as exc:
            logger.debug("agent event sink error (ignored): %s", exc)

    dto = DevGuiAgentRequest(
        session_id=session_id,
        goal=body.goal,
        max_steps=body.max_steps,
        stall_limit=body.stall_limit,
        interactive=False,       # no stdin gate in the server
        planning=body.planning,
        grounding=body.grounding,
        progress=False,          # no rich Live display headless
        video=body.video,
    )

    await ws_manager.send_agent_status(session_id, "running")

    task = asyncio.create_task(
        asyncio.to_thread(AdareAPI().devmode.run_gui_agent, dto, sink)
    )

    def _on_done(finished: asyncio.Task) -> None:
        # Use .exception()/.result() (never a bare `except Exception`) so an
        # unexpected failure in the run still reaches the browser.
        exc = finished.exception()
        if exc is not None:
            logger.warning("agent run for %s crashed: %s", session_id, exc)
            asyncio.run_coroutine_threadsafe(
                ws_manager.send_agent_status(session_id, "failed", str(exc)), loop
            )
            return
        result = finished.result()
        if not result.success:
            msg = result.error.message if result.error else "agent run failed"
            asyncio.run_coroutine_threadsafe(
                ws_manager.send_agent_status(session_id, "failed", msg), loop
            )
            return
        data = result.data
        state = "finished" if (data and data.success) else "failed"
        summary = (data.summary or data.reason) if data else ""
        asyncio.run_coroutine_threadsafe(
            ws_manager.send_agent_status(session_id, state, summary), loop
        )

    task.add_done_callback(_on_done)
    return {"started": True}


@router.get("/{session_id}/agent/steps/{index}.png")
async def agent_step_image(session_id: str, index: int):
    """Serve the annotated ``step_NNN.png`` written by the latest run."""
    run_dir = _RUN_DIRS.get(session_id)
    if run_dir is None:
        raise HTTPException(status_code=404, detail="no known agent run for this session")
    steps_dir = (run_dir / "steps").resolve()
    shot = (steps_dir / f"step_{index:03d}.png").resolve()
    # Path-traversal guard: the resolved file must stay under steps_dir.
    if not str(shot).startswith(str(steps_dir)):
        raise HTTPException(status_code=404)
    if not shot.is_file():
        raise HTTPException(status_code=404, detail="screenshot not available yet")
    return FileResponse(shot, media_type="image/png")
