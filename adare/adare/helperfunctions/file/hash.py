import hashlib
from pathlib import Path
from typing import Optional
import threading
import asyncio
from tqdm import tqdm

# configure logging
import logging
log = logging.getLogger(__name__)



def file_sha256_with_progress(
    file_path: Path,
    description: Optional[str] = None,
    silent: bool = False,
    interrupt_event: Optional[threading.Event] = None
) -> str:
    """
    Calculate SHA256 hash of file with progress bar.

    Args:
        file_path: Path to file
        description: Optional description for progress bar
        silent: If True, suppress progress bar
        interrupt_event: Optional event to check for user interruption

    Returns:
        SHA256 hash string

    Raises:
        InterruptedError: If interrupt_event is set during calculation
    """
    if silent:
        log.debug(f'Calculating hash for {file_path} in silent mode')
        hash_sha256 = hashlib.sha256()
        with open(file_path, "rb") as f:
            for chunk in iter(lambda: f.read(4096), b""):
                if interrupt_event and interrupt_event.is_set():
                    raise InterruptedError(f"Hash calculation interrupted by user for {file_path}")
                hash_sha256.update(chunk)
        result = hash_sha256.hexdigest()
        log.debug(f'Hash calculation completed for {file_path}')
        return result
    
    # Get file size for progress bar
    file_size = file_path.stat().st_size
    
    desc = description or f"Calculating hash for {file_path.name}"
    log.debug(f'Calculating hash for {file_path} with progress bar')
    
    hash_sha256 = hashlib.sha256()
    with open(file_path, "rb") as f, tqdm(
        desc=desc,
        total=file_size,
        unit='iB',
        unit_scale=True,
        unit_divisor=1024,
    ) as bar:
        chunk_size = 64 * 1024  # 64KB chunks
        while True:
            if interrupt_event and interrupt_event.is_set():
                raise InterruptedError(f"Hash calculation interrupted by user for {file_path}")
            chunk = f.read(chunk_size)
            if not chunk:
                break
            hash_sha256.update(chunk)
            bar.update(len(chunk))
    
    result = hash_sha256.hexdigest()
    log.debug(f'Hash calculation completed for {file_path}')
    return result


async def file_sha256_with_progress_async(
    file_path: Path,
    description: Optional[str] = None,
    silent: bool = False,
    interrupt_event: Optional[threading.Event] = None
) -> str:
    """
    Calculate SHA256 hash of file with progress bar (async version).

    Args:
        file_path: Path to file
        description: Optional description for progress bar
        silent: If True, suppress progress bar
        interrupt_event: Optional event to check for user interruption

    Returns:
        SHA256 hash string

    Raises:
        InterruptedError: If interrupt_event is set during calculation
    """
    def _calculate_hash():
        return file_sha256_with_progress(
            file_path=file_path,
            description=description,
            silent=silent,
            interrupt_event=interrupt_event
        )

    # Run the hash calculation in a thread pool to avoid blocking the event loop
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, _calculate_hash)


