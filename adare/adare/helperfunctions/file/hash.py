import hashlib
from pathlib import Path
from typing import Optional
from tqdm import tqdm

# configure logging
import logging
log = logging.getLogger(__name__)



def file_sha256_with_progress(
    file_path: Path,
    description: Optional[str] = None,
    silent: bool = False
) -> str:
    """
    Calculate SHA256 hash of file with progress bar.
    
    Args:
        file_path: Path to file
        description: Optional description for progress bar
        quiet: If True, suppress progress bar
        
    Returns:
        SHA256 hash string
    """
    if silent:
        log.debug(f'Calculating hash for {file_path} in silent mode')
        hash_sha256 = hashlib.sha256()
        with open(file_path, "rb") as f:
            for chunk in iter(lambda: f.read(4096), b""):
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
            chunk = f.read(chunk_size)
            if not chunk:
                break
            hash_sha256.update(chunk)
            bar.update(len(chunk))
    
    result = hash_sha256.hexdigest()
    log.debug(f'Hash calculation completed for {file_path}')
    return result


