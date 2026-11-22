"""Host-mode tests must get the placeholder metadata the agent path passes to tests."""

from pathlib import Path

import pytest

from adare.backend.experiment.test_loader import TestLoader
from adarelib.testset.testfunction import TestfunctionLoader

pytestmark = [pytest.mark.unit, pytest.mark.asyncio]

TESTFUNCTIONS = Path(__file__).resolve().parents[5] / 'appdata' / 'testfunctions'


async def test_structure_host_test_keeps_placeholder_metadata():
    contains_line = TestfunctionLoader().import_basictest_subclasses(directory=TESTFUNCTIONS)['csv']['contains_line']
    loader = object.__new__(TestLoader)  # structure_host_test only needs get_test_class
    loader.get_test_class = lambda name: contains_line
    metadata = {'t0_resolved': {'type': 'timestamp', 'interval': ['1792843200.3', '1792843202.0'], 'precision': 1}}
    resolved_test = {
        'name': 'utc_value_in_interval',
        'description': '',
        'parameter': {'dst': '/tmp/utc.csv', 'entry': ['{{ t0_resolved }}']},
        '_VARIABLE_METADATA': metadata,
    }

    test = await loader.structure_host_test('utc_value_in_interval', resolved_test)

    assert test.variable_metadata == metadata
    ok, msg = test.compare_with_placeholder('t0_resolved', '2026-10-24T12:00:01Z')
    assert ok, msg
