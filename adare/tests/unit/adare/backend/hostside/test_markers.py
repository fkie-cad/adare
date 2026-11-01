"""Step markers into a qemufile run directory (skipped when qfm is not importable)."""

import json

import pytest

from adare.backend.hostside import markers

pytestmark = pytest.mark.unit

try:
    markers.import_qfm()
except markers.MarkerUnavailable:
    pytest.skip('qfm (qemufile) not importable', allow_module_level=True)


def test_markers_are_valid_qfm_events(tmp_path):
    sink = markers.MarkerSink(tmp_path / 'qfm', 'RUN1', {'name': 't'})
    sink.step_start(1, 'ClickAction', detail='target.text=Documents')
    sink.step_end(1, 'ClickAction', True)
    sink.close()
    events = [json.loads(line) for line in (tmp_path / 'qfm' / 'events.jsonl').read_text().splitlines()]
    assert [e['data']['marker'] for e in events] == ['adare.step.start', 'adare.step.end']
    first = events[0]
    assert first['type'] == 'marker' and first['source'] == 'orchestrator'
    assert isinstance(first['t_mono_ns'], int) and first['t_wall'].endswith('Z')
    assert events[1]['t_mono_ns'] >= first['t_mono_ns']

    from qfm.store import EventReader

    assert EventReader(tmp_path / 'qfm').validate()['invalid'] == 0


def test_null_sink_is_inert():
    sink = markers.NullMarkerSink()
    sink.marker('x')
    sink.step_start(1, 'A')
    sink.step_end(1, 'A', True)
