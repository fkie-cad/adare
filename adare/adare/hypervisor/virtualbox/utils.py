"""
VirtualBox API utility functions.
"""
import hashlib
import logging
import subprocess

log = logging.getLogger(__name__)


def run_subprocess(cmd, *, check=True, capture_output=True, text=True, log_prefix="", timeout=30):
    try:
        return subprocess.run(
            cmd,
            check=check,
            stdout=subprocess.PIPE if capture_output else None,
            stderr=subprocess.PIPE if capture_output else None,
            text=text,
            timeout=timeout
        )
    except subprocess.CalledProcessError as e:
        log.error(f"{log_prefix}Subprocess failed: {e}")
        if capture_output:
            log.error(f"{log_prefix}stdout: {e.stdout}")
            log.error(f"{log_prefix}stderr: {e.stderr}")
        raise
    except subprocess.TimeoutExpired as e:
        log.error(f"{log_prefix}Subprocess timed out after {timeout} seconds: {' '.join(cmd)}")
        log.error(f"{log_prefix}Command: {e.cmd}")
        log.error(f"{log_prefix}Timeout: {e.timeout}s")
        if capture_output and e.stdout:
            log.error(f"{log_prefix}Partial stdout: {e.stdout[:500]}")
        if capture_output and e.stderr:
            log.error(f"{log_prefix}Partial stderr: {e.stderr[:500]}")
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
