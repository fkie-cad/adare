"""Tests for the streaming downloader: .part publishing and the streamed digest."""

import hashlib
from unittest.mock import MagicMock, patch

import pytest
import requests

from adare.helperfunctions.web import download as download_module
from adare.helperfunctions.web.download import CHUNK_SIZE, download, download_from_session

pytestmark = pytest.mark.unit


def _response(chunks, fail_after=None):
    """A fake streaming response yielding ``chunks`` (raising after ``fail_after`` of them)."""
    resp = MagicMock()
    resp.headers = {'content-length': str(sum(len(c) for c in chunks))}

    def iter_content(chunk_size):
        assert chunk_size == CHUNK_SIZE
        for i, chunk in enumerate(chunks):
            if fail_after is not None and i == fail_after:
                raise requests.ConnectionError('connection reset')
            yield chunk

    resp.iter_content.side_effect = iter_content
    return resp


@pytest.mark.parametrize('quiet', [True, False])
def test_download_publishes_file_and_returns_streamed_digest(tmp_path, quiet):
    chunks = [b'a' * 10, b'b' * 20, b'c']
    dest = tmp_path / 'disk.iso'
    with patch.object(requests, 'get', return_value=_response(chunks)) as get:
        digest = download('https://example.invalid/disk.iso', dest, quiet=quiet)

    get.assert_called_once()
    assert dest.read_bytes() == b''.join(chunks)
    assert digest == hashlib.sha256(b''.join(chunks)).hexdigest()
    assert not (tmp_path / 'disk.iso.part').exists()


def test_download_failure_leaves_no_partial_file(tmp_path):
    dest = tmp_path / 'disk.iso'
    with (
        patch.object(requests, 'get', return_value=_response([b'x' * 5, b'y' * 5], fail_after=1)),
        pytest.raises(requests.ConnectionError),
    ):
        download('https://example.invalid/disk.iso', dest, quiet=True)

    # Neither the final path (which callers treat as a cache hit) nor the .part survives.
    assert not dest.exists()
    assert not (tmp_path / 'disk.iso.part').exists()


def test_download_failure_keeps_previous_file_intact(tmp_path):
    dest = tmp_path / 'disk.iso'
    dest.write_bytes(b'previous complete file')
    with (
        patch.object(requests, 'get', return_value=_response([b'new', b'data'], fail_after=1)),
        pytest.raises(requests.ConnectionError),
    ):
        download('https://example.invalid/disk.iso', dest, quiet=True)

    assert dest.read_bytes() == b'previous complete file'


def test_download_from_session_returns_digest(tmp_path):
    chunks = [b'1234', b'5678']
    session = MagicMock()
    session.head.return_value.headers = {'content-length': '8'}
    session.get.return_value = _response(chunks)
    dest = tmp_path / 'bundle.zip'

    digest = download_from_session('https://example.invalid/bundle.zip', dest, session)

    assert dest.read_bytes() == b'12345678'
    assert digest == hashlib.sha256(b'12345678').hexdigest()
    assert not (tmp_path / 'bundle.zip.part').exists()


def test_http_stacks_are_not_imported_at_module_level():
    # Importing the module must not pull requests/aiohttp in (import-time cost
    # paid by every DB-touching command); they are imported where used.
    assert not hasattr(download_module, 'requests')
    assert not hasattr(download_module, 'aiohttp')
