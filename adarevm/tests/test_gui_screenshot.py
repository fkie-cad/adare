"""Agent screenshots: maim's PNG passes through untouched, capture runs off the event loop."""

import asyncio
import base64
import threading

import pytest

from adarevm.automation import gui
from adarevm.core.tools.gui_tools import GUIToolsMixin

PNG = b'\x89PNG\r\n\x1a\n-not-really-decoded-'


@pytest.fixture
def maim(monkeypatch):
    calls = []

    def check_output(cmd, stderr=None):
        calls.append(cmd)
        return PNG

    monkeypatch.setattr(gui, '_use_maim_screenshot', True)
    monkeypatch.setattr(gui.subprocess, 'check_output', check_output)
    return calls


def test_maim_png_is_returned_without_re_encoding(maim):
    result = gui.take_screenshot()
    assert result['status'] == 'success'
    assert base64.b64decode(result['image']['data']) == PNG
    assert maim == [['maim', '-f', 'png']]


def test_maim_region_screenshot_keeps_its_geometry_and_offset(maim):
    result = gui.take_screenshot(5, 6, 70, 80)
    assert maim == [['maim', '-f', 'png', '-g', '70x80+5+6']]
    assert result['offset'] == {'x': 5, 'y': 6}


class _Tools(GUIToolsMixin):
    async def send_event(self, websocket, event_type, data):
        pass


@pytest.mark.asyncio
async def test_screenshot_tool_captures_in_a_worker_thread(monkeypatch):
    threads = []

    def fake_take_screenshot(x, y, width, height):
        threads.append(threading.current_thread())
        return {'status': 'success', 'args': (x, y, width, height)}

    monkeypatch.setattr(gui, 'take_screenshot', fake_take_screenshot)
    result = await _Tools()._screenshot(None, 1, 2, 3, 4)

    assert result == {'status': 'success', 'args': (1, 2, 3, 4)}
    assert threads and threads[0] is not threading.main_thread()
    assert asyncio.get_running_loop()  # still on the loop afterwards
