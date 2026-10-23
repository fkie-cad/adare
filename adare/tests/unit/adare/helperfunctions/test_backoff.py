"""Poll-interval backoff used by the VM wait loops."""

from itertools import islice
from unittest.mock import patch

import pytest

from adare.helperfunctions.backoff import backoff_delays
from adare.hypervisor.qemu.vm_creator import qga_utils

pytestmark = pytest.mark.unit


def test_starts_short_grows_geometrically_and_caps():
    delays = list(islice(backoff_delays(initial=0.05, factor=1.5, cap=0.5), 10))
    assert delays[:4] == pytest.approx([0.05, 0.075, 0.1125, 0.16875])
    assert all(b >= a for a, b in zip(delays, delays[1:], strict=False))
    assert max(delays) == 0.5
    assert delays[-3:] == [0.5, 0.5, 0.5]  # stays at the cap forever


def test_doubling_variant():
    assert list(islice(backoff_delays(initial=0.1, factor=2.0, cap=2.0), 7)) == pytest.approx(
        [0.1, 0.2, 0.4, 0.8, 1.6, 2.0, 2.0]
    )


def test_initial_above_cap_is_clamped():
    assert list(islice(backoff_delays(initial=5.0, cap=1.0), 2)) == [1.0, 1.0]


@pytest.mark.parametrize('kwargs', [{'initial': 0}, {'cap': 0}, {'factor': 0.5}])
def test_rejects_degenerate_parameters(kwargs):
    with pytest.raises(ValueError):
        next(backoff_delays(**kwargs))


def test_qga_exec_polls_quickly_then_backs_off_to_poll_interval():
    """A command that finishes after a few polls costs a fraction of a second, not n * 0.5 s."""
    statuses = iter([{'exited': False}] * 8 + [{'exited': True, 'exitcode': 0, 'out-data': 'b2s='}])

    def fake_command(_sock, execute, _args=None, **_kw):
        return {'pid': 7} if execute == 'guest-exec' else next(statuses)

    with patch.object(qga_utils, '_command', side_effect=fake_command), patch.object(qga_utils.time, 'sleep') as sleep:
        assert qga_utils.qga_exec('sock', 'true', poll_interval=0.5) == (0, 'ok', '')

    slept = [c.args[0] for c in sleep.call_args_list]
    assert len(slept) == 8
    assert slept[0] == pytest.approx(0.05)
    assert max(slept) == 0.5
