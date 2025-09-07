"""
VirtualBox API utility functions.
"""
import hashlib
import logging
import subprocess
from pathlib import Path
from typing import Optional

log = logging.getLogger(__name__)


def run_subprocess(cmd, *, check=True, capture_output=True, text=True, log_prefix=""):
    try:
        result = subprocess.run(
            cmd,
            check=check,
            stdout=subprocess.PIPE if capture_output else None,
            stderr=subprocess.PIPE if capture_output else None,
            text=text
        )
        return result
    except subprocess.CalledProcessError as e:
        log.error(f"{log_prefix}Subprocess failed: {e}")
        if capture_output:
            log.error(f"{log_prefix}stdout: {e.stdout}")
            log.error(f"{log_prefix}stderr: {e.stderr}")
        raise


def read_file_hash(path, hash_algo="sha256"):
    """Read a file and return its hash."""
    try:
        with open(path, 'rb') as f:
            file_hash = hashlib.new(hash_algo)
            for chunk in iter(lambda: f.read(4096), b""):
                file_hash.update(chunk)
            return file_hash.hexdigest()
    except Exception as e:
        log.error(f"Error reading file hash for {path}: {e}")
        return None