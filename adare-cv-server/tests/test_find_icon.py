"""find_icon runs off the event loop and decodes its inputs once per request."""

import asyncio
import base64
import threading

import cv2
import numpy as np
from adare_cv_server import image_processing, server
from adare_cv_server.image_processing import ImageDecoder, shared_decodes


def _png(img: np.ndarray) -> bytes:
    ok, buf = cv2.imencode('.png', img)
    assert ok
    return buf.tobytes()


def _icon_and_screenshot() -> tuple[bytes, bytes]:
    rng = np.random.default_rng(0)
    icon = rng.integers(0, 255, size=(32, 32, 3), dtype=np.uint8)
    cv2.circle(icon, (16, 16), 10, (0, 0, 255), -1)
    screenshot = np.full((300, 400, 3), 240, dtype=np.uint8)
    screenshot[120:152, 200:232] = icon
    return _png(icon), _png(screenshot)


def test_find_icon_locates_the_icon_off_the_event_loop(monkeypatch):
    icon, screenshot = _icon_and_screenshot()
    threads = []
    real = server._find_icon_sync

    def spy(*args, **kwargs):
        threads.append(threading.current_thread())
        return real(*args, **kwargs)

    monkeypatch.setattr(server, '_find_icon_sync', spy)
    find_icon = getattr(server.find_icon, 'fn', server.find_icon)  # FastMCP tool wraps the function

    result = asyncio.run(
        find_icon(base64.b64encode(icon).decode(), base64.b64encode(screenshot).decode(), max_results=1)
    )

    assert threads and threads[0] is not threading.main_thread()
    assert result['locations'], result
    x, y = result['locations'][0]
    assert abs(x - 216) <= 3 and abs(y - 136) <= 3


def test_shared_decodes_reuses_one_decode_and_hands_out_copies(monkeypatch):
    icon, screenshot = _icon_and_screenshot()
    calls = []
    real_imdecode = cv2.imdecode

    def counting_imdecode(buf, flags):
        calls.append(flags)
        return real_imdecode(buf, flags)

    monkeypatch.setattr(image_processing.cv2, 'imdecode', counting_imdecode)

    with shared_decodes():
        first, _ = ImageDecoder.decode_images(screenshot, icon)
        first[:] = 0  # a stage scribbling on its copy must not leak into the next
        second, _ = ImageDecoder.decode_images(screenshot, icon)
        ImageDecoder.decode_images_with_alpha(screenshot, icon)

    # screenshot (color) + icon (color) once each, plus the icon's alpha-preserving decode
    assert len(calls) == 3
    assert second.any()

    calls.clear()
    ImageDecoder.decode_images(screenshot, icon)
    ImageDecoder.decode_images(screenshot, icon)
    assert len(calls) == 4  # outside the block every call decodes
