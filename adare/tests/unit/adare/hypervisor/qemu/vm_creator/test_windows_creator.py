"""Unattended Windows installs: the Autounattend floppy and the Setup error watch."""

import io
import re
from pathlib import Path
from unittest.mock import patch

import pycdlib
import pytest
from PIL import Image

from adare.hypervisor.qemu.vm_creator.iso_utils import ISOExtractionError, extract_virtio_driver
from adare.hypervisor.qemu.vm_creator.os_catalog import SetupLevel, get_os_definition
from adare.hypervisor.qemu.vm_creator.windows_creator import (
    PlaybookVMCreator,
    WindowsVMCreationError,
    _create_autounattend_media,
    _render_autounattend,
    _SetupErrorWatch,
)

pytestmark = pytest.mark.unit

DRIVER = {'viostor.inf': b'[Version]', 'viostor.sys': b'MZ' * 100, 'viostor.cat': b'cat', 'viostor.pdb': b'p' * 500}


def _virtio_iso(path: Path, files: dict[str, bytes]) -> Path:
    """A Rock Ridge ISO laid out like virtio-win: viostor/w11/amd64/<files>."""
    iso = pycdlib.PyCdlib()
    iso.new(rock_ridge='1.09')
    parts = ''
    for part in ('viostor', 'w11', 'amd64'):
        parts += '/' + part.upper()
        iso.add_directory(parts, rr_name=part)
    for name, data in files.items():
        stem, ext = name.upper().split('.')
        iso.add_fp(io.BytesIO(data), len(data), f'{parts}/{stem}.{ext};1', rr_name=name)
    iso.write(str(path))
    iso.close()
    return path


class TestExtractVirtioDriver:
    def test_reads_the_driver_without_debug_symbols(self, tmp_path):
        iso = _virtio_iso(tmp_path / 'virtio-win.iso', DRIVER)

        files = extract_virtio_driver(iso, 'viostor/w11/amd64')

        assert files == {name: data for name, data in DRIVER.items() if not name.endswith('.pdb')}

    def test_a_missing_folder_names_it(self, tmp_path):
        iso = _virtio_iso(tmp_path / 'virtio-win.iso', DRIVER)

        with pytest.raises(ISOExtractionError, match='viostor/w10/amd64'):
            extract_virtio_driver(iso, 'viostor/w10/amd64')


class TestAutounattendFloppy:
    def test_carries_the_disk_driver_next_to_the_answer_file(self, tmp_path):
        iso = _virtio_iso(tmp_path / 'virtio-win.iso', DRIVER)

        with patch('adare.hypervisor.qemu.vm_creator.windows_creator._write_fat12_floppy') as write:
            _create_autounattend_media(get_os_definition('windows11'), tmp_path, virtio_iso_path=iso)

        files = write.call_args.args[1]
        assert sorted(files) == ['Autounattend.xml', 'viostor.cat', 'viostor.inf', 'viostor.sys']

    def test_win11_loads_drivers_from_the_floppy_only(self):
        # Current Setup aborts with 0x80070103 on listed paths that do not exist,
        # so the answer file must not guess drive letters.
        xml = _render_autounattend('autounattend_win11.xml', setup_level=SetupLevel.FULL)

        driver_paths = re.search(r'<DriverPaths>(.*?)</DriverPaths>', xml, re.S).group(1)
        assert re.findall(r'<Path>(.*?)</Path>', driver_paths) == ['A:\\']

    @pytest.mark.parametrize('template', ['autounattend_win10.xml', 'autounattend_win11.xml'])
    def test_installs_winfsp_for_the_virtio_fs_shares(self, template):
        bare = _render_autounattend(template, setup_level=SetupLevel.BARE)
        base = _render_autounattend(template, setup_level=SetupLevel.BASE)

        assert 'winfsp' not in bare.lower()
        assert re.search(r'msiexec /i \S*winfsp\S*\.msi /qn', base)

    @pytest.mark.parametrize('template', ['autounattend_win10.xml', 'autounattend_win11.xml'])
    def test_miniforge_is_pinned(self, template):
        # "latest" moved to a conda whose `create` fails on Windows (26.9.4-0).
        xml = _render_autounattend(template, setup_level=SetupLevel.FULL)

        assert '/releases/latest/' not in xml
        assert re.search(r'miniforge/releases/download/[\d.]+-\d+/Miniforge3-[\d.]+-\d+-Windows-x86_64\.exe', xml)

    @pytest.mark.parametrize('template', ['autounattend_win10.xml', 'autounattend_win11.xml'])
    @pytest.mark.parametrize('level', list(SetupLevel)[:3])
    def test_first_logon_steps_are_numbered_in_order(self, template, level):
        xml = _render_autounattend(template, setup_level=level)

        first_logon = re.search(r'<FirstLogonCommands>(.*)</FirstLogonCommands>', xml, re.S).group(1)
        orders = [int(order) for order in re.findall(r'<Order>(\d+)</Order>', first_logon)]
        assert orders == list(range(1, len(orders) + 1))

    def test_win11_selects_an_edition(self):
        # Multi-edition ISOs otherwise stop at the product key / edition screen.
        xml = _render_autounattend('autounattend_win11.xml', setup_level=SetupLevel.FULL)

        assert re.search(r'<UserData>.*<ProductKey>\s*<Key>[\w-]+</Key>', xml, re.S)


def _ppm() -> bytes:
    buffer = io.BytesIO()
    Image.new('RGB', (4, 4)).save(buffer, 'PPM')
    return buffer.getvalue()


class TestSetupErrorWatch:
    def _watch(self, tmp_path, lines):
        watch = _SetupErrorWatch(tmp_path / 'qmp.sock', tmp_path / 'win_setup-error.png')
        watch._last -= _SetupErrorWatch.INTERVAL_SECONDS
        screendump = patch.object(_SetupErrorWatch, '_screendump', return_value=_ppm())
        ocr = patch.object(PlaybookVMCreator, '_screen_lines', return_value=lines)
        return watch, screendump, ocr

    def test_an_error_dialog_stops_the_install_with_its_text_and_a_screenshot(self, tmp_path):
        error = 'Windows installation encountered an unexpected error. Error code: 0x80070103 - 0x40031'
        watch, screendump, ocr = self._watch(tmp_path, ['Windows 11 Setup', error, 'Close'])

        with screendump, ocr, pytest.raises(WindowsVMCreationError, match='0x80070103 - 0x40031'):
            watch()

        assert (tmp_path / 'win_setup-error.png').is_file()

    def test_a_working_setup_passes(self, tmp_path):
        watch, screendump, ocr = self._watch(tmp_path, ["We're getting a few things ready", 'Next'])

        with screendump, ocr:
            watch()

        assert not (tmp_path / 'win_setup-error.png').exists()

    def test_reads_the_screen_at_most_once_a_minute(self, tmp_path):
        watch, screendump, ocr = self._watch(tmp_path, [])

        with screendump as dump, ocr:
            watch()
            watch()

        assert dump.call_count == 1

    def test_an_unreadable_screen_does_not_fail_the_install(self, tmp_path):
        watch, _, ocr = self._watch(tmp_path, [])

        with patch.object(_SetupErrorWatch, '_screendump', side_effect=ConnectionRefusedError), ocr:
            watch()
