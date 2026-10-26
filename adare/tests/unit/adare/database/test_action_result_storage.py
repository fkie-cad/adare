"""Action results are stored without screenshot payloads (they bloated project DBs to 47 GB)."""

from unittest.mock import MagicMock

import pytest

from adare.database.api.playbook import MAX_RESULT_STRING, PlaybookApi, strip_bulky_values

pytestmark = pytest.mark.unit

PNG_B64 = 'iVBORw0KGgo' + 'A' * 200_000


def test_screenshot_image_data_is_replaced():
    result = {
        'coordinates': None,
        'data': {
            'status': 'success',
            'image': {'data': PNG_B64, 'format': 'png'},
            'offset': {'x': 0, 'y': 0},
            'screenshot_path': 'reporting/screenshots/01_desktop.png',
        },
        'execution_time': 1.5,
    }

    stored = strip_bulky_values(result)

    assert stored['data']['image'] == {'data': f'<omitted: {len(PNG_B64)} chars of png data>', 'format': 'png'}
    assert stored['data']['offset'] == {'x': 0, 'y': 0}
    assert stored['data']['screenshot_path'] == 'reporting/screenshots/01_desktop.png'
    assert stored['execution_time'] == 1.5
    assert result['data']['image']['data'] == PNG_B64  # caller's dict is untouched


def test_small_image_data_is_also_replaced():
    stored = strip_bulky_values({'image': {'data': 'abc', 'format': 'png'}})
    assert stored['image']['data'] == '<omitted: 3 chars of png data>'


def test_oversized_strings_are_replaced_anywhere():
    long_text = 'x' * (MAX_RESULT_STRING + 1)
    stored = strip_bulky_values({'details': [{'message': long_text}, 'short'], 'output': long_text})
    assert stored == {
        'details': [{'message': f'<omitted: {len(long_text)} chars>'}, 'short'],
        'output': f'<omitted: {len(long_text)} chars>',
    }


def test_ordinary_results_pass_through():
    result = {'coordinates': [10, 20], 'data': {'status': 'success', 'key': 'enter'}, 'execution_time': 0.2}
    assert strip_bulky_values(result) == result
    assert strip_bulky_values(None) is None


def test_update_action_execution_complete_stores_stripped_result():
    execution = MagicMock()
    api = PlaybookApi.__new__(PlaybookApi)
    api._session = MagicMock()
    api._session.query.return_value.filter.return_value.first.return_value = execution

    api.update_action_execution_complete(
        'exec-id', success=True, result_data={'data': {'image': {'data': PNG_B64, 'format': 'png'}}}
    )

    assert execution.status == 'success'
    assert execution.result_data == {
        'data': {'image': {'data': f'<omitted: {len(PNG_B64)} chars of png data>', 'format': 'png'}}
    }
