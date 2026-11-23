"""Testfunction upload: symlinked/differently spelled state dirs, and no silent empty upload."""

import base64
import io
import os
import zipfile
from unittest.mock import AsyncMock, MagicMock

import pytest

from adare.backend.experiment.test_loader import TestLoader
from adare.backend.experiment.testfunction_archive import build_testfunctions_zip
from adare.backend.experiment.websocket_client import AdareVMClient
from adare.exceptions import TestfunctionUploadError


def _names(zip_bytes: bytes) -> list[str]:
    with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
        return sorted(zf.namelist())


@pytest.fixture
def real_and_link(tmp_path):
    """A testfunctions dir under a 'real' ADARE_HOME and the same dir reached through a symlink."""
    real_home = tmp_path / 'real_home'
    (real_home / 'testfunctions' / 'sqlite').mkdir(parents=True)
    (real_home / 'testfunctions' / 'sqlite' / 'row_count.py').write_text('x = 1\n')
    (real_home / 'testfunctions' / 'standard.py').write_text('y = 2\n')
    link_home = tmp_path / 'link_home'
    os.symlink(real_home, link_home)
    return real_home / 'testfunctions', link_home / 'testfunctions'


def test_symlinked_state_dir_with_real_db_paths(real_and_link):
    real, link = real_and_link
    # STATE_DIR is the symlinked spelling, the database holds the real paths
    data = build_testfunctions_zip(link, {real / 'sqlite' / 'row_count.py'})
    assert _names(data) == ['sqlite/row_count.py']


def test_real_state_dir_with_symlinked_db_paths(real_and_link):
    real, link = real_and_link
    data = build_testfunctions_zip(real, {link / 'standard.py', link / 'sqlite' / 'row_count.py'})
    assert _names(data) == ['sqlite/row_count.py', 'standard.py']


def test_file_outside_testfunctions_dir_is_an_error(real_and_link, tmp_path):
    real, _ = real_and_link
    outside = tmp_path / 'elsewhere' / 'other.py'
    outside.parent.mkdir()
    outside.write_text('z = 3\n')
    with pytest.raises(TestfunctionUploadError) as exc:
        build_testfunctions_zip(real, {real / 'standard.py', outside})
    assert str(outside) in exc.value.message
    assert 'outside the testfunctions directory' in exc.value.message


def test_missing_file_is_an_error(real_and_link):
    real, _ = real_and_link
    missing = real / 'gone.py'
    with pytest.raises(TestfunctionUploadError) as exc:
        build_testfunctions_zip(real, {real / 'standard.py', missing})
    assert str(missing) in exc.value.message
    assert 'does not exist' in exc.value.message


def test_upload_everything_when_no_specific_files(real_and_link):
    real, link = real_and_link
    assert _names(build_testfunctions_zip(link)) == ['sqlite/row_count.py', 'standard.py']


@pytest.mark.asyncio
async def test_client_upload_sends_zip_through_symlink(real_and_link):
    real, link = real_and_link
    client = AdareVMClient.__new__(AdareVMClient)
    client.call_tool = AsyncMock(return_value={'status': 'success'})
    await client.upload_testfunctions(link, {real / 'sqlite' / 'row_count.py'})
    params = client.call_tool.call_args.args[1]
    assert _names(base64.b64decode(params['testfunctions_data'])) == ['sqlite/row_count.py']


@pytest.mark.asyncio
async def test_client_upload_never_sends_an_empty_zip(real_and_link, tmp_path):
    real, _ = real_and_link
    client = AdareVMClient.__new__(AdareVMClient)
    client.call_tool = AsyncMock()
    with pytest.raises(TestfunctionUploadError):
        await client.upload_testfunctions(real, {tmp_path / 'not' / 'there.py'})
    client.call_tool.assert_not_called()


def _loader(tmp_path, monkeypatch, state_dir, required):
    monkeypatch.setattr('adare.config.configdirectory.STATE_DIR', state_dir)
    loader = TestLoader(tmp_path, tmp_path)
    monkeypatch.setattr(loader, '_extract_used_testfunction_names', lambda: {'sqlite.row_count'})
    monkeypatch.setattr(loader, '_get_testfunction_files_for_functions', lambda names: required)
    return loader


@pytest.mark.asyncio
async def test_load_tests_aborts_when_a_required_file_is_unusable(real_and_link, tmp_path, monkeypatch):
    real, link = real_and_link
    state_dir = link.parent
    loader = _loader(tmp_path, monkeypatch, state_dir, {tmp_path / 'nowhere' / 'row_count.py'})
    client = AdareVMClient.__new__(AdareVMClient)
    client.call_tool = AsyncMock()
    with pytest.raises(TestfunctionUploadError, match='row_count.py'):
        await loader.load_tests(client)
    client.call_tool.assert_not_called()


@pytest.mark.asyncio
async def test_load_tests_uploads_through_symlinked_state_dir(real_and_link, tmp_path, monkeypatch):
    real, link = real_and_link
    loader = _loader(tmp_path, monkeypatch, link.parent, {real / 'sqlite' / 'row_count.py'})
    client = AdareVMClient.__new__(AdareVMClient)
    client.call_tool = AsyncMock(return_value={'status': 'success'})
    await loader.load_tests(client)
    params = client.call_tool.call_args.args[1]
    assert _names(base64.b64decode(params['testfunctions_data'])) == ['sqlite/row_count.py']


@pytest.mark.asyncio
async def test_load_tests_turns_os_error_and_guest_rejection_into_upload_error(real_and_link, tmp_path, monkeypatch):
    real, link = real_and_link
    loader = _loader(tmp_path, monkeypatch, link.parent, {real / 'standard.py'})
    client = MagicMock()
    client.upload_testfunctions = AsyncMock(side_effect=OSError('disk full'))
    with pytest.raises(TestfunctionUploadError, match='disk full'):
        await loader.load_tests(client)
    client.upload_testfunctions = AsyncMock(return_value={'status': 'error', 'message': 'bad zip'})
    with pytest.raises(TestfunctionUploadError, match='bad zip'):
        await loader.load_tests(client)
