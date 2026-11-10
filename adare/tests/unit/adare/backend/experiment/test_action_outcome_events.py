"""Complete events and the forensic log carry how a GUI action went (error, skip, verify, effect, text)."""

import json

import pytest

from adare.backend.experiment.event_manager import EventManager
from adare.backend.experiment.execution.base import ActionResult
from adare.backend.experiment.forensic_reporter import ForensicReporter
from adare.database.models.project_models import ActionEvent
from adare.types.playbook import ClickAction, KeyboardAction, Target

pytestmark = pytest.mark.unit


def _complete(action, result):
    return EventManager().create_action_complete_event(action, 0, 'a1', result).to_dict()


def test_failed_click_carries_error_and_verify_outcome():
    result = ActionResult(
        success=False,
        message='Click verify failed',
        data={'verified': False, 'click_attempts': 3, 'effect': 'unchanged'},
    )
    data = _complete(ClickAction(target=Target(text='OK')), result)
    assert data['error_message'] == 'Click verify failed'
    assert data['verified'] is False and data['click_attempts'] == 3 and data['effect'] == 'unchanged'


def test_skipped_keyboard_is_marked_skipped():
    data = _complete(KeyboardAction(key='delete'), ActionResult(success=True, data={'skipped': True}))
    assert data['skipped'] is True and data['error_message'] is None


def test_effect_info_is_carried():
    info = {'region': [0, 0, 10, 10], 'changed_pixels': 0}
    result = ActionResult(success=True, data={'text': 'hello', 'effect': 'unchanged', 'effect_info': info})
    data = _complete(KeyboardAction(text='hello'), result)
    assert data['text'] == 'hello' and data['effect_info'] == info


def test_forensic_log_shows_text_effect_skip_and_error():
    action_data = {
        'text': 'hello',
        'effect': 'unchanged',
        'effect_info': {'changed_pixels': 0},
        'skipped': True,
        'verified': False,
        'click_attempts': 2,
        'error_message': 'verify failed',
    }
    event = ActionEvent(id='e1', success=False, action_data=json.dumps(action_data))
    details = ForensicReporter()._extract_result_details(event)
    assert details['text_entered'] == 'hello'
    assert details['effect'] == 'unchanged' and details['effect_info'] == {'changed_pixels': 0}
    assert details['skipped'] is True and details['verified'] is False and details['click_attempts'] == 2
    assert details['error'] == 'verify failed'
