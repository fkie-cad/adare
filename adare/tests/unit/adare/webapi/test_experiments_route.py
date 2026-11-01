"""GET /api/experiments/{name} accepts a short name or a ``Project.experiment`` dotnotation.

Links built from run rows (Runs list, Environment page) carry the dotnotation; the
Experiments list links with the short name. Both must resolve.
"""

from unittest.mock import MagicMock, patch

import pytest

from adare.core.result import Result
from adare.webapi.routes.experiments import get_experiment

pytestmark = pytest.mark.unit

NOT_FOUND = Result.fail(code='ExperimentNotFoundError', message='not found', solutions=[])


def _show(by_dotnotation: Result, by_name: Result) -> MagicMock:
    show = MagicMock()
    show.get_experiment.side_effect = lambda name=None, ulid=None, dotnotation=None: (
        by_dotnotation if dotnotation is not None else by_name
    )
    return show


def _call(name: str, show: MagicMock) -> dict:
    api = MagicMock()
    api.show = show
    with patch('adare.webapi.routes.experiments._api', return_value=api):
        return get_experiment(name)


def test_dotnotation_is_resolved_by_dotnotation():
    show = _show(Result.ok({'name': 'exp'}), NOT_FOUND)
    resp = _call('Proj.exp', show)
    assert resp['success'] is True
    show.get_experiment.assert_called_once_with(dotnotation='Proj.exp')


def test_short_name_is_resolved_by_name():
    show = _show(NOT_FOUND, Result.ok({'name': 'exp'}))
    resp = _call('exp', show)
    assert resp['success'] is True
    show.get_experiment.assert_called_once_with(name='exp')


def test_dotted_short_name_falls_back_to_name_lookup():
    show = _show(NOT_FOUND, Result.ok({'name': 'v1.2'}))
    resp = _call('v1.2', show)
    assert resp['success'] is True
    assert show.get_experiment.call_count == 2


def test_unknown_experiment_reports_not_found():
    resp = _call('Proj.missing', _show(NOT_FOUND, NOT_FOUND))
    assert resp['success'] is False
    assert resp['error']['code'] == 'ExperimentNotFoundError'
