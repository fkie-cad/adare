import logging
import shutil
from collections.abc import Callable, Iterable
from pathlib import Path

from tqdm import tqdm

log = logging.getLogger(__name__)

BUFFER_SIZE = 1024 * 1024 # 1MB

def __copy(src: str | Path, dst: str | Path, buffer_size: int = BUFFER_SIZE) -> None:
    """Copy a file from src to dst without a progress bar."""
    src_path = Path(src)
    dst_path = Path(dst)
    with src_path.open('rb') as fsrc, dst_path.open('wb') as fdst:
        while True:
            buf = fsrc.read(buffer_size)
            if not buf:
                break
            fdst.write(buf)


def copy_with_progress(src: str | Path, dst: str | Path, buffer_size: int = BUFFER_SIZE) -> None:
    """Copy a file from src to dst with a progress bar."""
    src_path = Path(src)
    dst_path = Path(dst)
    total_size = src_path.stat().st_size
    with src_path.open('rb') as fsrc, dst_path.open('wb') as fdst, tqdm(
        total=total_size, unit='B', unit_scale=True, desc=f"Copying {src_path.name}"
    ) as pbar:
        while True:
            buf = fsrc.read(buffer_size)
            if not buf:
                break
            fdst.write(buf)
            pbar.update(len(buf))


def copy(src: str | Path, dst: str | Path, buffer_size: int = BUFFER_SIZE, silent: bool = False) -> None:
    """
    Copy a file from src to dst, with optional progress bar.

    Args:
        src (Union[str, Path]): Source file path.
        dst (Union[str, Path]): Destination file path.
        buffer_size (int): Size of read/write buffer (default: 1MB).
        silent (bool): If True, no progress bar is shown.
    """
    src_path = Path(src)
    dst_path = Path(dst)

    dst_path.parent.mkdir(parents=True, exist_ok=True)

    if silent:
        __copy(src_path, dst_path, buffer_size)
    else:
        copy_with_progress(src_path, dst_path, buffer_size)

    log.info(f"Copied file {src_path} to {dst_path}.")


def copytree_with_progress(
    src: str | Path,
    dst: str | Path,
    preserve_metadata: bool = False,
    buffer_size: int = 1024 * 1024,
    dirs_exist_ok: bool = False,
    ignore: Callable[[str, Iterable[str]], Iterable[str]] | None = None
) -> None:
    """
    Recursively copy a directory from src to dst with a progress bar.

    Args:
        src (Union[str, Path]): Source directory path.
        dst (Union[str, Path]): Destination directory path.
        preserve_metadata (bool): Preserve file metadata (e.g. timestamps).
        buffer_size (int): Read/write chunk size in bytes.
        dirs_exist_ok (bool): Allow destination to already exist.
        ignore (Callable): A function like shutil.ignore_patterns().
    """
    import os
    src_path = Path(src)
    dst_path = Path(dst)

    if not src_path.is_dir():
        raise ValueError(f"Source path '{src}' is not a directory.")

    if dst_path.exists() and not dirs_exist_ok:
        raise FileExistsError(f"Destination '{dst}' already exists.")

    # Collect files to copy and apply ignore patterns
    all_files = []
    for dirpath, dirnames, filenames in os.walk(src_path):
        rel_dir = Path(dirpath).relative_to(src_path)
        ignore_set = set()
        if ignore:
            ignored = ignore(str(rel_dir), dirnames + filenames)
            ignore_set = set(ignored)

        for filename in filenames:
            if filename in ignore_set:
                continue
            src_file = Path(dirpath) / filename
            all_files.append(src_file)

    total_size = sum(f.stat().st_size for f in all_files)

    with tqdm(total=total_size, unit='B', unit_scale=True, desc=f"Copying {src_path.name}") as pbar:
        for file in all_files:
            rel_path = file.relative_to(src_path)
            target_file = dst_path / rel_path
            target_file.parent.mkdir(parents=True, exist_ok=True)

            with file.open('rb') as fsrc, target_file.open('wb') as fdst:
                while True:
                    buf = fsrc.read(buffer_size)
                    if not buf:
                        break
                    fdst.write(buf)
                    pbar.update(len(buf))

            if preserve_metadata:
                shutil.copystat(file, target_file)

    log.info(f"Copied directory {src_path} to {dst_path}.")
