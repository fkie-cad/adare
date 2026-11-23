"""A saved timestamp as the expected value of an ordered comparison (saved_timestamps.py)."""

import datetime

import pytest

from adare.backend.experiment.saved_timestamps import keep_point_in_time, saved_timestamp_variable
from adarelib.common.variables import Variable, VariableRegistry, VariableType
from adarelib.testset.valuecompare import is_ordered

pytestmark = pytest.mark.unit

MOMENT = datetime.datetime(2024, 1, 2, 3, 4, 5, tzinfo=datetime.UTC)


@pytest.fixture
def registry():
    return VariableRegistry(
        {
            'started': Variable(MOMENT, VariableType.TIMESTAMP, metadata={'timezone': 'UTC'}),
            'count_before': Variable('3', VariableType.STRING),
        }
    )


def _test(**parameter):
    return {'name': 't', 'function': 'json.value_matches', 'parameter': {'dst': '/data/app/state.json', **parameter}}


@pytest.mark.parametrize(
    ('parameters', 'ordered'),
    [
        ({}, False),
        ({'comparison_type': 'equals', 'value_type': 'auto'}, False),
        ({'comparison_type': 'greater'}, True),
        ({'value_type': 'timestamp'}, True),
        ({'timestamp_epoch': 1601}, True),
        ({'time_format': '%Y-%m-%d'}, True),
        ({'tolerance': 5}, True),
    ],
)
def test_is_ordered(parameters, ordered):
    assert is_ordered(parameters) is ordered


def test_ordered_test_with_a_lone_timestamp_variable(registry):
    test = _test(expected_value='{{ started }}', comparison_type='greater')

    assert saved_timestamp_variable(test, registry) == 'started'


@pytest.mark.parametrize(
    'test',
    [
        _test(expected_value='{{ started }}'),  # not ordered: resolved as before
        _test(expected_value='{{ count_before }}', comparison_type='greater'),  # not a timestamp
        _test(expected_value='at {{ started }}', comparison_type='greater'),  # text around it
        _test(expected_value='{{ unknown }}', comparison_type='greater'),
        _test(expected_value=5, comparison_type='greater'),
        {'name': 't', 'function': 'standard.file_exists'},
    ],
)
def test_other_tests_are_left_alone(test, registry):
    assert saved_timestamp_variable(test, registry) is None


def test_without_a_registry_nothing_is_kept():
    assert saved_timestamp_variable(_test(expected_value='{{ started }}', comparison_type='less'), None) is None


def test_keep_point_in_time_sets_a_placeholder_with_timestamp_metadata(registry):
    resolved = _test(expected_value='1704164645', comparison_type='greater')
    resolved['_VARIABLE_METADATA'] = {'other': {'type': 'regex'}}

    keep_point_in_time(resolved, 'started', registry)

    assert resolved['parameter']['expected_value'] == '{{ started_point_in_time }}'
    metadata = resolved['_VARIABLE_METADATA']['started_point_in_time']
    assert metadata['type'] == 'timestamp'
    assert float(metadata['resolved_value']) == MOMENT.timestamp()  # the registry keeps Unix seconds
    assert metadata['timezone'] == 'UTC'
    assert not metadata['tolerance']
    assert 'other' in resolved['_VARIABLE_METADATA']
