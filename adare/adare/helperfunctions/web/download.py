# external imports
# configure logging
import hashlib
import logging
import os
from pathlib import Path
from typing import TYPE_CHECKING

from tqdm import tqdm

# requests/aiohttp are imported inside the functions: this module is reached at
# import time by every DB-touching command (via backend.project.directory), and
# the two HTTP stacks alone cost ~60 ms there.
if TYPE_CHECKING:
    import aiohttp
    import requests

log = logging.getLogger(__name__)

# Disk images and ISOs are multi-GB; 1 KiB chunks meant millions of Python-level
# write/update calls per download.
CHUNK_SIZE = 1024 * 1024


class _PartialDownload:
    """Stream into ``<path>.part``, hashing as it goes; publish onto ``path`` only on success.

    A partially written file is never left at ``path``, where callers that cache
    by "file exists and is non-empty" would mistake it for a complete download.
    On any failure (including KeyboardInterrupt) the ``.part`` file is removed.
    """

    def __init__(self, path: Path):
        self.path = Path(path)
        self.part = self.path.with_name(self.path.name + '.part')
        self._digest = hashlib.sha256()

    def __enter__(self) -> '_PartialDownload':
        self._file = open(self.part, 'wb')
        return self

    def write(self, data: bytes) -> int:
        self._digest.update(data)
        return self._file.write(data)

    def __exit__(self, exc_type, exc, tb) -> None:
        self._file.close()
        if exc_type is None:
            os.replace(self.part, self.path)
        else:
            self.part.unlink(missing_ok=True)

    @property
    def sha256(self) -> str:
        return self._digest.hexdigest()


def _progress_bar(total: int) -> tqdm:
    return tqdm(
        desc='',
        total=total,
        unit='iB',
        unit_scale=True,
        unit_divisor=1024,
    )


def download(url: str, path: Path, headers: dict = None, quiet: bool = False) -> str:
    """
    download a file from an url

    The file is written to ``<path>.part`` and moved onto ``path`` only once the
    whole body arrived, so ``path`` never holds a truncated download.

    :param url: url
    :param path: place where the downloaded file will be saved to
    :param headers: headers for the request
    :param quiet: determines whether additional information about the download process should be printed
    :return: SHA256 hex digest of the downloaded bytes, computed while streaming
        (saves re-reading a multi-GB file just to verify it)
    """
    import requests

    if not headers:
        headers = dict()
    resp = requests.get(url, stream=True, headers=headers)
    resp.raise_for_status()
    total = int(resp.headers.get('content-length', 0))
    if quiet:
        log.debug(f'download of {path.as_posix()} in silent mode start')
        with _PartialDownload(path) as file:
            for data in resp.iter_content(chunk_size=CHUNK_SIZE):
                file.write(data)
        log.debug(f'download of {path.as_posix()} in silent mode done')
    else:
        log.debug(f'download of {path.as_posix()} start')
        print(f'\nDownload {url} -> {path.as_posix()}')
        with _PartialDownload(path) as file, _progress_bar(total) as bar:
            for data in resp.iter_content(chunk_size=CHUNK_SIZE):
                size = file.write(data)
                bar.update(size)
        log.debug(f'download of {path.as_posix()} done')
    return file.sha256


def download_from_session(url: str, path: Path, session: 'requests.Session') -> str:
    """
    download a file from an url (with requests) and progress bar with tqdm

    :param url: url
    :param path: place where the downloaded file will be saved to
    :param session: requests session
    :return: SHA256 hex digest of the downloaded bytes
    """
    total = int(session.head(url).headers.get('content-length', 0))
    log.debug(f'download of {path.as_posix()} start')
    print(f'\nDownload {url} -> {path.as_posix()}')
    response = session.get(url, stream=True)
    response.raise_for_status()
    with _PartialDownload(path) as file, _progress_bar(total) as bar:
        for data in response.iter_content(chunk_size=CHUNK_SIZE):
            size = file.write(data)
            bar.update(size)
    log.debug(f'download of {path.as_posix()} done')
    return file.sha256


async def download2(url: str, path: Path, session: 'aiohttp.ClientSession') -> str:
    """
    download a file from an url (with aiohttp) and progress bar with tqdm

    :param url: url
    :param path: place where the downloaded file will be saved to
    :param session: aiohttp session
    :return: SHA256 hex digest of the downloaded bytes
    """
    async with session.get(url) as response:
        total = int(response.headers.get('content-length', 0))
        log.debug(f'download of {path.as_posix()} start')
        print(f'\nDownload {url} -> {path.as_posix()}')
        with _PartialDownload(path) as file, _progress_bar(total) as bar:
            async for data in response.content.iter_any():
                size = file.write(data)
                bar.update(size)
        log.debug(f'download of {path.as_posix()} done')
    return file.sha256
