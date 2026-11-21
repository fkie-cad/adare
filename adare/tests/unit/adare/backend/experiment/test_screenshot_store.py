"""Run screenshots are written at once and recompressed losslessly in the background."""

import io
import random

import pytest
from PIL import Image

from adare.backend.experiment import screenshot_store
from adare.backend.experiment.screenshot_store import (
    ENV_VAR,
    png_level,
    recompress_png,
    store_screenshot,
    wait_for_pending,
)


def _screenshot_png(level: int = 1) -> tuple[bytes, Image.Image]:
    """A desktop-like frame (flat areas + some noise) encoded the fast way."""
    rng = random.Random(7)
    img = Image.new('RGB', (320, 200), (40, 90, 160))
    px = img.load()
    for y in range(60, 140):
        for x in range(20, 300):
            px[x, y] = (rng.randrange(256), 200, 200) if x % 7 else (255, 255, 255)
    buf = io.BytesIO()
    img.save(buf, format='PNG', compress_level=level)
    return buf.getvalue(), img


def _pixels(path) -> bytes:
    with Image.open(path) as img:
        return img.convert('RGB').tobytes()


def test_store_writes_then_recompresses_pixel_identical(tmp_path, monkeypatch):
    monkeypatch.delenv(ENV_VAR, raising=False)
    raw, img = _screenshot_png(level=1)
    path = tmp_path / '001_click.png'

    store_screenshot(path, raw)
    assert wait_for_pending(timeout=30) == 0

    assert path.stat().st_size < len(raw)
    assert _pixels(path) == img.tobytes()
    assert not list(tmp_path.glob('.*.tmp'))


def test_off_keeps_captured_bytes(tmp_path, monkeypatch):
    monkeypatch.setenv(ENV_VAR, 'off')
    raw, _ = _screenshot_png(level=1)
    path = tmp_path / 'shot.png'

    store_screenshot(path, raw)
    wait_for_pending(timeout=30)

    assert path.read_bytes() == raw


def test_not_replaced_when_not_smaller(tmp_path):
    raw, _ = _screenshot_png(level=9)
    path = tmp_path / 'shot.png'
    path.write_bytes(raw)

    assert recompress_png(path, level=0) is False
    assert path.read_bytes() == raw


def test_corrupt_png_is_left_alone(tmp_path):
    path = tmp_path / 'broken.png'
    path.write_bytes(b'\x89PNG\r\n\x1a\nnot really')

    assert recompress_png(path, level=9) is False
    assert path.read_bytes() == b'\x89PNG\r\n\x1a\nnot really'
    assert not list(tmp_path.glob('.*.tmp'))


def test_rgba_mode_is_kept(tmp_path):
    img = Image.new('RGBA', (64, 64), (10, 20, 30, 128))
    buf = io.BytesIO()
    img.save(buf, format='PNG', compress_level=0)
    path = tmp_path / 'alpha.png'
    path.write_bytes(buf.getvalue())

    assert recompress_png(path, level=9) is True
    with Image.open(path) as out:
        assert out.mode == 'RGBA'
        assert out.tobytes() == img.tobytes()


@pytest.mark.parametrize(
    ('value', 'expected'),
    [('', 9), ('6', 6), ('0', 0), ('off', None), ('NONE', None), ('12', 9), ('fast', 9)],
)
def test_png_level_from_env(monkeypatch, value, expected):
    monkeypatch.setenv(ENV_VAR, value)
    assert png_level() == expected


def test_wait_for_pending_without_work():
    assert screenshot_store.wait_for_pending(timeout=0) == 0
