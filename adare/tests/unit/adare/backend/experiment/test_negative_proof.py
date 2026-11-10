"""Implicit controls for negative tests: INCONCLUSIVE when the act behind an absence is unproven."""

from types import SimpleNamespace

import pytest

from adare.backend.experiment.execution.base import ActionResult
from adare.backend.experiment.negative_proof import EffectLedger, is_negative_test, judge_negative_test
from adare.backend.experiment.test_result_processor import TestResultProcessor
from adare.database.api.event import stored_test_details, stored_test_status
from adare.database.models.run_verdict import compute_result_status
from adare.types.playbook import BlockAction, ClickAction, CommandAction, KeyboardAction, Target
from adarelib.constants import StatusEnum

pytestmark = pytest.mark.unit

ABSENT = {'name': 'gone', 'function': 'standard.file_does_not_exist', 'parameter': {'dst': '/x'}}
PRESENT = {'name': 'there', 'function': 'standard.file_exists', 'parameter': {'dst': '/x'}}


def _click(desc='Delete'):
    return ClickAction(target=Target(text=desc), description=desc)


def _ok(**data):
    return ActionResult(success=True, message='ok', data=data)


def _passed():
    return ActionResult(success=True, message='passed', data={'test_status': 'SUCCESS'})


def _judge(ledger, test_def, result=None, test_class=None):
    return judge_negative_test(ledger, test_def['name'], test_def, test_class, result or _passed())


# ----------------------------------------------------------------------------- which tests are negative


@pytest.mark.parametrize(
    'test_def',
    [
        {'function': 'standard.file_does_not_exist'},
        {'function': 'standard.dir_does_not_exist'},
        {'function': 'visual.not_exists'},
        {'function': 'visual.count_max', 'parameter': {'max': 0}},
        {'function': 'visual.count_max', 'parameter': {'max': '0'}},
        {'function': 'standard.file_exists', 'expect_to_fail': True},
    ],
)
def test_negative_tests(test_def):
    assert is_negative_test(test_def)


@pytest.mark.parametrize(
    'test_def',
    [
        {'function': 'standard.file_exists'},
        {'function': 'visual.count_max', 'parameter': {'max': 2}},
        {'function': 'visual.exists'},
    ],
)
def test_positive_tests(test_def):
    assert not is_negative_test(test_def)


def test_testfunction_can_declare_itself_negative():
    assert is_negative_test({'function': 'mine.cleared'}, SimpleNamespace(negative=True))


# ----------------------------------------------------------------------------- the verdict rule


def test_negative_test_with_proven_actions_stays_success():
    ledger = EffectLedger()
    ledger.record_action(_click(), _ok(effect='changed'))
    ledger.record_action(KeyboardAction(key='delete'), _ok(effect='changed'))
    result = _judge(ledger, ABSENT)
    assert result.data['test_status'] == 'SUCCESS'


@pytest.mark.parametrize(
    ('data', 'reason'),
    [
        ({'skipped': True}, 'skipped'),
        ({'effect': 'unchanged'}, 'no screen change'),
        ({'verified': False, 'effect': 'unchanged'}, 'verify'),
    ],
)
def test_unproven_action_makes_negative_test_inconclusive(data, reason):
    ledger = EffectLedger()
    ledger.record_action(_click(), _ok(**data))
    result = _judge(ledger, ABSENT)
    assert result.success  # not a failure: execution continues
    assert result.data['test_status'] == 'INCONCLUSIVE'
    assert reason in result.data['inconclusive_reasons'][0]
    assert 'Delete' in result.data['inconclusive_reasons'][0]
    assert ledger.test_statuses['gone'] == 'INCONCLUSIVE'


def test_effect_none_is_not_a_problem():
    ledger = EffectLedger()
    ledger.record_action(KeyboardAction(key='alt', effect='none'), _ok(effect='none'))
    assert _judge(ledger, ABSENT).data['test_status'] == 'SUCCESS'


def test_skipped_block_counts_executed_block_does_not():
    ledger = EffectLedger()
    ledger.record_action(BlockAction(actions=[]), _ok())
    assert ledger.entries == []
    ledger.record_action(BlockAction(actions=[]), _ok(skipped=True))
    assert _judge(ledger, ABSENT).data['test_status'] == 'INCONCLUSIVE'


def test_non_gui_actions_are_ignored():
    ledger = EffectLedger()
    ledger.record_action(CommandAction(command='rm /x'), ActionResult(success=True, data={}))
    assert ledger.entries == []


def test_positive_test_is_never_affected_by_actions():
    ledger = EffectLedger()
    ledger.record_action(_click(), _ok(effect='unchanged'))
    assert _judge(ledger, PRESENT).data['test_status'] == 'SUCCESS'


def test_failed_negative_test_stays_failed():
    ledger = EffectLedger()
    ledger.record_action(_click(), _ok(effect='unchanged'))
    failed = ActionResult(success=False, message='exists', data={'test_status': 'FAILED'})
    result = _judge(ledger, ABSENT, failed)
    assert not result.success and result.data['test_status'] == 'FAILED'


def test_explicit_control_must_pass_before():
    ledger = EffectLedger()
    test_def = {**ABSENT, 'controls': ['there']}
    result = _judge(ledger, test_def)
    assert result.data['test_status'] == 'INCONCLUSIVE'
    assert 'did not run' in result.data['inconclusive_reasons'][0]

    ledger = EffectLedger()
    _judge(ledger, PRESENT, ActionResult(success=False, data={'test_status': 'FAILED'}))
    result = _judge(ledger, test_def)
    assert 'did not pass (FAILED)' in result.data['inconclusive_reasons'][0]

    ledger = EffectLedger()
    _judge(ledger, PRESENT)
    assert _judge(ledger, test_def).data['test_status'] == 'SUCCESS'


def test_controls_on_a_positive_test_only_check_the_controls():
    ledger = EffectLedger()
    ledger.record_action(_click(), _ok(effect='unchanged'))
    test_def = {**PRESENT, 'name': 'p2', 'controls': ['missing']}
    reasons = _judge(ledger, test_def).data['inconclusive_reasons']
    assert len(reasons) == 1 and 'missing' in reasons[0]


def test_deferred_test_only_counts_actions_before_its_position():
    ledger = EffectLedger()
    ledger.record_action(_click(), _ok(effect='changed'))
    ledger.note_deferred('gone')
    ledger.record_action(_click('Later'), _ok(effect='unchanged'))  # after the test's position
    assert _judge(ledger, ABSENT).data['test_status'] == 'SUCCESS'


# ----------------------------------------------------------------------------- stored status & verdict


def test_stored_status_is_the_real_outcome():
    assert stored_test_status({'success': True, 'test_status': 'INCONCLUSIVE'}) == StatusEnum.INCONCLUSIVE
    assert stored_test_status({'success': True, 'test_status': 'WARNING'}) == StatusEnum.WARNING
    assert stored_test_status({'success': False, 'test_status': 'ERROR'}) == StatusEnum.ERROR
    assert stored_test_status({'success': False, 'test_status': 'FAILED'}) == StatusEnum.FAILED
    # events from before test_status existed
    assert stored_test_status({'success': False, 'result_category': 'execution_error'}) == StatusEnum.ERROR
    assert stored_test_status({'success': True, 'result_category': 'warning'}) == StatusEnum.WARNING
    assert stored_test_status({'success': True}) == StatusEnum.SUCCESS
    # a failed action never stores a passing status
    assert stored_test_status({'success': False, 'test_status': 'SUCCESS'}) == StatusEnum.FAILED


def test_details_keep_expect_to_fail_outcome_and_reasons():
    details = stored_test_details(
        {
            'test_output': ['found /x'],
            'expect_to_fail': True,
            'original_status': 'FAILED',
            'inconclusive_reasons': ['action #1 (click) was skipped by its when: condition'],
        }
    )
    import json

    lines = json.loads(details)
    assert lines[0] == 'found /x'
    assert 'expect_to_fail: the test itself reported FAILED' in lines
    assert lines[-1].startswith('INCONCLUSIVE: action #1')
    assert stored_test_details({'error_message': 'boom'}) == 'boom'


def _t(success, status):
    return (success, 'a', str(int(status)))


def test_verdict_precedence():
    expected = ['a', 'b']
    inconclusive = _t(True, StatusEnum.INCONCLUSIVE)
    assert compute_result_status([inconclusive, _t(False, StatusEnum.FAILED)], expected) == StatusEnum.FAILED
    # INCONCLUSIVE outranks a missing test
    assert compute_result_status([inconclusive], expected) == StatusEnum.INCONCLUSIVE
    assert compute_result_status([_t(True, StatusEnum.WARNING)], expected) == StatusEnum.TEST_MISSING
    both = [_t(True, StatusEnum.WARNING), (True, 'b', str(int(StatusEnum.INCONCLUSIVE)))]
    assert compute_result_status(both, expected) == StatusEnum.INCONCLUSIVE
    assert compute_result_status([(True, 'a', '2'), (True, 'b', '4')], expected) == StatusEnum.WARNING
    # an ERROR result is a failure
    assert compute_result_status([(True, 'a', str(int(StatusEnum.ERROR)))], ['a']) == StatusEnum.FAILED


# ----------------------------------------------------------------------------- expect_to_fail processing


def _ws(status):
    return {'status': 'success', 'result': {'status': status, 'details': ['d']}}


def test_warning_under_expect_to_fail_is_a_failure():
    result = TestResultProcessor.process_test_result('t', _ws('WARNING'), expect_to_fail=True)
    assert not result.success
    assert result.data['test_status'] == 'FAILED' and result.data['original_status'] == 'WARNING'


def test_expected_failure_is_success_and_keeps_original():
    result = TestResultProcessor.process_test_result('t', _ws('FAILED'), expect_to_fail=True)
    assert result.success and result.data['test_status'] == 'SUCCESS' and result.data['original_status'] == 'FAILED'


def test_error_stays_error_under_expect_to_fail():
    result = TestResultProcessor.process_test_result('t', _ws('ERROR'), expect_to_fail=True)
    assert not result.success and result.data['test_status'] == 'ERROR'


def test_transport_error_is_error():
    result = TestResultProcessor.process_test_result('t', {'status': 'error', 'message': 'ws closed'})
    assert not result.success and result.data['test_status'] == 'ERROR'
