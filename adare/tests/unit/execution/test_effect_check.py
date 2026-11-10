"""Automatic effect check of GUI actions (region diff, settle polling, evidence, strict/warn/off).

No VM: frames are synthetic images, target resolution and the GUI executor are fakes.
"""

import base64
from types import SimpleNamespace
from unittest.mock import AsyncMock

import cv2
import numpy as np
import pytest

from adare.backend.experiment.execution.effect_check import (
    EffectProbe,
    box_around,
    resolve_effect_mode,
    screen_without_edges,
)
from adare.backend.experiment.execution.simple_actions import SimpleActionsExecutor
from adare.helperfunctions.image import count_changed_pixels, decode_base64_image
from adare.types.playbook import ClickVerify, KeyboardAction, ScrollAction, Settings, Target

pytestmark = pytest.mark.unit

W, H = 1280, 800


def frame(*rects) -> str:
    """A grey screen with white rectangles (x, y, w, h), as base64 PNG."""
    img = np.full((H, W, 3), 60, dtype=np.uint8)
    for x, y, w, h in rects:
        img[y : y + h, x : x + w] = 255
    ok, buf = cv2.imencode('.png', img)
    assert ok
    return base64.b64encode(buf.tobytes()).decode()


CLOCK = (W - 90, H - 30, 80, 24)  # bottom-right taskbar clock


class FakeTR:
    """Target resolution stand-in: hands out frames in order (the last one repeats)."""

    def __init__(self, frames, resolution_frame=None, screenshots_dir=None):
        self.frames = list(frames)
        self.resolution_frame = resolution_frame
        self.screenshots_dir = screenshots_dir
        self.captures = 0

    async def capture_frame(self):
        self.captures += 1
        return self.frames.pop(0) if len(self.frames) > 1 else self.frames[0]


# ----------------------------------------------------------------------------- regions


def test_box_around_point_is_clamped_to_screen():
    x, y, w, h = box_around([(5, 5)], W, H)
    assert (x, y) == (0, 0) and w == int(W * 0.25) and h == int(H * 0.25)
    x, y, w, h = box_around([(W - 1, H - 1)], W, H)
    assert x + w == W and y + h == H


def test_box_around_two_points_covers_both():
    x, y, w, h = box_around([(100, 100), (1100, 700)], W, H)
    assert x <= 100 and y <= 100 and x + w >= 1100 and y + h >= 700


def test_screen_without_edges_drops_panels():
    x, y, w, h = screen_without_edges(W, H)
    assert x > 0 and y > 0 and x + w < W and y + h < H
    cx, cy, cw, ch = CLOCK
    assert cy >= y + h  # the clock lies outside the compared region


def test_resolve_effect_mode_defaults_to_warn():
    assert resolve_effect_mode(None) == 'warn'
    assert resolve_effect_mode(Settings(effect_check='strict')) == 'strict'
    assert resolve_effect_mode(Settings(effect_check='prove')) == 'prove'
    with pytest.raises(ValueError):
        Settings(effect_check='paranoid')


@pytest.mark.parametrize('written', ['off', "'off'", 'no', 'false'])
def test_unquoted_yaml_off_parses_as_off(tmp_path, written):
    """YAML 1.1 loads a bare ``off`` as False; it must still mean off, never warn."""
    from adare.types.playbook import parse_playbook

    path = tmp_path / 'playbook.yml'
    path.write_text(f"settings:\n  effect_check: {written}\nactions:\n  - idle:\n      duration: 0.1\n")
    settings = parse_playbook(path).settings
    assert settings.effect_check == 'off'
    assert resolve_effect_mode(settings) == 'off'


def test_effect_mode_false_is_off_not_warn():
    assert resolve_effect_mode(SimpleNamespace(effect_check=False)) == 'off'


# ----------------------------------------------------------------------------- region diff


def test_count_changed_pixels_only_inside_region():
    before = decode_base64_image(frame())
    after = decode_base64_image(frame((600, 380, 40, 40), CLOCK))
    assert count_changed_pixels(before, after, box_around([(620, 400)], W, H)) == 1600
    # a click far from the clock: the clock ticking is not a change
    assert count_changed_pixels(before, decode_base64_image(frame(CLOCK)), box_around([(620, 400)], W, H)) == 0


# ----------------------------------------------------------------------------- probe


@pytest.mark.asyncio
async def test_changed_when_screen_changes_near_the_click():
    tr = FakeTR([frame(), frame((600, 380, 40, 40))])
    probe = EffectProbe(tr, settle_timeout=0)
    probe.begin_action()
    await probe.arm([(620, 400)])
    data = await probe.settle('click')
    assert data['effect'] == 'changed'
    assert data['effect_info']['changed_pixels'] >= 1600


@pytest.mark.asyncio
async def test_unchanged_when_only_the_clock_changes_and_evidence_is_kept(tmp_path):
    tr = FakeTR([frame(), frame(CLOCK)], screenshots_dir=tmp_path)
    probe = EffectProbe(tr, settle_timeout=0)
    probe.begin_action()
    await probe.arm([(620, 400)])
    data = await probe.settle('click Delete')
    assert data['effect'] == 'unchanged'
    evidence = data['effect_info']['evidence']
    assert evidence.endswith('.webp') and (tmp_path / evidence.rsplit('/', 1)[-1]).is_file()


@pytest.mark.asyncio
async def test_settle_polls_until_a_late_redraw():
    tr = FakeTR([frame(), frame(), frame(), frame((600, 380, 40, 40))])
    probe = EffectProbe(tr, settle_timeout=2.0)
    probe.begin_action()
    await probe.arm([(620, 400)])
    data = await probe.settle('click')
    assert data['effect'] == 'changed' and data['effect_info']['polls'] == 3


@pytest.mark.asyncio
async def test_resolution_frame_is_reused_as_before():
    tr = FakeTR([frame((600, 380, 40, 40))])
    probe = EffectProbe(tr, settle_timeout=0)
    probe.begin_action()
    tr.resolution_frame = frame()  # set by target resolution during the action
    await probe.arm([(620, 400)])
    assert tr.captures == 0
    assert (await probe.settle('click'))['effect'] == 'changed'


@pytest.mark.asyncio
async def test_keyboard_sees_a_change_far_from_the_last_click():
    # LibreOffice: a click in the Options dialog, alt+o closes it, then text is typed into the
    # document (or a Save dialog) far from that click; the last click's box would miss it
    tr = FakeTR([frame()])
    probe = EffectProbe(tr, settle_timeout=0)
    await probe.arm([(200, 200)])
    probe.begin_action()
    tr.frames = [frame(), frame((1000, 600, 40, 40))]
    await probe.arm(whole_screen=True)
    assert (await probe.settle('keyboard'))['effect'] == 'changed'


@pytest.mark.asyncio
async def test_keyboard_ignores_the_panel_clock():
    tr = FakeTR([frame(), frame(CLOCK)])
    probe = EffectProbe(tr, settle_timeout=0)
    probe.begin_action()
    await probe.arm(whole_screen=True)
    assert (await probe.settle('keyboard'))['effect'] == 'unchanged'


@pytest.mark.asyncio
async def test_scroll_uses_last_pointer_box():
    tr = FakeTR([frame()])
    probe = EffectProbe(tr, settle_timeout=0)
    await probe.arm([(200, 200)])
    probe.begin_action()
    tr.frames = [frame(), frame((1000, 600, 40, 40))]  # change far from the pointer
    await probe.arm()
    assert (await probe.settle('scroll'))['effect'] == 'unchanged'


@pytest.mark.asyncio
async def test_off_mode_does_nothing():
    tr = FakeTR([frame()])
    probe = EffectProbe(tr, mode='off')
    await probe.arm([(1, 1)])
    assert await probe.settle() == {} and tr.captures == 0


# ----------------------------------------------------------------------------- GUI actions


class Settings_:
    def __init__(self, mode):
        self.effect_check = mode


class Playbook_:
    def __init__(self, mode):
        self.settings = Settings_(mode)


def _executor(tr, mode='warn', gui_status='success'):
    executor = SimpleActionsExecutor(
        websocket_client=AsyncMock(), target_resolution_executor=tr, playbook=Playbook_(mode)
    )
    executor.effect_probe.settle_timeout = 0
    executor.gui_executor = AsyncMock()
    executor.gui_executor.keyboard = AsyncMock(return_value={'status': gui_status})
    executor.gui_executor.scroll = AsyncMock(return_value={'status': gui_status})
    return executor


@pytest.mark.asyncio
async def test_keyboard_unchanged_warns_by_default():
    result = await _executor(FakeTR([frame()])).execute_keyboard(KeyboardAction(key='delete'))
    assert result.success and result.data['effect'] == 'unchanged'


@pytest.mark.asyncio
async def test_keyboard_unchanged_fails_under_strict():
    result = await _executor(FakeTR([frame()]), mode='strict').execute_keyboard(KeyboardAction(key='delete'))
    assert not result.success and 'effect_check: strict' in result.message


@pytest.mark.asyncio
async def test_effect_none_skips_the_check():
    tr = FakeTR([frame()])
    result = await _executor(tr, mode='strict').execute_keyboard(KeyboardAction(key='alt', effect='none'))
    assert result.success and result.data['effect'] == 'none' and tr.captures == 0


@pytest.mark.asyncio
async def test_keyboard_changed():
    tr = FakeTR([frame(), frame((300, 300, 300, 100))])
    result = await _executor(tr).execute_keyboard(KeyboardAction(text='hello'))
    assert result.success and result.data['effect'] == 'changed'
    assert result.data['text'] == 'hello'


@pytest.mark.asyncio
async def test_scroll_reports_effect():
    tr = FakeTR([frame(), frame((300, 300, 300, 100))])
    result = await _executor(tr).execute_scroll(ScrollAction(direction='down', amount=3))
    assert result.success and result.data['effect'] == 'changed'


@pytest.mark.asyncio
async def test_keyboard_verify_failure_fails_the_step():
    executor = _executor(FakeTR([frame()]))
    executor._verify_holds = AsyncMock(return_value=False)
    action = KeyboardAction(key='enter', verify=ClickVerify(exists=Target(text='Saved')), verify_timeout=0)
    result = await executor.execute_keyboard(action)
    assert not result.success and result.data['verified'] is False and 'Saved' in result.message


@pytest.mark.asyncio
async def test_keyboard_verify_success_is_verified_effect():
    executor = _executor(FakeTR([frame()]))
    executor._verify_holds = AsyncMock(return_value=True)
    action = KeyboardAction(key='enter', verify=ClickVerify(exists=Target(text='Saved')))
    result = await executor.execute_keyboard(action)
    assert result.success and result.data['effect'] == 'verified' and result.data['verified'] is True


@pytest.mark.parametrize(('written', 'mode'), [(None, 'warn'), ('prove', 'prove'), ('strict', 'strict')])
def test_action_executor_hands_the_mode_to_the_ledger(written, mode):
    from adare.backend.experiment.action_executor import ActionExecutor

    settings = Settings() if written is None else Settings(effect_check=written)
    executor = ActionExecutor(playbook=SimpleNamespace(settings=settings))
    assert executor.test_actions.effect_ledger.mode == mode
