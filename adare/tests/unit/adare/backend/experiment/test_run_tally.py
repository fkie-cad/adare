"""Tests for the DB-derived run tally in ``adare.backend.experiment.run_tally``.

The bug these cover: the run summary was built from ``PlaybookController.action_results``,
which only holds top-level playbook actions, so a ``loop:`` body — and every ``test:``
inside it — was missing from the tally. A ten-iteration loop with four assertions per
iteration reported "Tests: 1/1 passed" instead of 41, and a failure inside an iteration
never showed up in the numbers.
"""

import json

import pytest

pytestmark = pytest.mark.unit

from adare.backend.experiment.print import format_nesting_detail
from adare.backend.experiment.run_tally import (
    EventRow,
    build_tally,
    event_kind,
    load_event_rows,
)
from adarelib.constants import StatusEnum

RUN = "01KYMNJDBDCX3EHAZ9PN2ERXK5"


# --------------------------------------------------------------------------- #
# helpers
# --------------------------------------------------------------------------- #

def make_action(group_id, kind, *, success=True, parent=None, complete=True,
                 sequence_order=0, **extra):
    """Build the start (+ complete) rows of one executed action."""
    rows = [EventRow(
        group_id=group_id, category='action', event_type_specific=f'{kind}_start',
        parent_group_id=parent, sequence_order=sequence_order, **extra,
    )]
    if complete:
        rows.append(EventRow(
            group_id=group_id, category='action', event_type_specific=f'{kind}_complete',
            parent_group_id=parent, success=success, sequence_order=sequence_order, **extra,
        ))
    return rows


def make_test(group_id, *, status=StatusEnum.SUCCESS, parent=None, complete=True):
    """Build the start (+ complete) rows of one executed test."""
    rows = [EventRow(group_id=group_id, category='test',
                     event_type_specific='test_start', parent_group_id=parent)]
    if complete:
        rows.append(EventRow(
            group_id=group_id, category='test', event_type_specific='test_complete',
            parent_group_id=parent,
            success=status in (StatusEnum.SUCCESS, StatusEnum.WARNING),
            test_status=int(status),
        ))
    return rows


def pecmd_shaped_run(*, iterations=10, failing_iterations=()):
    """Recreate the shape of the §5.3 pecmd playbook.

    Top level: 3 commands, 1 test, 1 loop, 1 pull.
    Loop body per iteration: 10 non-test actions (one of them a save_timestamp
    utility) plus 4 tests. Iterations listed in *failing_iterations* fail their
    last test and stop the loop right there.
    """
    loop_id = 'action_3_loopaction'
    rows = []
    for i in range(3):
        rows += make_action(f'action_{i}_commandaction', 'command', sequence_order=i)
    rows += make_test('action_1_actiontestaction')
    rows += make_action('action_4_pullaction', 'pull', sequence_order=4)

    completed = 0
    stopped = False
    for i in range(iterations):
        if stopped:
            break
        for j, kind in enumerate(('action', 'command', 'keyboard', 'idle', 'keyboard',
                                  'keyboard', 'savetimestamp', 'command', 'command')):
            rows += make_action(f'loop_{i}_action_{j}', kind, parent=loop_id, sequence_order=j)
        failing = i in failing_iterations
        for t in range(4):
            last = t == 3
            status = StatusEnum.FAILED if (failing and last) else StatusEnum.SUCCESS
            rows += make_test(f'loop_{i}_test_{t}', status=status, parent=loop_id)
            if failing and last:
                stopped = True
                break
        if not failing:
            completed += 1

    rows += make_action(
        loop_id, 'loop', success=not failing_iterations, sequence_order=3,
        loop_iterations_planned=iterations,
        loop_iterations_completed=completed,
    )
    return rows


# --------------------------------------------------------------------------- #
# event_kind
# --------------------------------------------------------------------------- #

class TestEventKind:
    @pytest.mark.parametrize("specific,expected", [
        ('command_complete', 'command'),
        ('command_start', 'command'),
        ('wait_until_complete', 'wait_until'),
        ('action_complete', 'action'),
        ('pull_changed_files_complete', 'pull_changed_files'),
        ('loop_start', 'loop'),
        ('', ''),
        (None, ''),
    ])
    def test_kind(self, specific, expected):
        assert event_kind(specific) == expected

    def test_pull_changed_files_is_not_the_pull_utility(self):
        """Prefix confusion here would silently drop a real action from the tally."""
        assert event_kind('pull_changed_files_complete') != 'pull'


# --------------------------------------------------------------------------- #
# build_tally
# --------------------------------------------------------------------------- #

class TestLoopBodiesAreCounted:
    def test_pecmd_shape_reports_41_tests_not_1(self):
        tally = build_tally(pecmd_shaped_run())
        assert tally.total_tests == 41
        assert tally.successful_tests == 41
        assert tally.failed_tests == 0
        assert tally.top_level_tests == 1
        assert tally.nested_tests == 40
        assert tally.all_passed is True

    def test_loop_iterations_are_reported(self):
        tally = build_tally(pecmd_shaped_run())
        assert len(tally.loops) == 1
        assert tally.loops[0].iterations_completed == 10
        assert tally.loops[0].iterations_planned == 10
        assert tally.iterations_completed == 10

    def test_actions_include_the_loop_body(self):
        tally = build_tally(pecmd_shaped_run())
        # 3 top-level commands + 1 top-level test (pull is a utility, loop is a
        # container) + per iteration 8 non-utility actions and 4 tests.
        assert tally.top_level_actions == 4
        assert tally.nested_actions == 10 * (8 + 4)
        assert tally.total_actions == 4 + 120


class TestExclusions:
    def test_target_resolution_substeps_are_not_actions(self):
        """find_step/execute_step events belong to their parent click."""
        rows = make_action('click_0', 'click')
        rows += make_action('find_step_1', 'action', parent='click_0', sequence_order=-1)
        rows += make_action('execute_step_1', 'action', parent='click_0', sequence_order=-1)
        tally = build_tally(rows)
        assert tally.total_actions == 1
        assert tally.nested_actions == 0

    @pytest.mark.parametrize("kind", ['pull', 'pause', 'savetimestamp'])
    def test_utility_actions_are_excluded(self, kind):
        tally = build_tally(make_action('u', kind) + make_action('c', 'command'))
        assert tally.total_actions == 1

    def test_containers_are_not_counted_as_actions(self):
        """A container's success is its children's; counting it double-counts."""
        rows = make_action('loop_0', 'loop', loop_iterations_completed=2, loop_iterations_planned=2)
        rows += make_action('block_0', 'block')
        rows += make_action('loop_0_action_0', 'command', parent='loop_0')
        tally = build_tally(rows)
        assert tally.total_actions == 1
        assert tally.nested_actions == 1
        assert len(tally.loops) == 1

    def test_start_and_complete_are_one_unit(self):
        tally = build_tally(make_action('c', 'command'))
        assert tally.total_actions == 1


class TestPartialFailure:
    """The case that matters most and never occurred in the real run."""

    def test_failure_inside_an_iteration_is_visible(self):
        tally = build_tally(pecmd_shaped_run(failing_iterations={3}))
        # Iterations 0..2 pass fully (4 tests each), iteration 3 fails on its 4th
        # test and stops the loop: 12 + 4 nested tests + 1 top-level.
        assert tally.total_tests == 17
        assert tally.failed_tests == 1
        assert tally.successful_tests == 16
        assert tally.all_passed is False

    def test_three_failing_iterations_are_all_counted(self):
        rows = []
        for i in range(10):
            failing = i in (2, 5, 7)
            for t in range(4):
                rows += make_test(
                    f'loop_{i}_test_{t}',
                    status=StatusEnum.FAILED if (failing and t == 3) else StatusEnum.SUCCESS,
                    parent='loop_0',
                )
        rows += make_action('loop_0', 'loop', success=False,
                             loop_iterations_planned=10, loop_iterations_completed=7)
        tally = build_tally(rows)
        assert tally.total_tests == 40
        assert tally.failed_tests == 3
        assert tally.successful_tests == 37
        assert tally.all_passed is False

    def test_a_short_loop_does_not_read_as_all_passed(self):
        """Loop stopped after 8 of 10 iterations with nothing marked failed."""
        rows = make_action('loop_0', 'loop', loop_iterations_planned=10,
                            loop_iterations_completed=8)
        rows += make_test('loop_0_test_0', parent='loop_0')
        tally = build_tally(rows)
        assert tally.failed_tests == 0
        assert tally.all_passed is False
        assert tally.loops[0].fully_iterated is False

    def test_started_but_never_completed_counts_against_the_run(self):
        rows = make_action('c0', 'command')
        rows += make_action('c1', 'command', complete=False)
        rows += make_test('t0', complete=False, parent='loop_0')
        tally = build_tally(rows)
        assert tally.incomplete_actions == 2   # the command and the test action
        assert tally.incomplete_tests == 1
        assert tally.all_passed is False


class TestResultStatusIsAuthoritative:
    def test_warning_is_a_pass(self):
        """Matches ExperimentRun.result_status: WARNING is pass-with-warning."""
        tally = build_tally(make_test('t', status=StatusEnum.WARNING))
        assert tally.successful_tests == 1
        assert tally.failed_tests == 0

    def test_result_status_beats_the_event_success_flag(self):
        rows = [
            EventRow(group_id='t', category='test', event_type_specific='test_start'),
            EventRow(group_id='t', category='test', event_type_specific='test_complete',
                     success=True, test_status=int(StatusEnum.FAILED)),
        ]
        tally = build_tally(rows)
        assert tally.failed_tests == 1

    def test_event_success_used_when_no_result_row_exists(self):
        rows = [
            EventRow(group_id='t', category='test', event_type_specific='test_start'),
            EventRow(group_id='t', category='test', event_type_specific='test_complete',
                     success=False),
        ]
        assert build_tally(rows).failed_tests == 1


class TestEmptyTally:
    def test_no_events_has_no_executions(self):
        tally = build_tally([])
        assert tally.has_executions is False
        assert tally.total_actions == 0
        assert tally.total_tests == 0


# --------------------------------------------------------------------------- #
# load_event_rows against a real (temporary) project schema
# --------------------------------------------------------------------------- #

@pytest.fixture
def project_session(tmp_path):
    """A session on a throwaway SQLite database carrying the project schema."""
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    from adare.database.models.project_models import ProjectBase

    engine = create_engine(f"sqlite:///{tmp_path / 'project.sqlite3'}")
    ProjectBase.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    yield session
    session.close()
    engine.dispose()


def _status(session, status_enum):
    from adare.database.models.project_models import Status

    row = session.query(Status).filter_by(name=status_enum.name).first()
    if row is None:
        row = Status(id=str(int(status_enum)), name=status_enum.name)
        session.add(row)
        session.flush()
    return row


def _add_action_event(session, counter, *, group_id, specific, success=None,
                      parent=None, sequence_order=0, extra=None):
    from adare.database.models.project_models import ActionEvent

    data = {'action_id': group_id, 'sequence_order': sequence_order}
    if success is not None:
        data['success'] = success
    data.update(extra or {})
    session.add(ActionEvent(
        id=f"E{next(counter):025d}",
        event_type='action_event', category='action', experiment_run_id=RUN,
        parent_event_id=parent, success=success, event_group_id=group_id,
        event_type_specific=specific, action_type=specific.rsplit('_', 1)[0],
        action_id=group_id, action_data=json.dumps(data),
    ))


def _add_test_event(session, counter, *, group_id, specific, success=None,
                    status=None, parent=None):
    from adare.database.models.project_models import Result, TestEvent

    result = None
    if status is not None:
        result = Result(id=f"R{next(counter):025d}", status_id=_status(session, status).id)
        session.add(result)
        session.flush()
    session.add(TestEvent(
        id=f"E{next(counter):025d}",
        event_type='test_event', category='test', experiment_run_id=RUN,
        parent_event_id=parent, success=success, event_group_id=group_id,
        event_type_specific=specific, result=result,
    ))


class TestLoadEventRows:
    def test_partial_failure_loop_round_trips_through_the_database(self, project_session):
        """Ten iterations, three of which fail an assertion, read back from SQL."""
        from itertools import count
        counter = count(1)
        loop_id = 'action_0_loopaction'

        _add_action_event(project_session, counter, group_id=loop_id,
                          specific='loop_start', extra={'iteration_count': 10})
        for i in range(10):
            failing = i in (2, 5, 7)
            _add_action_event(project_session, counter, group_id=f'loop_{i}_action_0',
                              specific='command_start', parent=loop_id)
            _add_action_event(project_session, counter, group_id=f'loop_{i}_action_0',
                              specific='command_complete', success=True, parent=loop_id)
            # A target-resolution substep, which must not become an action.
            _add_action_event(project_session, counter, group_id=f'find_step_{i}',
                              specific='action_start', parent=f'loop_{i}_action_0',
                              sequence_order=-1)
            _add_action_event(project_session, counter, group_id=f'find_step_{i}',
                              specific='action_complete', success=True,
                              parent=f'loop_{i}_action_0', sequence_order=-1)
            for t in range(2):
                failed = failing and t == 1
                _add_test_event(project_session, counter, group_id=f'loop_{i}_test_{t}',
                                specific='test_start', parent=loop_id)
                _add_test_event(project_session, counter, group_id=f'loop_{i}_test_{t}',
                                specific='test_complete', success=not failed,
                                status=StatusEnum.FAILED if failed else StatusEnum.SUCCESS,
                                parent=loop_id)
        _add_action_event(project_session, counter, group_id=loop_id,
                          specific='loop_complete', success=False,
                          extra={'iterations_completed': 7, 'actions_executed': 30})
        project_session.commit()

        tally = build_tally(load_event_rows(project_session, RUN))

        assert tally.total_tests == 20
        assert tally.failed_tests == 3
        assert tally.successful_tests == 17
        assert tally.nested_tests == 20
        assert tally.top_level_tests == 0
        # 10 commands + 20 tests; substeps and the loop container excluded.
        assert tally.total_actions == 30
        assert tally.failed_actions == 3
        assert tally.all_passed is False
        assert tally.loops[0].iterations_completed == 7
        assert tally.loops[0].iterations_planned == 10
        assert tally.loops[0].fully_iterated is False

    def test_other_runs_are_not_mixed_in(self, project_session):
        from itertools import count
        counter = count(1)
        _add_action_event(project_session, counter, group_id='a', specific='command_start')
        _add_action_event(project_session, counter, group_id='a',
                          specific='command_complete', success=True)
        project_session.commit()
        assert load_event_rows(project_session, 'SOME-OTHER-RUN') == []


# --------------------------------------------------------------------------- #
# summary rendering
# --------------------------------------------------------------------------- #

class TestFormatNestingDetail:
    def test_nothing_nested_renders_nothing(self):
        tally = build_tally(make_action('c', 'command'))
        assert format_nesting_detail(tally.top_level_actions, tally.nested_actions, tally.loops) == ""

    def test_single_loop(self):
        tally = build_tally(pecmd_shaped_run())
        detail = format_nesting_detail(tally.top_level_tests, tally.nested_tests, tally.loops)
        assert "1 top-level" in detail
        assert "40 in a loop of 10 iterations" in detail

    def test_short_loop_shows_the_shortfall(self):
        rows = make_action('loop_0', 'loop', loop_iterations_planned=10,
                            loop_iterations_completed=8)
        rows += make_test('loop_0_test_0', parent='loop_0')
        tally = build_tally(rows)
        detail = format_nesting_detail(tally.top_level_tests, tally.nested_tests, tally.loops)
        assert "8/10 iterations" in detail

    def test_multiple_loops(self):
        rows = make_action('loop_0', 'loop', loop_iterations_planned=3, loop_iterations_completed=3)
        rows += make_action('loop_1', 'loop', loop_iterations_planned=2, loop_iterations_completed=2)
        rows += make_action('loop_0_a', 'command', parent='loop_0')
        rows += make_action('loop_1_a', 'command', parent='loop_1')
        tally = build_tally(rows)
        detail = format_nesting_detail(tally.top_level_actions, tally.nested_actions, tally.loops)
        assert "2 loops" in detail
        assert "5 iterations" in detail

    def test_block_only_nesting(self):
        rows = make_action('block_0', 'block')
        rows += make_action('block_0_a', 'command', parent='block_0')
        tally = build_tally(rows)
        detail = format_nesting_detail(tally.top_level_actions, tally.nested_actions, tally.loops)
        assert "nested blocks" in detail


class TestSummaryLine:
    """End-to-end rendering of the summary the human reads."""

    @staticmethod
    def _summary(tally, success):
        from adare.backend.experiment.print import ExperimentFlowConsole

        console = ExperimentFlowConsole(disable=True)
        console.log_experiment_summary(
            ulid=RUN, success=success,
            total_actions=tally.total_actions,
            successful_actions=tally.successful_actions,
            failed_actions=tally.failed_actions,
            total_tests=tally.total_tests,
            successful_tests=tally.successful_tests,
            failed_tests=tally.failed_tests,
            duration=683.9, breakdown=tally,
        )
        return console.state.messages['EXPERIMENT_SUMMARY']['message']

    def test_passing_run_reports_every_assertion(self):
        tally = build_tally(pecmd_shaped_run())
        message = self._summary(tally, success=tally.all_passed)
        assert "EXPERIMENT COMPLETED SUCCESSFULLY" in message
        assert "Tests: [bold cyan]41[/bold cyan]/[dim]41[/dim] passed" in message
        assert "40 in a loop of 10 iterations" in message

    def test_failure_inside_an_iteration_is_not_green(self):
        tally = build_tally(pecmd_shaped_run(failing_iterations={3}))
        message = self._summary(tally, success=tally.all_passed)
        assert "EXPERIMENT FAILED" in message
        assert "[bold red]1[/bold red] failed" in message

    def test_incomplete_steps_are_called_out(self):
        rows = make_action('c1', 'command', complete=False)
        rows += make_action('c0', 'command')
        tally = build_tally(rows)
        message = self._summary(tally, success=tally.all_passed)
        assert "never reported completion" in message

    def test_legacy_callers_render_without_a_breakdown(self):
        from adare.backend.experiment.print import ExperimentFlowConsole

        console = ExperimentFlowConsole(disable=True)
        console.log_experiment_summary(
            ulid=RUN, success=True, total_actions=5, successful_actions=5,
            failed_actions=0, total_tests=1, successful_tests=1, failed_tests=0,
            duration=683.9,
        )
        message = console.state.messages['EXPERIMENT_SUMMARY']['message']
        assert "Actions: [bold cyan]5[/bold cyan]/[dim]5[/dim] passed" in message
        assert "top-level" not in message
