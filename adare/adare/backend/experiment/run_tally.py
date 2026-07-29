"""Recompute what an experiment run actually executed, from the persisted events.

The run summary used to be built from ``PlaybookController.action_results``, which
only ever holds *top-level* playbook actions. ``loop:``/``block:`` bodies are
executed by :mod:`adare.backend.experiment.execution.flow_control`, which keeps its
child results in a local list and hands back a single aggregate ``ActionResult``.
A ten-iteration loop containing four ``test:`` entries therefore reported
"Tests: 1/1 passed" while forty assertions had actually run — a 40x understatement
of the evidence behind the run, and a green line even when an iteration failed.

This module recomputes the tally from the event rows written for the run, i.e. the
same tables an auditor would query (``test_events`` -> ``event`` -> ``result`` and
``action_events`` -> ``event``). Nested work is counted exactly once and any
failure inside any iteration lands in the totals.

Counting rules, chosen to match the in-memory semantics they replace:

* a *unit* is one ``event_group_id`` (the start/complete pair of one executed
  action or test), so nothing is double counted;
* ``sequence_order == -1`` marks a target-resolution sub-step (``find_step_*`` /
  ``execute_step_*``) emitted inside a single click/drag — internal machinery, not
  a playbook action, so it is skipped;
* ``pull`` / ``pause`` / ``savetimestamp`` are utility actions and stay out of the
  action totals (mirrors ``PlaybookController._is_utility_action``);
* ``loop`` / ``block`` containers are *not* counted as actions themselves. Their
  success is by definition the conjunction of their children, so counting the
  container would double-count one real failure. Their iteration counts are
  reported separately instead, which is what makes the structure visible;
* a ``test:`` entry counts both as a test and as an action, which is what
  ``_is_countable_action`` did for top-level test actions.
"""

import json
import logging
from collections.abc import Iterable
from dataclasses import dataclass, field
from pathlib import Path

from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import joinedload

from adarelib.constants import StatusEnum

log = logging.getLogger(__name__)

# Target resolution emits find/execute sub-steps as action events with this
# sentinel sequence order. They belong to their parent click, not to the playbook.
INTERNAL_STEP_SEQUENCE = -1

# Actions deliberately kept out of the execution statistics.
UTILITY_KINDS = frozenset({'pull', 'pause', 'savetimestamp'})

# Control-flow containers: their children are the executed work.
CONTAINER_KINDS = frozenset({'loop', 'block'})

# WARNING is pass-with-warning, the same rule ExperimentRun.result_status uses.
PASSING_TEST_STATUSES = frozenset({int(StatusEnum.SUCCESS), int(StatusEnum.WARNING)})


def event_kind(event_type_specific: str | None) -> str:
    """Reduce a specific event type to its action kind.

    ``'command_complete'`` -> ``'command'``, ``'wait_until_start'`` ->
    ``'wait_until'``, ``'action_complete'`` -> ``'action'``.
    """
    name = event_type_specific or ''
    for suffix in ('_complete', '_start'):
        if name.endswith(suffix):
            return name[: -len(suffix)]
    return name


@dataclass(frozen=True)
class EventRow:
    """One persisted event, reduced to the fields the tally needs.

    Kept separate from the ORM models so the counting logic is pure and testable
    without a database.
    """
    group_id: str
    category: str                                   # 'action' | 'test'
    event_type_specific: str
    parent_group_id: str | None = None
    success: bool | None = None
    sequence_order: int | None = None
    test_status: int | None = None                   # StatusEnum value, tests only
    loop_iterations_planned: int | None = None       # from the loop start event
    loop_iterations_completed: int | None = None     # from the loop complete event
    loop_actions_executed: int | None = None

    @property
    def is_complete(self) -> bool:
        return self.event_type_specific.endswith('_complete')


@dataclass(frozen=True)
class LoopSummary:
    """What one ``loop:`` container reported about its iterations."""
    iterations_planned: int | None = None
    iterations_completed: int | None = None
    actions_executed: int | None = None
    completed: bool = False

    @property
    def fully_iterated(self) -> bool:
        """True when the loop ran every iteration it announced."""
        if self.iterations_planned is None or self.iterations_completed is None:
            return True
        return self.iterations_completed >= self.iterations_planned


@dataclass(frozen=True)
class ExperimentTally:
    """Executed actions and tests for one run, split by nesting depth."""
    total_actions: int = 0
    successful_actions: int = 0
    failed_actions: int = 0
    incomplete_actions: int = 0
    top_level_actions: int = 0
    nested_actions: int = 0

    total_tests: int = 0
    successful_tests: int = 0
    failed_tests: int = 0
    incomplete_tests: int = 0
    top_level_tests: int = 0
    nested_tests: int = 0

    loops: tuple[LoopSummary, ...] = field(default_factory=tuple)

    @property
    def has_executions(self) -> bool:
        """True when the run produced something worth tallying."""
        return bool(self.total_actions or self.total_tests)

    @property
    def all_passed(self) -> bool:
        """True only when nothing failed and nothing was left unfinished.

        A started-but-never-completed unit counts against the run: the summary
        must not read green when an action stopped reporting mid-flight.
        """
        return not (
            self.failed_actions or self.failed_tests
            or self.incomplete_actions or self.incomplete_tests
            or any(not loop.fully_iterated for loop in self.loops)
        )

    @property
    def iterations_completed(self) -> int:
        return sum(loop.iterations_completed or 0 for loop in self.loops)

    @property
    def iterations_planned(self) -> int:
        return sum(loop.iterations_planned or 0 for loop in self.loops)


class _Counter:
    """Mutable accumulator for one category (actions or tests)."""

    def __init__(self):
        self.total = 0
        self.successful = 0
        self.failed = 0
        self.incomplete = 0
        self.top_level = 0
        self.nested = 0

    def add(self, *, nested: bool, completed: bool, passed: bool):
        self.total += 1
        if nested:
            self.nested += 1
        else:
            self.top_level += 1
        if not completed:
            self.incomplete += 1
        elif passed:
            self.successful += 1
        else:
            self.failed += 1


def build_tally(rows: Iterable[EventRow]) -> ExperimentTally:
    """Aggregate event rows into an :class:`ExperimentTally`."""
    groups: dict[str, list[EventRow]] = {}
    for row in rows:
        if row.sequence_order == INTERNAL_STEP_SEQUENCE:
            continue
        groups.setdefault(row.group_id, []).append(row)

    actions = _Counter()
    tests = _Counter()
    loops: list[LoopSummary] = []

    for group_rows in groups.values():
        kind = event_kind(group_rows[0].event_type_specific)
        complete = next((row for row in group_rows if row.is_complete), None)
        start = next((row for row in group_rows if not row.is_complete), None)
        nested = any(row.parent_group_id for row in group_rows)

        if kind in CONTAINER_KINDS:
            if kind == 'loop':
                loops.append(LoopSummary(
                    iterations_planned=start.loop_iterations_planned if start else None,
                    iterations_completed=complete.loop_iterations_completed if complete else None,
                    actions_executed=complete.loop_actions_executed if complete else None,
                    completed=complete is not None,
                ))
            continue

        is_test = group_rows[0].category == 'test'
        passed = _group_passed(complete, is_test=is_test)

        if is_test:
            tests.add(nested=nested, completed=complete is not None, passed=passed)

        if kind in UTILITY_KINDS:
            continue
        actions.add(nested=nested, completed=complete is not None, passed=passed)

    return ExperimentTally(
        total_actions=actions.total,
        successful_actions=actions.successful,
        failed_actions=actions.failed,
        incomplete_actions=actions.incomplete,
        top_level_actions=actions.top_level,
        nested_actions=actions.nested,
        total_tests=tests.total,
        successful_tests=tests.successful,
        failed_tests=tests.failed,
        incomplete_tests=tests.incomplete,
        top_level_tests=tests.top_level,
        nested_tests=tests.nested,
        loops=tuple(loops),
    )


def _group_passed(complete: EventRow | None, *, is_test: bool) -> bool:
    """Decide whether a completed unit passed.

    Tests are judged by their persisted ``Result`` status when there is one — that
    is the row an auditor reads — and fall back to the event's success flag.
    """
    if complete is None:
        return False
    if is_test and complete.test_status is not None:
        return complete.test_status in PASSING_TEST_STATUSES
    return bool(complete.success)


def _parse_action_data(raw: str | None) -> dict:
    """Decode ``ActionEvent.action_data``; an unreadable blob yields no metadata."""
    if not raw:
        return {}
    try:
        decoded = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return {}
    return decoded if isinstance(decoded, dict) else {}


def _coerce_int(value) -> int | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def load_event_rows(session, experiment_run_ulid: str) -> list[EventRow]:
    """Read the action and test events of one run into :class:`EventRow` objects."""
    from adare.database.models.project_models import ActionEvent, TestEvent

    rows: list[EventRow] = []

    action_events = (
        session.query(ActionEvent)
        .filter(ActionEvent.experiment_run_id == experiment_run_ulid)
        .all()
    )
    for event in action_events:
        data = _parse_action_data(event.action_data)
        rows.append(EventRow(
            group_id=event.event_group_id or event.action_id or event.id,
            category='action',
            event_type_specific=event.event_type_specific or '',
            parent_group_id=event.parent_event_id,
            success=event.success,
            sequence_order=_coerce_int(data.get('sequence_order')),
            loop_iterations_planned=_coerce_int(data.get('iteration_count')),
            loop_iterations_completed=_coerce_int(data.get('iterations_completed')),
            loop_actions_executed=_coerce_int(data.get('actions_executed')),
        ))

    test_events = (
        session.query(TestEvent)
        .options(joinedload(TestEvent.result))
        .filter(TestEvent.experiment_run_id == experiment_run_ulid)
        .all()
    )
    for event in test_events:
        status = _coerce_int(event.result.status_id) if event.result is not None else None
        rows.append(EventRow(
            group_id=event.event_group_id or event.id,
            category='test',
            event_type_specific=event.event_type_specific or '',
            parent_group_id=event.parent_event_id,
            success=event.success,
            test_status=status,
        ))

    return rows


def tally_from_database(project_path: Path, experiment_run_ulid: str) -> ExperimentTally | None:
    """Build the tally for a run from its project database.

    Returns ``None`` when the events cannot be read, so callers can fall back to
    the in-memory counters rather than print a summary of zeroes.
    """
    from adare.database.api.experiment import ExperimentApi

    try:
        with ExperimentApi(project_path) as api:
            rows = load_event_rows(api._session, experiment_run_ulid)
    except (SQLAlchemyError, OSError, ValueError, KeyError) as e:
        log.warning(f"Could not recompute run tally for {experiment_run_ulid} from the database: {e}")
        return None

    tally = build_tally(rows)
    log.info(
        f"Run tally for {experiment_run_ulid} from database: "
        f"actions {tally.successful_actions}/{tally.total_actions} "
        f"({tally.top_level_actions} top-level, {tally.nested_actions} nested), "
        f"tests {tally.successful_tests}/{tally.total_tests} "
        f"({tally.top_level_tests} top-level, {tally.nested_tests} nested), "
        f"loops {len(tally.loops)} with {tally.iterations_completed} iterations"
    )
    return tally
