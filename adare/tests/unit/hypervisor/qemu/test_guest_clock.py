"""Tests for reading and resyncing the guest clock through libvirt's guest-agent channel."""

import libvirt
import pytest

from adare.hypervisor.exceptions import HypervisorException
from adare.hypervisor.qemu import guest_clock

pytestmark = pytest.mark.unit


class FakeAgentVM:
    """QEMU VM stand-in answering QGA commands the way _send_qga_command_via_libvirt does."""

    def __init__(self, replies):
        self.replies = replies
        self.sent = []

    async def _send_qga_command_via_libvirt(self, command, timeout=5):
        self.sent.append((command['execute'], timeout))
        return self.replies[command['execute']]


class FakeDomain:
    def __init__(self, failures=0, error='Guest agent is not responding'):
        self.failures = failures
        self.error = error
        self.times = []

    def setTime(self, value):  # noqa: N802 -- libvirt's name
        self.times.append(value)
        if self.failures:
            self.failures -= 1
            raise libvirt.libvirtError(self.error)


class FakeRestoredVM:
    def __init__(self, domain):
        self.domain = domain

    def _ensure_libvirt_domain(self):
        if self.domain is None:
            raise HypervisorException('domain gone')
        return self.domain


@pytest.fixture(autouse=True)
def no_sleep(monkeypatch):
    monkeypatch.setattr(guest_clock.time, 'sleep', lambda s: None)
    # The restored guest's clock, 90 s behind.
    monkeypatch.setattr(guest_clock, '_stale_guest_time', lambda domain: guest_clock.time.time() - 90)


@pytest.mark.asyncio
async def test_read_time_and_offset():
    vm = FakeAgentVM(
        {
            'guest-get-time': {'return': 1_700_000_000_123_456_789},
            'guest-get-timezone': {'return': {'zone': 'IST', 'offset': 19800}},
        }
    )
    assert await guest_clock.read_guest_time(vm) == pytest.approx(1_700_000_000.123456789)
    assert await guest_clock.read_guest_utc_offset(vm) == '+05:30'


@pytest.mark.asyncio
async def test_west_of_utc_offset():
    vm = FakeAgentVM({'guest-get-timezone': {'return': {'zone': 'EDT', 'offset': -14400}}})
    assert await guest_clock.read_guest_utc_offset(vm) == '-04:00'


@pytest.mark.asyncio
async def test_agent_error_raises():
    vm = FakeAgentVM({'guest-get-time': {'error': {'desc': 'Guest agent is not connected'}}})
    with pytest.raises(guest_clock.GuestClockError, match='not connected'):
        await guest_clock.read_guest_time(vm)


def test_resync_sets_host_time_and_logs_how_far_behind(caplog):
    domain = FakeDomain()
    with caplog.at_level('INFO', logger=guest_clock.__name__):
        assert guest_clock.resync_guest_clock(FakeRestoredVM(domain))
    (value,) = domain.times
    assert set(value) == {'seconds', 'nseconds'} and 0 <= value['nseconds'] < 1_000_000_000
    assert 'was +90.0' in caplog.text


def test_resync_retries_until_agent_reconnects():
    domain = FakeDomain(failures=3)
    assert guest_clock.resync_guest_clock(FakeRestoredVM(domain))
    assert len(domain.times) == 4


def test_rtc_reinjection_unavailable_still_counts_as_set():
    # aarch64 virt: libvirt set the time, then its x86-only RTC step failed.
    error = "unable to execute QEMU command 'rtc-reset-reinjection': not available for this machine"
    domain = FakeDomain(failures=1, error=error)
    assert guest_clock.resync_guest_clock(FakeRestoredVM(domain))
    assert len(domain.times) == 1


def test_resync_gives_up_without_raising():
    assert not guest_clock.resync_guest_clock(FakeRestoredVM(FakeDomain(failures=100)))
    assert not guest_clock.resync_guest_clock(FakeRestoredVM(None))
