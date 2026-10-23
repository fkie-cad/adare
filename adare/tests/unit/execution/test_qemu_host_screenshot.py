"""QMP screenshot path: no settle sleep after screendump, lossless fast PNG encode."""

import base64
import io
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from PIL import Image

from adare.backend.experiment.execution import qemu_host_gui_executor
from adare.backend.experiment.execution.qemu_host_gui_executor import QEMUHostGUIExecutor

pytestmark = pytest.mark.unit


def _executor(tmp_path: Path) -> QEMUHostGUIExecutor:
    image = Image.new('RGB', (64, 48))
    image.putpixel((3, 4), (200, 10, 30))

    async def screendump(path):
        image.save(path, format='PPM')  # QEMU writes the file before replying
        return True, None

    vm = MagicMock(send_qmp_screenshot=AsyncMock(side_effect=screendump))
    return QEMUHostGUIExecutor(vm, target_resolution_executor=SimpleNamespace(screenshots_dir=tmp_path / 'shots'))


@pytest.mark.asyncio
async def test_screenshot_reads_the_screendump_without_sleeping(tmp_path):
    executor = _executor(tmp_path)
    with patch.object(qemu_host_gui_executor.asyncio, 'sleep', AsyncMock()) as sleep:
        result = await executor.screenshot()

    assert result['status'] == 'success'
    sleep.assert_not_awaited()
    png = Image.open(io.BytesIO(base64.b64decode(result['image']['data'])))
    assert png.format == 'PNG' and png.size == (64, 48)
    assert png.convert('RGB').getpixel((3, 4)) == (200, 10, 30)  # lossless at compress_level=1
    executor.vm.update_screen_resolution.assert_called_once_with(64, 48)
    assert not list((tmp_path / 'temp_qmp').iterdir())  # temp PPM cleaned up
