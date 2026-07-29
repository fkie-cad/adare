"""Tests for the vision-LLM GUI agent, action parser, and playbook recorder.

These run with no live vLLM: the model is stubbed and the GUI executor is a
fake. They assert (a) the action parser handles real model reply shapes and
coordinate conventions, (b) the recorder emits parse_playbook-valid YAML with
an image crop + description, and (c) the agent's step / stall budgets trip.
"""

from __future__ import annotations

import base64
import io

import pytest
from PIL import Image

from adare.backend.experiment.vlm.actions import parse_action
from adare.backend.experiment.vlm.agent import GuiAgent
from adare.backend.experiment.vlm.exceptions import VLMError
from adare.backend.experiment.vlm.recorder import PlaybookRecorder
from adare.types.playbook import (
    ClickAction,
    IdleAction,
    KeyboardAction,
    WaitUntilAction,
    parse_playbook,
)

pytestmark = pytest.mark.unit


def _png_bytes(color=(30, 30, 40), w=1280, h=800) -> bytes:
    buf = io.BytesIO()
    Image.new('RGB', (w, h), color).save(buf, format='PNG')
    return buf.getvalue()


def _png_b64(**kw) -> str:
    return base64.b64encode(_png_bytes(**kw)).decode()


# ---------------------------------------------------------------------------
# Action parser
# ---------------------------------------------------------------------------

def test_parse_click_absolute():
    a = parse_action(
        '{"reasoning":"r","action":"click","x":100,"y":200,"button":"left",'
        '"describe":"Next button"}',
        coord_space='absolute', screen_width=1280, screen_height=800,
    )
    assert a.kind == 'click'
    assert (a.x, a.y) == (100, 200)
    assert a.describe == 'Next button'


def test_parse_click_normalized_1000_scales_to_pixels():
    a = parse_action(
        '{"action":"click","x":500,"y":500,"describe":"centre"}',
        coord_space='normalized_1000', screen_width=1000, screen_height=800,
    )
    assert a.x == 500  # 500/1000 * 1000
    assert a.y == 400  # 500/1000 * 800


def test_parse_handles_code_fence_and_prose():
    reply = 'Sure, here is the action:\n```json\n{"action":"type","text":"adare"}\n```'
    a = parse_action(reply)
    assert a.kind == 'type'
    assert a.text == 'adare'


def test_parse_done_and_key():
    assert parse_action('{"action":"done","summary":"installed"}').summary == 'installed'
    assert parse_action('{"action":"key","combo":"ctrl+a"}').combo == 'ctrl+a'


def test_parse_rejects_unknown_and_malformed():
    with pytest.raises(VLMError):
        parse_action('{"action":"teleport"}')
    with pytest.raises(VLMError):
        parse_action('not json at all')
    with pytest.raises(VLMError):
        parse_action('{"action":"click","describe":"missing coords"}',
                     screen_width=100, screen_height=100)


# ---------------------------------------------------------------------------
# Recorder -> parse_playbook round-trip
# ---------------------------------------------------------------------------

def test_recorder_emits_valid_playbook(tmp_path):
    rec = PlaybookRecorder(tmp_path / 'gui_kubuntu.play.yaml', goal='install kubuntu')
    png = _png_bytes()
    rec.record_click(png, 640, 400, 'the Install button')
    rec.record_type('adare', 'username field')
    rec.record_key('enter', 'confirm')
    rec.record_wait('the partitioning screen')
    rec.record_idle(2.0)
    path = rec.finalize()

    # Sidecar + image crop exist.
    assert rec.meta_path.exists()
    imgs = list((tmp_path / 'img').glob('*.png'))
    assert len(imgs) == 1

    # Re-parses through ADARE's own loader.
    pb = parse_playbook(path)
    kinds = [type(a).__name__ for a in pb.actions]
    assert kinds == ['ClickAction', 'KeyboardAction', 'KeyboardAction',
                     'WaitUntilAction', 'IdleAction']

    click = pb.actions[0]
    assert isinstance(click, ClickAction)
    assert click.target.image == imgs[0].name
    assert click.description == 'the Install button'

    typed = pb.actions[1]
    assert isinstance(typed, KeyboardAction) and typed.text == 'adare'
    pressed = pb.actions[2]
    assert isinstance(pressed, KeyboardAction) and pressed.key == 'enter'

    wait = pb.actions[3]
    assert isinstance(wait, WaitUntilAction)
    assert wait.condition.exists.text == 'the partitioning screen'

    assert isinstance(pb.actions[4], IdleAction)


def test_recorder_key_combination(tmp_path):
    rec = PlaybookRecorder(tmp_path / 'p.play.yaml')
    rec.record_key('ctrl+alt+t', 'open terminal')
    pb = parse_playbook(rec.finalize())
    assert pb.actions[0].combination == ['ctrl', 'alt', 't']


def test_recorder_refuses_empty(tmp_path):
    from adare.backend.experiment.vlm.exceptions import PlaybookRecordingError
    rec = PlaybookRecorder(tmp_path / 'empty.play.yaml')
    with pytest.raises(PlaybookRecordingError):
        rec.finalize()


# ---------------------------------------------------------------------------
# Agent loop (stubbed model + executor)
# ---------------------------------------------------------------------------

class _FakeClient:
    """Scripted stand-in for VLMClient."""

    def __init__(self, replies):
        self._replies = list(replies)
        self.calls = 0

    @staticmethod
    def image_content(b64):
        return {'type': 'image_url', 'image_url': {'url': f'data:image/png;base64,{b64}'}}

    @staticmethod
    def text_content(text):
        return {'type': 'text', 'text': text}

    async def chat(self, messages, *, temperature=0.0, max_tokens=1024):
        self.calls += 1
        if self._replies:
            return self._replies.pop(0)
        return '{"action":"note"}'


class _FakeExecutor:
    """Fake AbstractGUIExecutor; screenshots vary per call unless frozen."""

    def __init__(self, frozen=False):
        self.frozen = frozen
        self.n = 0
        self.clicks = []
        self.keys = []

    async def screenshot(self, region=None):
        self.n += 1
        shade = 30 if self.frozen else min(255, 30 + self.n * 5)
        return {'status': 'success',
                'image': {'data': _png_b64(color=(shade, shade, shade)), 'format': 'png'}}

    async def click(self, x, y, button_type='left'):
        self.clicks.append((x, y, button_type))
        return {'status': 'success'}

    async def keyboard(self, action_type, value):
        self.keys.append((action_type, value))
        return {'status': 'success'}

    async def scroll(self, direction, amount):
        return {'status': 'success'}

    async def drag(self, x1, y1, x2, y2):
        return {'status': 'success'}


@pytest.mark.asyncio
async def test_agent_happy_path_records_playbook(tmp_path):
    replies = [
        '{"action":"click","x":640,"y":400,"describe":"Install button"}',
        '{"action":"type","text":"adare","describe":"username"}',
        '{"action":"key","combo":"enter","describe":"confirm"}',
        '{"action":"wait","until_describe":"the next screen"}',
        '{"action":"done","summary":"installation complete"}',
    ]
    executor = _FakeExecutor()
    recorder = PlaybookRecorder(tmp_path / 'gui.play.yaml', goal='install')
    agent = GuiAgent(
        executor, _FakeClient(replies), 'install kubuntu',
        recorder=recorder, run_dir=tmp_path / 'run',
        max_steps=20, step_settle_seconds=0,
    )
    result = await agent.run()

    assert result.success is True
    assert result.summary == 'installation complete'
    assert executor.clicks == [(640, 400, 'left')]
    assert ('type', 'adare') in executor.keys

    # A valid playbook was produced.
    assert result.playbook_path is not None
    pb = parse_playbook(result.playbook_path)
    assert [type(a).__name__ for a in pb.actions] == [
        'ClickAction', 'KeyboardAction', 'KeyboardAction', 'WaitUntilAction']
    # The illustrated report exists.
    assert (tmp_path / 'run' / 'install_report.md').exists()


@pytest.mark.asyncio
async def test_agent_trips_max_steps(tmp_path):
    executor = _FakeExecutor(frozen=False)  # varies → not a stall
    agent = GuiAgent(
        executor, _FakeClient(['{"action":"note"}'] * 10), 'goal',
        max_steps=3, stall_limit=99, step_settle_seconds=0,
    )
    result = await agent.run()
    assert result.success is False
    assert 'max steps' in result.reason


@pytest.mark.asyncio
async def test_agent_trips_stall(tmp_path):
    executor = _FakeExecutor(frozen=True)  # identical screen every step
    agent = GuiAgent(
        executor, _FakeClient(['{"action":"note"}'] * 10), 'goal',
        max_steps=50, stall_limit=3, step_settle_seconds=0,
    )
    result = await agent.run()
    assert result.success is False
    assert 'stall' in result.reason
