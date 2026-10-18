"""Controller mixin: failure evidence and ``on_failure`` steps (see ``failure_evidence``)."""

import logging
import time
from pathlib import Path
from typing import Any

from adare.backend.experiment.action_executor import ActionResult
from adare.types.playbook import ActionType

log = logging.getLogger(__name__)


class FailureHandlingMixin:
    """Methods ``PlaybookController.execute_playbook`` calls when an action fails."""

    # Provided by PlaybookController.
    experiment_run_directory: Path | None
    action_executor: Any
    variable_resolver: Any
    on_failure_results: list[ActionResult]
    failure_evidence: list[dict]

    @staticmethod
    def _get_action_detail(action: ActionType) -> str:
        raise NotImplementedError

    async def _record_failure_evidence(self, action_index: int, resolved_action: ActionType, result: ActionResult):
        """Save screenshot, OCR dump and target description for a failed action (never raises)."""
        from adare.backend.experiment.failure_evidence import collect_failure_evidence

        try:
            record = await collect_failure_evidence(
                run_dir=self.experiment_run_directory,
                action_index=action_index,
                action=resolved_action,
                result=result,
                target_resolution=self.action_executor.target_resolution,
            )
        except Exception as e:  # noqa: BLE001 - evidence must never change the run outcome
            log.error(f"Failure evidence for action {action_index} failed: {e}", exc_info=True)
            return
        if record:
            self.failure_evidence.append(record)
            if result.data is None:
                result.data = {}
            if isinstance(result.data, dict):
                result.data['failure_evidence'] = record.get('files', {})

    async def _run_on_failure_steps(self, steps: list[ActionType]):
        """Execute the ``on_failure:`` steps in order; one failing step does not stop the rest.

        No flow-console events are emitted for them (the run tally is derived from events and
        must not change), and no DB execution records are written; results go to the log and
        to ``self.on_failure_results``.
        """
        log.warning(f"Running {len(steps)} on_failure step(s) after a failed action")
        for j, step in enumerate(steps):
            step_name = type(step).__name__
            context = f"onfail{j + 1:02d}_{self._get_action_detail(step)}".rstrip("_")
            start = time.time()
            try:
                step_result = await self.action_executor.execute_action(
                    step,
                    parent_event_id=None,
                    event_emitter=None,
                    variable_resolver=self.variable_resolver,
                    action_context=context,
                )
            except Exception as e:  # noqa: BLE001 - recovery steps must not abort the run
                log.error(f"on_failure step {j + 1} ({step_name}) raised: {e}", exc_info=True)
                step_result = ActionResult(success=False, message=f"{type(e).__name__}: {e}")
            step_result.execution_time = time.time() - start
            self.on_failure_results.append(step_result)
            if step_result.success:
                log.info(f"on_failure step {j + 1}/{len(steps)} ({step_name}) ok")
            else:
                log.error(f"on_failure step {j + 1}/{len(steps)} ({step_name}) failed: {step_result.message}")
