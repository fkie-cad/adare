"""Implicit controls for negative tests: was the act behind an absence actually done?

A test for an absent artifact (``*_does_not_exist``, ``visual.not_exists``, ``count_max``
with max 0, anything with ``expect_to_fail``, or a test function declaring
``negative = True``) passes just as well when the GUI action that should have produced
the absence never took effect. So a *passing* negative test becomes **INCONCLUSIVE** when
any GUI action before it in the run

* was skipped by a ``when:`` condition,
* failed,
* failed its ``verify:``, or
* showed no screen change in the automatic effect check (``effect: unchanged``, unless the
  author marked it ``effect: none``),

or when one of its explicit ``controls:`` (other tests, e.g. "the file existed before")
did not pass before it. The implicit action checks never affect a positive test; explicit
``controls:`` count on whichever test declares them. :class:`EffectLedger` collects
the evidence while the run executes; :func:`judge_negative_test` applies the rule.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

from adare.types.playbook import BlockAction, ClickAction, DragAction, GotoAction, KeyboardAction, ScrollAction

log = logging.getLogger(__name__)

#: Actions whose effect is checked (and whose lack of effect undermines an absence)
GUI_ACTIONS = (ClickAction, KeyboardAction, DragAction, ScrollAction, GotoAction)
#: Negative test functions not recognisable by their name alone
NEGATIVE_FUNCTIONS = frozenset({'visual.not_exists'})
#: Test statuses that count as a control having passed
PASSING_STATUSES = frozenset({'SUCCESS', 'WARNING'})


def _is_zero(value: Any) -> bool:
    try:
        return float(value) == 0
    except (TypeError, ValueError):
        return False


def is_negative_test(test_def: dict, test_class: type | None = None) -> bool:
    """True if a passing result of this test asserts that something is absent."""
    function = str(test_def.get('function') or '')
    short = function.rsplit('.', 1)[-1]
    if short.endswith('_does_not_exist') or function in NEGATIVE_FUNCTIONS:
        return True
    if short == 'count_max' and _is_zero((test_def.get('parameter') or {}).get('max')):
        return True
    if test_def.get('expect_to_fail'):
        return True
    return bool(getattr(test_class, 'negative', False))


def _describe(action) -> str:
    kind = type(action).__name__.replace('Action', '').lower()
    description = (getattr(action, 'description', '') or '').strip()
    if description:
        return f'{kind} "{description[:60]}"'
    target = getattr(action, 'target', None)
    detail = getattr(target, 'text', None) or getattr(target, 'image', None) if target is not None else None
    detail = detail or getattr(action, 'text', None) or getattr(action, 'key', None)
    return f'{kind} {detail!r}' if detail else kind


@dataclass
class LedgerEntry:
    """What one executed GUI action (or skipped block) says about its own effect."""

    number: int
    label: str
    success: bool
    skipped: bool = False
    effect: str | None = None
    verified: bool | None = None

    def problem(self) -> str | None:
        """Why this action does not support an absence, or None if it does."""
        where = f'action #{self.number} ({self.label})'
        if not self.success:
            return f'{where} failed'
        if self.skipped:
            return f'{where} was skipped by its when: condition'
        if self.verified is False:
            return f'{where} failed its verify:'
        if self.effect == 'unchanged':
            return f'{where} showed no screen change near its input (effect: unchanged)'
        return None


@dataclass
class EffectLedger:
    """The run's record of GUI-action effects and test outcomes, in execution order."""

    entries: list[LedgerEntry] = field(default_factory=list)
    test_statuses: dict[str, str] = field(default_factory=dict)
    # Host-side backend: tests run after the guest quiesced, so remember where each one stood
    cutoffs: dict[str, int] = field(default_factory=dict)

    def record_action(self, action, result) -> None:
        data = getattr(result, 'data', None) or {}
        if isinstance(action, BlockAction):
            if not data.get('skipped'):
                return  # an executed block's children record themselves
        elif not isinstance(action, GUI_ACTIONS):
            return
        self.entries.append(
            LedgerEntry(
                number=len(self.entries) + 1,
                label=_describe(action),
                success=bool(getattr(result, 'success', False)),
                skipped=bool(data.get('skipped')),
                effect=data.get('effect'),
                verified=data.get('verified'),
            )
        )

    def record_test(self, name: str, status: str | None) -> None:
        self.test_statuses[name] = status or 'UNKNOWN'

    def note_deferred(self, name: str) -> None:
        """A test whose evaluation is deferred: only the actions before this point count."""
        self.cutoffs.setdefault(name, len(self.entries))

    def problems_before(self, test_name: str, controls: list[str] | None = None, actions: bool = True) -> list[str]:
        """Reasons the actions (if ``actions``) and controls before ``test_name`` lack proof."""
        reasons = []
        if actions:
            entries = self.entries[: self.cutoffs.get(test_name, len(self.entries))]
            reasons = [problem for entry in entries if (problem := entry.problem())]
        for control in controls or []:
            status = self.test_statuses.get(control)
            if status is None:
                reasons.append(f'control "{control}" did not run before this test')
            elif status not in PASSING_STATUSES:
                reasons.append(f'control "{control}" did not pass ({status})')
        return reasons


def judge_negative_test(ledger: EffectLedger, test_name: str, test_def: dict, test_class, result):
    """Turn a passing negative test into INCONCLUSIVE when its proof is missing.

    Returns the (possibly updated) ActionResult; also records the test's final status.
    """
    data = dict(getattr(result, 'data', None) or {})
    status = data.get('test_status') or ('SUCCESS' if result.success else 'FAILED')
    controls = [c for c in (test_def.get('controls') or []) if isinstance(c, str)]
    negative = is_negative_test(test_def, test_class)
    if result.success and status in PASSING_STATUSES and (controls or negative):
        # The implicit action checks guard absences only; explicit controls count on any test.
        reasons = ledger.problems_before(test_name, controls, actions=negative)
        if reasons:
            status = 'INCONCLUSIVE'
            data.update(test_status=status, inconclusive_reasons=reasons)
            result.data = data
            result.message = f"{result.message} - INCONCLUSIVE: {'; '.join(reasons)}".lstrip(' -')
            log.warning(f"Negative test '{test_name}' passed but is INCONCLUSIVE: {'; '.join(reasons)}")
    ledger.record_test(test_name, status)
    return result
