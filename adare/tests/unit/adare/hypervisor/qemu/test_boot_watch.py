"""A guest that booted without a guest agent fails fast instead of being retried.

From the host, a missing agent and a late one look identical; the guest's screen
tells them apart. These tests pin the still-screen measure and the decision the
boot loop takes from it.
"""

import io
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from PIL import Image, ImageDraw

from adare.hypervisor.exceptions import GuestAgentMissingException, GuestAgentTimeoutException
from adare.hypervisor.qemu.boot_watch import BootScreenWatch
from adare.hypervisor.qemu.lifecycle import QEMULifecycleStrategy

pytestmark = pytest.mark.unit


def _frame(color=(40, 40, 40), box=None, text_at=None) -> bytes:
    """A 1024x768 'greeter': a panel, optionally a moved box or a small clock change."""
    image = Image.new('RGB', (1024, 768), color)
    draw = ImageDraw.Draw(image)
    draw.rectangle((300, 250, 724, 520), fill=(230, 230, 230))
    if box is not None:
        draw.rectangle(box, fill=(200, 30, 30))
    if text_at is not None:
        draw.rectangle((text_at, 5, text_at + 8, 15), fill=(255, 255, 255))
    buf = io.BytesIO()
    image.save(buf, 'PPM')
    return buf.getvalue()


def _uniform() -> bytes:
    buf = io.BytesIO()
    Image.new('RGB', (1024, 768), (0, 0, 0)).save(buf, 'PPM')
    return buf.getvalue()


@pytest.fixture
def clock():
    now = [1000.0]
    with patch('adare.hypervisor.qemu.boot_watch.time.monotonic', side_effect=lambda: now[0]):
        yield now


class TestSettledFor:
    def test_a_still_screen_counts_up(self, clock):
        watch = BootScreenWatch(MagicMock())
        watch.observe(_frame())
        clock[0] += 30
        watch.observe(_frame())
        clock[0] += 45
        assert watch.settled_for() == 75

    def test_a_clock_tick_does_not_reset_it(self, clock):
        watch = BootScreenWatch(MagicMock())
        watch.observe(_frame(text_at=500))
        clock[0] += 60
        watch.observe(_frame(text_at=510))
        assert watch.settled_for() == 60

    def test_a_real_change_restarts_it(self, clock):
        watch = BootScreenWatch(MagicMock())
        watch.observe(_frame())
        clock[0] += 60
        watch.observe(_frame(box=(0, 0, 400, 300)))
        clock[0] += 5
        assert watch.settled_for() == 5

    def test_a_blank_screen_never_counts(self, clock):
        watch = BootScreenWatch(MagicMock())
        watch.observe(_uniform())
        clock[0] += 120
        watch.observe(_uniform())
        assert watch.settled_for() == 0

    def test_the_picture_after_a_blank_starts_fresh(self, clock):
        watch = BootScreenWatch(MagicMock())
        watch.observe(_uniform())
        clock[0] += 120
        watch.observe(_frame())
        clock[0] += 10
        assert watch.settled_for() == 10

    def test_save_last_writes_a_png(self, tmp_path):
        watch = BootScreenWatch(MagicMock())
        assert watch.save_last(tmp_path / 'none.png') is None
        watch.observe(_frame())
        path = watch.save_last(tmp_path / 'shot.png')
        assert Image.open(path).format == 'PNG'

    @pytest.mark.asyncio
    async def test_a_failed_screendump_is_skipped(self):
        vm = MagicMock()
        vm.send_qmp_screenshot = AsyncMock(return_value=(False, 'no display'))
        watch = BootScreenWatch(vm)
        await watch.sample()
        assert watch.settled_for() == 0


def _context(guest_platform: str):
    vm = MagicMock()
    vm.vm_name = 'test-vm'
    vm.start = AsyncMock()
    vm.wait_until_fully_booted = AsyncMock(return_value=False)
    return SimpleNamespace(
        vm=vm,
        playbook=None,
        guest_platform=guest_platform,
        user_interrupt_event=None,
        experiment_run_ulid='01TEST',
        experiment_run_directory=None,
    )


@pytest.mark.asyncio
class TestBootLoopDecision:
    @pytest.fixture(autouse=True)
    def _loop(self, monkeypatch, tmp_path):
        monkeypatch.setattr(QEMULifecycleStrategy, '_boot_attempts', classmethod(lambda cls: 3))
        monkeypatch.setattr(QEMULifecycleStrategy, '_ready_timeout_for_attempt', classmethod(lambda cls, a, p=None: 1))
        monkeypatch.setattr(
            QEMULifecycleStrategy, '_boot_screenshot_path', staticmethod(lambda ctx: tmp_path / 's.png')
        )
        monkeypatch.setattr(
            'adare.backend.experiment.execution.gui_executor_factory.resolve_gui_execution_mode', lambda vm, s: None
        )
        self.strategy = QEMULifecycleStrategy.__new__(QEMULifecycleStrategy)
        self.strategy._reset_vm_for_boot_retry = AsyncMock()
        self.tmp_path = tmp_path

    def _settled(self, seconds: float):
        def make(vm):
            watch = BootScreenWatch(vm)
            watch.run = AsyncMock()
            watch.settled_for = MagicMock(return_value=seconds)
            watch.observe(_frame())
            return watch

        return patch('adare.hypervisor.qemu.lifecycle.BootScreenWatch', side_effect=make)

    async def test_linux_guest_idle_on_its_screen_is_not_retried(self):
        ctx = _context('linux')
        with self._settled(90), pytest.raises(GuestAgentMissingException) as err:
            await self.strategy.start_and_initialize_vm(ctx, rerun_file_transfer_on_retry=False)
        assert ctx.vm.start.await_count == 1
        self.strategy._reset_vm_for_boot_retry.assert_not_awaited()
        assert 'no qemu-guest-agent' in str(err.value) and str(self.tmp_path / 's.png') in str(err.value)
        assert (self.tmp_path / 's.png').exists()

    async def test_linux_guest_still_changing_keeps_the_retries(self):
        ctx = _context('linux')
        with self._settled(10), pytest.raises(GuestAgentTimeoutException) as err:
            await self.strategy.start_and_initialize_vm(ctx, rerun_file_transfer_on_retry=False)
        assert not isinstance(err.value, GuestAgentMissingException)
        assert ctx.vm.start.await_count == 3

    async def test_windows_is_never_judged_by_its_screen(self):
        ctx = _context('windows')
        with (
            patch('adare.hypervisor.qemu.lifecycle.BootScreenWatch') as watch_cls,
            pytest.raises(GuestAgentTimeoutException) as err,
        ):
            await self.strategy.start_and_initialize_vm(ctx, rerun_file_transfer_on_retry=False)
        watch_cls.assert_not_called()
        assert not isinstance(err.value, GuestAgentMissingException)
        assert ctx.vm.start.await_count == 3
