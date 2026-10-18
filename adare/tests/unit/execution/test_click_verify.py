"""click ``verify`` / ``retries`` / ``verify_timeout`` (T2F gap G7) and the click settle env.

No VM: the target-resolution executor and the GUI executor are fakes.
"""

import asyncio
import sys
from unittest.mock import AsyncMock, MagicMock

import cattrs
import pytest

pytestmark = pytest.mark.unit

from adare.backend.experiment.execution.base import ActionResult
from adare.backend.experiment.execution.simple_actions import SimpleActionsExecutor
from adare.hypervisor.qemu.utilities.click_timing import click_settle_seconds
from adare.types.playbook import ClickAction, ClickVerify, Target, structure_action


class FakeTargetResolution:
    """Stands in for TargetResolutionExecutor: clicks succeed, the verify target appears on a schedule."""

    def __init__(self, appears_after_click: int | None, click_ok: bool = True):
        self.appears_after_click = appears_after_click
        self.click_ok = click_ok
        self.clicks = 0
        self.use_cache_seen: list = []
        self.target_resolver = MagicMock()
        self.target_resolver.resolve_target = AsyncMock(side_effect=self._resolve)

    async def _resolve(self, target, screenshot_base64, *a, **k):
        if self.appears_after_click is not None and self.clicks >= self.appears_after_click:
            return MagicMock()  # found
        return None

    def begin_resolution(self):
        pass

    async def get_current_screenshot_with_path(self, action_context=None):
        return "ZmFrZQ==", None

    async def execute_action_with_steps(
        self, action, execute_func, parent_action_id=None, event_emitter=None, action_context=None
    ):
        self.use_cache_seen.append(action.target.use_cache)
        if not self.click_ok:
            return ActionResult(success=False, message="Could not resolve target")
        self.clicks += 1
        return ActionResult(success=True, message="click", coordinates=(1, 2), data={})


def _executor(fake):
    return SimpleActionsExecutor(websocket_client=AsyncMock(), target_resolution_executor=fake)


def _click(**kw):
    return ClickAction(target=Target(text="File"), **kw)


@pytest.mark.asyncio
async def test_without_verify_is_a_single_click_and_no_check():
    fake = FakeTargetResolution(appears_after_click=None)
    result = await _executor(fake).execute_click(_click())
    assert result.success and fake.clicks == 1
    fake.target_resolver.resolve_target.assert_not_called()
    assert "click_attempts" not in (result.data or {})


@pytest.mark.asyncio
async def test_verify_passes_first_time():
    fake = FakeTargetResolution(appears_after_click=1)
    action = _click(verify=ClickVerify(exists=Target(text="New Window")), verify_timeout=0)
    result = await _executor(fake).execute_click(action)
    assert result.success and fake.clicks == 1
    assert result.data["click_attempts"] == 1 and result.data["verified"] is True


@pytest.mark.asyncio
async def test_verify_retries_until_effect_seen():
    fake = FakeTargetResolution(appears_after_click=3)
    action = _click(verify=ClickVerify(exists=Target(text="New Window")), retries=3, verify_timeout=0)
    result = await _executor(fake).execute_click(action)
    assert result.success and fake.clicks == 3
    assert result.data["click_attempts"] == 3
    # retries re-resolve with a fresh detection (cache bypass); the first attempt is untouched
    assert fake.use_cache_seen == [None, False, False]


@pytest.mark.asyncio
async def test_verify_fails_after_retries_exhausted():
    fake = FakeTargetResolution(appears_after_click=None)
    action = _click(verify=ClickVerify(exists=Target(text="New Window")), retries=2, verify_timeout=0)
    result = await _executor(fake).execute_click(action)
    assert not result.success and fake.clicks == 3
    assert "Click verify failed after 3 attempt(s)" in result.message
    assert result.data["verified"] is False


@pytest.mark.asyncio
async def test_zero_retries_still_checks_once_and_fails():
    fake = FakeTargetResolution(appears_after_click=None)
    action = _click(verify=ClickVerify(not_exists=Target(text="Dialog")), verify_timeout=0)
    # not_exists of something that is never found is satisfied at once
    assert (await _executor(fake).execute_click(action)).success
    fake2 = FakeTargetResolution(appears_after_click=0)  # "Dialog" is always on screen
    result = await _executor(fake2).execute_click(action)
    assert not result.success and fake2.clicks == 1


@pytest.mark.asyncio
async def test_not_exists_condition_retries_until_gone():
    class Fake(FakeTargetResolution):
        async def _resolve(self, target, screenshot_base64, *a, **k):
            return MagicMock() if self.clicks < 2 else None  # menu closes after the 2nd click

    fake = Fake(appears_after_click=None)
    action = _click(verify=ClickVerify(not_exists=Target(text="Menu")), retries=2, verify_timeout=0)
    result = await _executor(fake).execute_click(action)
    assert result.success and fake.clicks == 2


@pytest.mark.asyncio
async def test_unresolved_target_is_not_retried():
    fake = FakeTargetResolution(appears_after_click=None, click_ok=False)
    action = _click(verify=ClickVerify(exists=Target(text="x")), retries=5, verify_timeout=0)
    result = await _executor(fake).execute_click(action)
    assert not result.success and len(fake.use_cache_seen) == 1


@pytest.mark.asyncio
async def test_verify_polls_within_timeout(monkeypatch):
    """The condition may become true a little after the click: poll until verify_timeout."""

    class Fake(FakeTargetResolution):
        def __init__(self):
            super().__init__(appears_after_click=None)
            self.polls = 0

        async def _resolve(self, target, screenshot_base64, *a, **k):
            self.polls += 1
            return MagicMock() if self.polls >= 3 else None

    fake = Fake()
    action = _click(verify=ClickVerify(exists=Target(text="x")), verify_timeout=5.0)
    sleeps = []

    async def fast_sleep(seconds):
        sleeps.append(seconds)

    monkeypatch.setattr("adare.backend.experiment.execution.gui_actions.asyncio.sleep", fast_sleep)
    result = await _executor(fake).execute_click(action)
    assert result.success and fake.clicks == 1 and fake.polls == 3 and len(sleeps) == 2


# --- playbook syntax -------------------------------------------------------


def test_yaml_syntax_structures_verify():
    action = structure_action(
        {
            "click": {
                "target": {"text": "Library"},
                "verify": {"exists": {"text": "Organize"}},
                "retries": 2,
                "verify_timeout": 4.0,
            },
            "description": "Open the library",
        }
    )
    assert isinstance(action.verify, ClickVerify)
    assert action.verify.exists.text == "Organize" and action.verify.not_exists is None
    assert action.retries == 2 and action.verify_timeout == 4.0


def test_yaml_click_without_verify_is_unchanged():
    action = structure_action({"click": {"target": {"text": "Library"}}})
    assert action.verify is None and action.retries == 0


@pytest.mark.parametrize(
    "body",
    [
        {"target": {"text": "a"}, "retries": 1},  # retries needs verify
        {"target": {"text": "a"}, "verify": {}},  # empty verify
        {"target": {"text": "a"}, "verify": {"exists": {"text": "b"}, "not_exists": {"text": "c"}}},
        {"target": {"text": "a"}, "verify": {"exists": {"text": "b"}}, "retries": -1},
    ],
)
def test_invalid_verify_is_rejected(body):
    with pytest.raises((ValueError, cattrs.errors.BaseValidationError)):
        structure_action({"click": body})


def test_unknown_key_inside_click_is_still_rejected():
    with pytest.raises((ValueError, cattrs.errors.BaseValidationError)):
        structure_action({"click": {"target": {"text": "a"}, "verifyy": {}}})


def test_variables_resolve_inside_verify():
    from adare.backend.experiment.variable_resolver import VariableResolver

    resolver = VariableResolver(variable_registry=None, jinja_env=None)
    action = _click(verify=ClickVerify(exists=Target(text="{{ name }}")))
    resolved = resolver.resolve_action_variables(action, {"name": "Organize"})
    assert resolved.verify.exists.text == "Organize"
    assert action.verify.exists.text == "{{ name }}"


def test_verify_round_trips_through_database_json():
    from adare.database.api.playbook import PlaybookApi

    api = PlaybookApi.__new__(PlaybookApi)
    action = _click(verify=ClickVerify(not_exists=Target(text="Menu")), retries=2, verify_timeout=1.5)
    params = api._action_to_parameters_json(action)
    assert params["verify"] == {"not_exists": {"text": "Menu"}}
    assert params["retries"] == 2 and params["verify_timeout"] == 1.5


# --- move-to-press settle ---------------------------------------------------


def test_settle_default_is_ten_ms(monkeypatch):
    monkeypatch.delenv("ADARE_CLICK_SETTLE_MS", raising=False)
    assert click_settle_seconds() == 0.01


@pytest.mark.parametrize("value,expected", [("120", 0.12), ("0", 0.0), (" 35.5 ", 0.0355)])
def test_settle_env_override(monkeypatch, value, expected):
    monkeypatch.setenv("ADARE_CLICK_SETTLE_MS", value)
    assert click_settle_seconds() == pytest.approx(expected)


@pytest.mark.parametrize("value", ["", "abc", "-5", "999999"])
def test_settle_bad_values_fall_back_to_default(monkeypatch, value):
    monkeypatch.setenv("ADARE_CLICK_SETTLE_MS", value)
    assert click_settle_seconds() == 0.01


def test_qmp_click_sleeps_the_settle_between_move_and_press(monkeypatch):
    """The real QEMUVM click path: move, settle, press, hold, release."""
    if "libvirt" not in sys.modules:
        try:
            import libvirt  # noqa: F401
        except ImportError:
            monkeypatch.setitem(sys.modules, "libvirt", MagicMock())  # CI without libvirt bindings
    from adare.hypervisor.qemu.vm import QEMUVM

    # Don't leave modules imported against the stub behind for other tests.

    vm = QEMUVM.__new__(QEMUVM)
    vm._ensure_tablet_active = AsyncMock()
    vm._normalize_coordinates = MagicMock(return_value=(1, 2))
    vm._send_qmp_command = AsyncMock(return_value={"return": {}})
    sleeps = []

    async def fake_sleep(seconds):
        sleeps.append(seconds)

    monkeypatch.setattr("adare.hypervisor.qemu.vm.asyncio.sleep", fake_sleep)
    monkeypatch.setenv("ADARE_CLICK_SETTLE_MS", "80")
    assert asyncio.run(vm.send_qmp_mouse_click(10, 20))
    assert sleeps == [pytest.approx(0.08), 0.05]
    monkeypatch.delenv("ADARE_CLICK_SETTLE_MS")
    sleeps.clear()
    assert asyncio.run(vm.send_qmp_mouse_click(10, 20))
    assert sleeps == [0.01, 0.05]


@pytest.fixture(autouse=True)
def _forget_modules_imported_against_a_libvirt_stub():
    before = set(sys.modules)
    had_libvirt = "libvirt" in sys.modules
    yield
    if not had_libvirt:
        for name in set(sys.modules) - before:
            if name.startswith("adare.hypervisor.qemu") or name == "libvirt":
                del sys.modules[name]
