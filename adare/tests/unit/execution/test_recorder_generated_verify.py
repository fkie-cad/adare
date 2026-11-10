"""The recorder derives ``verify:`` / step-done gates from the screens before and after a step."""

import cv2
import numpy as np
import pytest
import yaml

from adare.backend.experiment.vlm.effect_verify import derive_effect_crop
from adare.backend.experiment.vlm.recorder import PlaybookRecorder
from adare.types.playbook import parse_playbook

pytestmark = pytest.mark.unit

W, H = 1280, 800


def png(*rects, noise=None) -> bytes:
    img = np.full((H, W, 3), 60, dtype=np.uint8)
    for x, y, w, h in rects:
        img[y : y + h, x : x + w] = 255
        img[y + 10 : y + 20, x + 10 : x + w - 10] = 0  # some structure inside
    if noise:
        x, y, w, h = noise
        img[y : y + h, x : x + w] = 128
    ok, buf = cv2.imencode('.png', img)
    assert ok
    return buf.tobytes()


DIALOG = (500, 300, 260, 140)
CLOCK = (W - 90, H - 30, 80, 24)


def test_crop_of_the_region_that_appeared():
    crop, reason = derive_effect_crop(png(), png(DIALOG), png(DIALOG))
    assert reason is None
    left, top, right, bottom = crop.box
    assert left <= 500 and top <= 300 and right >= 760 and bottom >= 440


def test_no_crop_when_only_the_clock_changed():
    crop, reason = derive_effect_crop(png(), png(CLOCK), png(CLOCK))
    assert crop is None and 'edges' in reason


def test_no_crop_when_region_is_still_changing():
    crop, reason = derive_effect_crop(png(), png(DIALOG), png(DIALOG, noise=(520, 340, 200, 60)))
    assert crop is None and 'still changing' in reason


def test_large_change_is_capped():
    crop, _ = derive_effect_crop(png(), png((100, 100, 1000, 600)), None)
    left, top, right, bottom = crop.box
    assert right - left <= 480 and bottom - top <= 320


def test_recorder_adds_verify_to_the_click(tmp_path):
    rec = PlaybookRecorder(tmp_path / 'p.yml')
    before = png()
    rec.record_click(before, 620, 360, 'open dialog')
    assert rec.attach_effect(before, png(DIALOG), png(DIALOG))
    rec.record_key('ctrl+s', 'save')
    assert not rec.attach_effect(png(DIALOG), png(DIALOG), png(DIALOG))  # nothing changed
    path = rec.finalize()

    doc = yaml.safe_load(path.read_text())
    click = doc['actions'][1]['click']
    assert click['verify']['exists']['image'].endswith('_effect.png')
    assert (tmp_path / 'img' / click['verify']['exists']['image']).is_file()
    assert 'verify' not in doc['actions'][2]['keyboard']
    assert parse_playbook(path).actions[1].verify.exists.image == click['verify']['exists']['image']


def test_recorder_step_done_gate(tmp_path):
    rec = PlaybookRecorder(tmp_path / 'p.yml')
    rec.record_key('super', 'menu')
    assert rec.record_step_done(png(), png(DIALOG), png(DIALOG), 'done when the dialog is open')
    gate = rec._actions[-1]['wait_until']
    assert gate['condition']['exists']['image'].endswith('_done.png')
    assert gate['description'] == 'step done: done when the dialog is open'


def test_rollback_drops_generated_checks(tmp_path):
    rec = PlaybookRecorder(tmp_path / 'p.yml')
    mark = rec.mark()
    rec.record_click(png(), 620, 360, 'x')
    rec.attach_effect(png(), png(DIALOG), png(DIALOG))
    rec.rollback(mark)
    assert rec.action_count == 0
