"""Bounded polls that replaced fixed sleeps in the QEMU external-snapshot path."""

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from adare.hypervisor.qemu.mixins import snapshots
from adare.hypervisor.qemu.mixins.snapshots import SnapshotMixin

pytestmark = pytest.mark.unit


class _Clock:
    """Fake monotonic clock advanced by the patched time.sleep."""

    def __init__(self):
        self.now = 0.0
        self.sleeps: list[float] = []

    def monotonic(self):
        return self.now

    def sleep(self, seconds):
        self.sleeps.append(seconds)
        self.now += seconds


@pytest.fixture
def clock():
    c = _Clock()
    with patch.object(snapshots.time, 'monotonic', c.monotonic), patch.object(snapshots.time, 'sleep', c.sleep):
        yield c


def test_guest_sync_wait_returns_as_soon_as_the_process_exits(clock):
    replies = iter([{'exited': False}, {'exited': False}, {'exited': True, 'exitcode': 0}])
    vm = SimpleNamespace(_virsh_agent_return=MagicMock(side_effect=lambda cmd: next(replies)))

    SnapshotMixin._wait_guest_exec_exit(vm, pid=42, timeout=2.0)

    assert clock.now < 0.2  # not the old fixed 2 s
    assert vm._virsh_agent_return.call_args_list[0].args[0] == {
        'execute': 'guest-exec-status',
        'arguments': {'pid': 42},
    }


def test_guest_sync_wait_never_exceeds_the_old_fixed_wait(clock):
    vm = SimpleNamespace(_virsh_agent_return=MagicMock(return_value={'exited': False}))
    SnapshotMixin._wait_guest_exec_exit(vm, pid=42, timeout=2.0)
    assert clock.now == pytest.approx(2.0)


def test_guest_sync_wait_without_a_pid_keeps_the_fixed_wait(clock):
    vm = SimpleNamespace(_virsh_agent_return=MagicMock())
    SnapshotMixin._wait_guest_exec_exit(vm, pid=None, timeout=2.0)
    assert clock.now == pytest.approx(2.0)
    vm._virsh_agent_return.assert_not_called()


@pytest.mark.parametrize(
    ('stdout', 'returncode', 'expected'),
    [
        ('{"return": {"pid": 7}}', 0, {'pid': 7}),
        ('{"return": {}}', 0, {}),
        ('error: guest agent is not connected', 1, {}),
        ('not json', 0, {}),
        ('[1, 2]', 0, {}),
    ],
)
def test_virsh_agent_return_parses_the_return_object(stdout, returncode, expected):
    vm = SimpleNamespace(vm_name='dom')
    completed = SimpleNamespace(stdout=stdout, returncode=returncode)
    with patch.object(snapshots.subprocess, 'run', return_value=completed) as run:
        assert SnapshotMixin._virsh_agent_return(vm, {'execute': 'guest-ping'}) == expected
    assert run.call_args.args[0][:3] == ['virsh', 'qemu-agent-command', 'dom']
