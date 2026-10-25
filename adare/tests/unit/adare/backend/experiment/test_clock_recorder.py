"""Tests for guest clock sampling, the clock log, and the interval plumbing on the host."""

import json

import pytest

from adare.backend.experiment.clock import GUEST_UTC_OFFSET_KEY, ClockRecorder, ClockSample, ClockSummary, is_jump
from adare.backend.experiment.test_loader import _attach_guest_utc_offset
from adare.backend.experiment.timestamp_interval import resolve_interval_bounds
from adare.backend.experiment.variable_resolver import VariableResolver
from adare.backend.experiment.websocket_client import WebSocketTimeoutError
from adarelib.common.variables import VariableRegistry
from adarelib.testset.yaml.customtags import YamlTimestamp

pytestmark = pytest.mark.unit


class FakeAgent:
    """In-guest agent stand-in whose clock runs `offset` seconds off the host."""

    def __init__(self, offset=0.0, utc_offset='+02:00'):
        self.connected = True
        self.offset = offset
        self.utc_offset = utc_offset
        self.calls = []

    async def get_timestamp(self, use_local=False, timeout=10.0):
        import time

        self.calls.append(use_local)
        return {'timestamp': time.time() + self.offset, 'timezone': self.utc_offset if use_local else 'UTC'}


class TestClockSample:
    def test_offset_and_uncertainty(self):
        sample = ClockSample(host_before=100.0, guest=160.5, host_after=101.0, source='qga')
        assert sample.offset == pytest.approx(60.0)
        assert sample.uncertainty == pytest.approx(0.5)

    def test_jump_needs_more_than_threshold_plus_uncertainty(self):
        a = ClockSample(100.0, 100.0, 100.2, 'qga')
        assert not is_jump(a, ClockSample(200.0, 200.9, 200.2, 'qga'))
        assert is_jump(a, ClockSample(200.0, 230.0, 200.2, 'qga'))

    def test_summary_stability(self):
        summary = ClockSummary()
        first = ClockSample(0.0, 0.0, 0.1, 'qga', '+02:00')
        summary.add(first, None, 'a')
        assert summary.stable
        assert summary.add(ClockSample(10.0, 40.0, 10.1, 'qga', '+02:00'), first, 'b')
        assert not summary.stable and summary.jumps[0]['at'] == 'b'

    def test_timezone_change_is_unstable(self):
        summary = ClockSummary()
        summary.add(ClockSample(0.0, 0.0, 0.1, 'agent', '+02:00'), None, 'a')
        summary.add(ClockSample(1.0, 1.0, 1.1, 'agent', '+01:00'), None, 'b')
        assert not summary.stable
        assert summary.utc_offsets == ['+02:00', '+01:00']


@pytest.mark.asyncio
class TestClockRecorder:
    async def test_agent_probe_logs_sample_and_timezone(self, tmp_path):
        context = {}
        recorder = ClockRecorder(tmp_path, context)
        agent = FakeAgent(offset=3.0)

        sample = await recorder.probe('before', 'ActionTestAction', 'check', None, agent, vm=None, with_timezone=True)

        assert sample.source == 'agent'
        assert sample.offset == pytest.approx(3.0, abs=0.5)
        assert context[GUEST_UTC_OFFSET_KEY] == '+02:00'
        record = json.loads((tmp_path / 'clock.jsonl').read_text().splitlines()[0])
        assert record['phase'] == 'before' and record['action'] == 'ActionTestAction'
        assert record['guest_utc_offset'] == '+02:00' and record['jump'] is False

    async def test_jump_is_flagged(self, tmp_path):
        recorder = ClockRecorder(tmp_path, {})
        agent = FakeAgent(offset=0.0)
        await recorder.probe('before', 'ClickAction', '', None, agent, vm=None)
        agent.offset = 3600.0  # NTP steps the guest clock by an hour
        await recorder.probe('after', 'ClickAction', '', None, agent, vm=None)

        lines = [json.loads(line) for line in (tmp_path / 'clock.jsonl').read_text().splitlines()]
        assert [line['jump'] for line in lines] == [False, True]
        summary = recorder.write_summary()[None]
        assert not summary['stable'] and summary['jumps'][0]['step'] == pytest.approx(3600.0, abs=1.0)
        assert json.loads((tmp_path / 'clock_summary.json').read_text())['default']['stable'] is False

    async def test_failed_probe_never_raises(self, tmp_path):
        class DeadAgent(FakeAgent):
            async def get_timestamp(self, use_local=False, timeout=10.0):
                raise WebSocketTimeoutError('no answer')

        recorder = ClockRecorder(tmp_path, {})
        assert await recorder.probe('before', 'ClickAction', '', None, DeadAgent(), vm=None) is None
        assert recorder.write_summary()[None]['failed_probes'] == 1

    async def test_no_guest_access_counts_as_failed(self, tmp_path):
        recorder = ClockRecorder(tmp_path, {})
        assert await recorder.probe('before', 'ClickAction', '', None, client=None, vm=None) is None
        assert recorder.write_summary()[None]['failed_probes'] == 1

    async def test_qga_preferred_over_agent(self, tmp_path):
        class QemuVM:
            async def _send_qga_command_via_libvirt(self, command, timeout=5):
                return {
                    'guest-get-time': {'return': 1_000_000_000_000},
                    'guest-get-timezone': {'return': {'zone': 'EST', 'offset': -18000}},
                }[command['execute']]

        vm = QemuVM()
        agent = FakeAgent()
        context = {}

        sample = await ClockRecorder(tmp_path, context).probe(
            'before', 'ActionTestAction', '', None, agent, vm, with_timezone=True
        )

        assert sample.source == 'qga' and sample.guest == 1_000.0
        assert context[GUEST_UTC_OFFSET_KEY] == '-05:00'
        assert agent.calls == []  # QGA reads leave no agent log events

    async def test_disabled_recorder_writes_nothing(self, tmp_path):
        recorder = ClockRecorder(tmp_path, {}, enabled=False)
        assert await recorder.probe('before', 'ClickAction', '', None, FakeAgent(), vm=None) is None
        assert recorder.write_summary() == {}
        assert not (tmp_path / 'clock.jsonl').exists()


class TestIntervalResolution:
    def test_bounds_resolved_from_context(self):
        resolve = lambda template, ctx: template.replace('{{ t0 }}', str(ctx['t0'])).replace('{{ t1 }}', str(ctx['t1']))  # noqa: E731
        metadata = resolve_interval_bounds({'interval': ['{{ t0 }}', '{{ t1 }}']}, resolve, {'t0': 1.5, 't1': 2.5})
        assert metadata['interval'] == ['1.5', '2.5']

    def test_unset_bound_kept_for_runtime(self):
        metadata = resolve_interval_bounds({'interval': ['{{ t0 }}', '{{ t1 }}']}, lambda t, c: '', {'x': 1})
        assert metadata['interval'] == ['{{ t0 }}', '{{ t1 }}']

    def test_interval_tag_becomes_placeholder(self):
        resolver = VariableResolver(variable_registry=VariableRegistry())
        test = {
            'name': 'deleted_at',
            'parameter': {'entry': ['x', YamlTimestamp(after='{{ t0 }}', before='{{ t1 }}', precision=1)]},
        }

        resolved = resolver.process_data(test, {'t0': 100.0, 't1': 105.0})

        placeholder = resolved['parameter']['entry'][1]
        assert placeholder == '{{ t0_resolved }}'
        metadata = resolver.get_placeholder_metadata()['t0_resolved']
        assert metadata['interval'] == ['100.0', '105.0']
        assert metadata['precision'] == 1


class TestGuestUtcOffsetAttachment:
    def test_attached_to_timestamp_placeholders_only(self):
        metadata = {'a_resolved': {'type': 'timestamp'}, 'r_resolved': {'type': 'regex'}}
        _attach_guest_utc_offset(metadata, {GUEST_UTC_OFFSET_KEY: '+02:00'})
        assert metadata['a_resolved']['guest_utc_offset'] == '+02:00'
        assert 'guest_utc_offset' not in metadata['r_resolved']

    def test_latest_offset_wins(self):
        metadata = {'a_resolved': {'type': 'timestamp', 'guest_utc_offset': '+02:00'}}
        _attach_guest_utc_offset(metadata, {GUEST_UTC_OFFSET_KEY: '+01:00'})
        assert metadata['a_resolved']['guest_utc_offset'] == '+01:00'

    def test_nothing_measured(self):
        metadata = {'a_resolved': {'type': 'timestamp'}}
        _attach_guest_utc_offset(metadata, {})
        assert metadata == {'a_resolved': {'type': 'timestamp'}}


@pytest.mark.asyncio
class TestActionExecutorBrackets:
    """execute_action reads the guest clock before and after leaf actions only."""

    def _executor(self):
        from unittest.mock import AsyncMock

        from adare.backend.experiment.action_executor import ActionExecutor, ActionResult

        executor = ActionExecutor()
        executor.clock.probe = AsyncMock(return_value=None)
        ok = ActionResult(success=True, message='')
        executor.simple_actions.execute_idle = AsyncMock(return_value=ok)
        executor.test_actions.execute_test = AsyncMock(return_value=ok)
        executor.flow_control.execute_block = AsyncMock(return_value=ok)
        return executor

    @staticmethod
    def _phases(executor):
        return [
            (c.args[0], c.args[1], c.kwargs.get('with_timezone', False)) for c in executor.clock.probe.call_args_list
        ]

    async def test_leaf_action_is_bracketed(self):
        from adare.types.playbook import IdleAction

        executor = self._executor()
        await executor.execute_action(IdleAction(duration=0.1))
        assert self._phases(executor) == [('before', 'IdleAction', False), ('after', 'IdleAction', False)]

    async def test_test_action_refreshes_timezone_before_only(self):
        from adare.types.playbook import ActionTestAction

        executor = self._executor()
        await executor.execute_action(ActionTestAction(name='t'))
        assert self._phases(executor) == [('before', 'ActionTestAction', True)]

    async def test_container_is_not_bracketed(self):
        from adare.types.playbook import BlockAction

        executor = self._executor()
        await executor.execute_action(BlockAction(actions=[]))
        assert self._phases(executor) == []


class TestIntervalEndToEnd:
    """YAML tag -> host resolver with the runtime context -> guest-side comparison."""

    TEST_YAML = """
name: trashbin_check
function: csv.contains_line
parameter:
  entry:
    - '$I'
    - !timestamp
      after: '{{ deleted_after }}'
      before: '{{ deleted_before }}'
      precision: 1
      format: '%Y-%m-%d %H:%M:%S'
"""

    def _compare(self, row_value: str) -> tuple[bool, str]:
        import attrs
        import yaml

        from adarelib.testset.basictest import BasicTest, Parameter
        from adarelib.testset.yaml.customloader import get_custom_loader

        @attrs.define
        class _Param(Parameter):
            pass

        test = yaml.load(self.TEST_YAML, Loader=get_custom_loader())
        resolver = VariableResolver(variable_registry=VariableRegistry())
        # 2026-10-24 12:00:00.300 .. 12:00:02 UTC, as save_timestamp stores them
        resolved = resolver.process_data(test, {'deleted_after': 1792843200.3, 'deleted_before': 1792843202.0})
        placeholder = resolved['parameter']['entry'][1].strip('{} ')
        metadata = resolver.get_placeholder_metadata()
        _attach_guest_utc_offset(metadata, {GUEST_UTC_OFFSET_KEY: '+02:00'})
        guest_test = BasicTest(name='t', parameter=_Param(), description='', variable_metadata=metadata)
        return guest_test.compare_with_placeholder(placeholder, row_value)

    def test_value_written_during_action(self):
        ok, msg = self._compare('2026-10-24 12:00:01')
        assert ok, msg

    def test_whole_second_truncation_admitted_by_precision(self):
        ok, msg = self._compare('2026-10-24 12:00:00')
        assert ok, msg

    def test_value_from_before_the_action(self):
        ok, msg = self._compare('2026-10-24 11:59:50')
        assert not ok and 'Before interval' in msg
