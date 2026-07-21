"""Iterative build-verify-backtrack GUI agent (terse goal -> verified playbook).

Where :class:`~adare.backend.experiment.vlm.agent.GuiAgent` is a purely reactive
loop (goal + screenshot -> one micro-action) that wanders or stalls on a terse,
high-level goal, :class:`PlanningAgent` adds the missing scaffolding a human
would use: it *decomposes* the goal into ordered sub-goals, *executes* each one
with the reactive loop (reused untouched), *verifies* it with an independent
checker, and — on a dead end — *resets the VM to a prior state and tries again*,
building the playbook out of only the verified blocks.

The orchestrator **composes** the existing ``GuiAgent`` as its per-sub-goal
executor (the same pattern as ``TextAuthorDriver``), so the reactive loop,
grounded clicks, visual log and recorder are all reused. Layering stays clean:
this module never imports the devmode session — the VM checkpoint/restore and the
acceptance checker are injected as **async callables**, so the same orchestrator
is exercised deterministically with fakes and wired to a real session in the
service layer.

Roles (each a :class:`~adare.backend.experiment.vlm.client.VLMClient`, all
defaulting to the main ``VLLM_*`` model, each overridable per role):

* **planner** — decomposes the terse goal (+ first screenshot) into sub-goals,
  each ``{text, success}`` (an imperative step + a "done when ..." statement).
* **executor** — the existing ``GuiAgent`` reactive loop, scoped to one sub-goal.
* **checker** — the injected ``verify`` callable (``run_acceptance_checks`` with
  the sub-goal's ``success`` statement) deciding pass/fail + reason.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable

from .actions import _extract_json_object
from .agent import AgentRunResult, GuiAgent
from .client import VLMClient
from .exceptions import VLMError

log = logging.getLogger(__name__)


# Injected-callable signatures (documentation only).
CheckpointFn = Callable[[str], Awaitable[Any]]
RestoreFn = Callable[[str], Awaitable[Any]]
VerifyFn = Callable[[str], Awaitable[tuple[bool, str]]]


_DECOMPOSE_SYSTEM = """\
You are a planner. Decompose a high-level goal for operating a computer through \
its GUI into an ordered list of concrete SUB-GOALS. Each sub-goal is executed by \
a separate agent that can only click, type, press keys and scroll — no terminal, \
no file access — and is verified from a screenshot by an independent checker.

For each sub-goal provide:
- "text":    a short imperative instruction (what the agent should do now).
- "success": a "done when ..." statement the checker can confirm from a \
screenshot alone (something visibly true on screen when the sub-goal is met).

Keep sub-goals COARSE — each one is checkpointed (a full VM snapshot), so aim \
for roughly 3 to 7, not one per click. Order them so each builds on the last.

Reply with ONLY this JSON object and nothing else:
{"steps": [{"text": "...", "success": "..."}, ...]}"""


_REVISE_SYSTEM = """\
You are a planner revising a partially-executed plan. The sub-goals listed as \
already done succeeded and must NOT be repeated. The current screenshot shows \
where execution is now, and you are told why the last attempt failed. Re-plan \
ONLY the REMAINING sub-goals from here, taking a different approach where the \
previous one hit a dead end.

Same rules as before: each sub-goal is {"text": imperative step, "success": \
"done when ..." statement verifiable from a screenshot}, kept coarse.

Reply with ONLY this JSON object and nothing else:
{"steps": [{"text": "...", "success": "..."}, ...]}"""


@dataclass
class PlanStep:
    """One sub-goal: an imperative step + a checker-verifiable success statement."""

    text: str
    success: str
    status: str = 'pending'  # pending | active | done | failed
    hint: str = ''           # last failure reason, fed back on retry


@dataclass
class Plan:
    """An ordered list of sub-goals with a cursor at the current one."""

    steps: list[PlanStep] = field(default_factory=list)
    current: int = 0

    def render(self) -> str:
        """A compact human/model-readable view of the plan and its progress."""
        lines = []
        for i, s in enumerate(self.steps):
            if s.status == 'done':
                mark = '[x]'
            elif i == self.current:
                mark = '[>]'
            else:
                mark = '[ ]'
            lines.append(f'{mark} {i + 1}. {s.text}  (success: {s.success})')
        return '\n'.join(lines)


class PlanningAgent:
    """Plan -> (checkpoint -> execute -> verify -> backtrack/retry/replan) -> playbook."""

    def __init__(
        self,
        executor: GuiAgent,
        planner_client: VLMClient,
        *,
        checkpoint: CheckpointFn,
        restore: RestoreFn,
        verify: VerifyFn,
        retry_limit: int = 2,
        replan_limit: int = 2,
        subgoal_max_steps: int = 25,
        subgoal_stall_limit: int = 4,
    ):
        self.executor = executor
        self.planner = planner_client
        self._checkpoint = checkpoint
        self._restore = restore
        self._verify = verify
        self.retry_limit = retry_limit
        self.replan_limit = replan_limit
        self.subgoal_max_steps = subgoal_max_steps
        self.subgoal_stall_limit = subgoal_stall_limit
        self.goal = executor.goal
        self.plan: Plan | None = None
        # Monotonic counter so every checkpoint name is unique even when the same
        # sub-goal index is re-checkpointed after a re-plan.
        self._ckpt_seq = 0

    # -- planning -----------------------------------------------------------

    def _parse_steps(self, reply: str) -> list[PlanStep]:
        """Parse a planner ``{"steps": [...]}`` reply into :class:`PlanStep`s."""
        obj = _extract_json_object(reply)
        raw = obj.get('steps')
        if not isinstance(raw, list) or not raw:
            raise VLMError(f'Planner returned no sub-goals: {obj!r}')
        steps: list[PlanStep] = []
        for item in raw:
            if not isinstance(item, dict):
                continue
            text = str(item.get('text', '')).strip()
            success = str(item.get('success', '')).strip()
            if not text:
                continue
            # A missing success statement means the checker cannot verify it;
            # fall back to the step text so the run still progresses honestly.
            steps.append(PlanStep(text=text, success=success or text))
        if not steps:
            raise VLMError(f'Planner produced no usable sub-goals: {obj!r}')
        return steps

    async def decompose(self, goal: str, screenshot_b64: str) -> Plan:
        """Decompose the terse goal (+ first screenshot) into an ordered plan."""
        messages = [
            {'role': 'system', 'content': _DECOMPOSE_SYSTEM},
            {'role': 'user', 'content': [
                self.planner.text_content(
                    f'GOAL: {goal}\n\nThis is the current screen. '
                    'Decompose the goal into ordered sub-goals.'),
                self.planner.image_content(screenshot_b64),
            ]},
        ]
        reply = await self.planner.chat(messages, temperature=0.0, max_tokens=1200)
        plan = Plan(steps=self._parse_steps(reply))
        log.info('Planner decomposed goal into %d sub-goals:\n%s',
                 len(plan.steps), plan.render())
        return plan

    async def revise(
        self, goal: str, done_so_far: list[str], screenshot_b64: str, reason: str,
    ) -> Plan:
        """Re-decompose the remainder after a sub-goal could not be completed."""
        done_txt = '\n'.join(f'- {d}' for d in done_so_far) or '(none yet)'
        messages = [
            {'role': 'system', 'content': _REVISE_SYSTEM},
            {'role': 'user', 'content': [
                self.planner.text_content(
                    f'GOAL: {goal}\n\n'
                    f'ALREADY DONE (do not repeat):\n{done_txt}\n\n'
                    f'The last attempt failed because: {reason}\n\n'
                    'This is the current screen. Re-plan the REMAINING sub-goals.'),
                self.planner.image_content(screenshot_b64),
            ]},
        ]
        reply = await self.planner.chat(messages, temperature=0.2, max_tokens=1200)
        plan = Plan(steps=self._parse_steps(reply))
        log.info('Planner revised remainder into %d sub-goals:\n%s',
                 len(plan.steps), plan.render())
        return plan

    # -- helpers ------------------------------------------------------------

    async def _screenshot_b64(self) -> str:
        b64, _png, _w, _h = await self.executor._capture()
        return b64

    def _plan_context(self, plan: Plan, index: int, hint: str) -> str:
        """The plan-wide context injected into the executor for this sub-goal."""
        parts = ['PLAN (you are executing the [>] step only):', plan.render()]
        if hint:
            parts.append(
                'A previous attempt at this sub-goal failed — do it differently. '
                f'Reason it failed: {hint}')
        return '\n'.join(parts)

    def _finish(self, success: bool, reason: str, *, summary: str = '') -> AgentRunResult:
        """Finalize via the executor so the recorder + report reuse is unchanged."""
        return self.executor._finish(success, reason, summary=summary)

    # -- the iterative loop -------------------------------------------------

    async def run(self) -> AgentRunResult:
        """Decompose, then execute/verify each sub-goal with backtrack + replan."""
        recorder = self.executor.recorder
        first = await self._screenshot_b64()
        plan = await self.decompose(self.goal, first)
        self.plan = plan

        replans = 0
        i = 0
        while i < len(plan.steps):
            sg = plan.steps[i]
            plan.current = i
            sg.status = 'active'

            name = f'plan_sg{i}_{self._ckpt_seq}'
            self._ckpt_seq += 1
            await self._checkpoint(name)                       # snapshot BEFORE
            mark = recorder.mark() if recorder else None

            attempt = 0
            outcome = 'abort'
            while True:
                context = self._plan_context(plan, i, sg.hint)
                run_reason = await self.executor.execute_subgoal(
                    sg.text, context,
                    max_steps=self.subgoal_max_steps,
                    stall_limit=self.subgoal_stall_limit,
                )
                ok, vreason = await self._verify(sg.success)
                if ok:
                    log.info('Sub-goal %d verified: %s', i, sg.text)
                    sg.status = 'done'
                    sg.hint = ''
                    outcome = 'pass'
                    break

                # Dead end: discard the steps recorded for this attempt and roll
                # the live VM back to the pre-sub-goal checkpoint before retrying.
                log.info('Sub-goal %d failed verification (%s); backtracking',
                         i, vreason or run_reason)
                if mark is not None:
                    recorder.rollback(mark)
                await self._restore(name)
                attempt += 1

                if attempt <= self.retry_limit:
                    sg.hint = vreason or run_reason
                    sg.status = 'active'
                    continue

                if replans < self.replan_limit:
                    done = [s.text for s in plan.steps[:i]]
                    screen = await self._screenshot_b64()
                    revised = await self.revise(
                        self.goal, done, screen, vreason or run_reason)
                    replans += 1
                    plan.steps[i:] = revised.steps            # keep verified prefix
                    outcome = 'replan'
                    break

                sg.status = 'failed'
                outcome = 'abort'
                break

            if outcome == 'pass':
                i += 1
                continue
            if outcome == 'replan':
                continue                                       # i now = first revised step
            return self._finish(
                False,
                f'could not complete sub-goal {i + 1} ("{sg.text}") after '
                f'{self.retry_limit} retries and {replans} re-plan(s)')

        done_txt = '; '.join(s.text for s in plan.steps)
        return self._finish(True, 'all sub-goals verified', summary=done_txt)
