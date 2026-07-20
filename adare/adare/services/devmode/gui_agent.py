"""DevMode service mixin: drive a session's VM with the vision-LLM GUI agent.

Exposes ``run_gui_agent`` which points :class:`GuiAgent` at an already-running
dev-session VM (``session.experiment_ctx.vm``) and, optionally, records a
replayable ADARE playbook. The vLLM endpoint/model/coord-space come from
``config.server`` (``VLLM_*`` / ``GUI_AGENT_*``) — so it works against any
OpenAI-compatible endpoint, including Ollama Cloud.
"""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path

from adare.core.dto.devmode import (
    DevGuiAgentRequest,
    DevGuiAgentResult,
    DevGuiAuthorRequest,
)
from adare.core.result import Result

log = logging.getLogger(__name__)


class GuiAgentMixin:
    """Adds vision-LLM GUI-agent execution to :class:`DevModeService`."""

    def run_gui_agent(self, request: DevGuiAgentRequest) -> Result[DevGuiAgentResult]:
        """Drive the session VM toward ``request.goal`` with the vision agent."""
        from adare.backend.experiment.vlm.exceptions import AgentError, VLMError

        try:
            result = asyncio.run(self._run_gui_agent_async(request))
            return Result.ok(result)
        except RuntimeError as exc:  # session/VM not found
            return Result.fail(
                'SESSION_NOT_FOUND', str(exc),
                ['Check active sessions with: adare dev list',
                 'Start one with: adare dev start -e <environment>'],
            )
        except VLMError as exc:
            return Result.fail(
                'VLM_ERROR', str(exc),
                ['Verify ADARE_VLLM_BASE_URL / ADARE_VLLM_API_KEY / ADARE_VLLM_MODEL',
                 'Run the preflight: adare vm gui-doctor'],
            )
        except AgentError as exc:
            return Result.fail(
                'AGENT_ERROR', str(exc),
                ['The agent hit a budget or stall limit — inspect the screenshot report',
                 'Try a clearer --goal or raise --max-steps'],
            )

    async def _run_gui_agent_async(self, request: DevGuiAgentRequest) -> DevGuiAgentResult:
        from adare.backend.experiment.execution.qemu_host_gui_executor import QEMUHostGUIExecutor
        from adare.backend.experiment.vlm import GuiAgent, PlaybookRecorder, VLMClient
        from adare.config.server import (
            AGENT_REPAIR_MODEL,
            GUI_AGENT_DECISION_RETRIES,
            GUI_AGENT_STALL_LIMIT,
            GUI_AGENT_WALL_CLOCK_SECONDS,
            LOCATE_CLICK,
            LOCATE_CROP_MARGIN,
            LOCATE_CROP_MIN,
            LOCATE_MODE,
            LOCATE_URL,
            VLLM_API_KEY,
            VLLM_BASE_URL,
            VLLM_COORD_SPACE,
            VLLM_MODEL,
        )
        from adare.config.server import GUI_AGENT_MAX_STEPS

        session = await self._manager.get_or_restore_session(request.session_id)
        if not session:
            raise RuntimeError(
                f"Dev session '{request.session_id}' not found or could not be restored"
            )
        ctx = session.experiment_ctx
        vm = getattr(ctx, 'vm', None) if ctx else None
        if vm is None:
            raise RuntimeError(
                f"Dev session '{request.session_id}' has no running VM"
            )

        client = VLMClient(base_url=VLLM_BASE_URL, model=VLLM_MODEL, api_key=VLLM_API_KEY)
        executor = QEMUHostGUIExecutor(vm=vm)

        locate_client = None
        if LOCATE_URL:
            from adare.backend.experiment.grounding import LocateAnythingClient
            locate_client = LocateAnythingClient(LOCATE_URL, mode=LOCATE_MODE)
            log.info('LocateAnything grounding enabled via %s', LOCATE_URL)

        # Optional cheaper model for text-only JSON-repair of malformed
        # decisions (same endpoint/key). Empty -> the agent reuses the main
        # client text-only, which is already far cheaper than a vision decision.
        repair_client = None
        if AGENT_REPAIR_MODEL:
            repair_client = VLMClient(
                base_url=VLLM_BASE_URL, model=AGENT_REPAIR_MODEL, api_key=VLLM_API_KEY)
            log.info('Decision-repair model enabled: %s', AGENT_REPAIR_MODEL)

        recorder = None
        run_dir: Path | None = None
        if request.output_file:
            out = Path(request.output_file)
            recorder = PlaybookRecorder(out, goal=request.goal)
            run_dir = out.parent / f'{out.stem}_run'
        elif ctx and getattr(ctx, 'experiment_run_directory', None):
            run_dir = Path(ctx.experiment_run_directory.path) / 'gui_agent'

        agent = GuiAgent(
            executor, client, request.goal,
            recorder=recorder, run_dir=run_dir, coord_space=VLLM_COORD_SPACE,
            locate_client=locate_client,
            locate_click=LOCATE_CLICK,
            locate_crop_margin=LOCATE_CROP_MARGIN,
            locate_crop_min=LOCATE_CROP_MIN,
            max_steps=request.max_steps or GUI_AGENT_MAX_STEPS,
            stall_limit=request.stall_limit or GUI_AGENT_STALL_LIMIT,
            wall_clock_seconds=GUI_AGENT_WALL_CLOCK_SECONDS,
            interactive=request.interactive,
            decision_retry_limit=GUI_AGENT_DECISION_RETRIES,
            repair_client=repair_client,
        )
        res = await agent.run()
        return DevGuiAgentResult(
            success=res.success,
            reason=res.reason,
            steps=len(res.steps),
            summary=res.summary,
            playbook_path=str(res.playbook_path) if res.playbook_path else None,
            report_path=str(res.report_path) if res.report_path else None,
        )

    # -- text authoring -----------------------------------------------------

    def run_gui_author(self, request: DevGuiAuthorRequest) -> Result[DevGuiAgentResult]:
        """Author a playbook from human text steps against the session VM."""
        from adare.backend.experiment.vlm.exceptions import AgentError

        try:
            result = asyncio.run(self._run_gui_author_async(request))
            return Result.ok(result)
        except RuntimeError as exc:  # session/VM not found
            return Result.fail(
                'SESSION_NOT_FOUND', str(exc),
                ['Check active sessions with: adare dev list',
                 'Start one with: adare dev start -e <environment>'],
            )
        except AgentError as exc:
            return Result.fail(
                'AGENT_ERROR', str(exc),
                ['Inspect the step screenshots under the run directory'],
            )

    async def _run_gui_author_async(self, request: DevGuiAuthorRequest) -> DevGuiAgentResult:
        from adare.backend.experiment.execution.qemu_host_gui_executor import QEMUHostGUIExecutor
        from adare.backend.experiment.vlm import PlaybookRecorder, TextAuthorDriver
        from adare.backend.experiment.vlm.exceptions import AgentError
        from adare.config.server import (
            LOCATE_CROP_MARGIN,
            LOCATE_CROP_MIN,
            LOCATE_MODE,
            LOCATE_URL,
            VLLM_COORD_SPACE,
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

        executor = QEMUHostGUIExecutor(vm=vm)

        locate_client = None
        if LOCATE_URL:
            from adare.backend.experiment.grounding import LocateAnythingClient
            locate_client = LocateAnythingClient(LOCATE_URL, mode=LOCATE_MODE)
            log.info('LocateAnything grounding enabled via %s', LOCATE_URL)
        else:
            log.warning('ADARE_LOCATE_URL is not set — described clicks cannot be '
                        'grounded; use `click @x,y ...` for explicit coordinates')

        recorder = None
        run_dir: Path | None = None
        if request.output_file:
            out = Path(request.output_file)
            recorder = PlaybookRecorder(out, goal='Authored from text')
            run_dir = out.parent / f'{out.stem}_run'
        elif ctx and getattr(ctx, 'experiment_run_directory', None):
            run_dir = Path(ctx.experiment_run_directory.path) / 'gui_author'

        driver = TextAuthorDriver(
            executor, recorder=recorder, run_dir=run_dir,
            locate_client=locate_client, coord_space=VLLM_COORD_SPACE,
            locate_crop_margin=LOCATE_CROP_MARGIN, locate_crop_min=LOCATE_CROP_MIN,
        )

        if request.script:
            res = await driver.run_script(request.script)
        elif request.interactive:
            res = await driver.run_interactive()
        else:
            raise AgentError('No script provided and not interactive — nothing to author')

        return DevGuiAgentResult(
            success=res.success,
            reason=res.reason,
            steps=len(res.steps),
            summary=res.summary,
            playbook_path=str(res.playbook_path) if res.playbook_path else None,
            report_path=str(res.report_path) if res.report_path else None,
        )
