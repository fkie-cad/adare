import hashlib
from pathlib import Path

def hash_file_sha256(filepath: Path):
    h = hashlib.sha256()
    with open(filepath.as_posix(), 'rb', buffering=0) as f:
        for b in iter(lambda : f.read(4096), b''):
            h.update(b)
    return h.hexdigest()

def combine_hashes(hashes: list):
    h = hashlib.sha256()
    for hash in hashes:
        h.update(hash.encode())
    return h.hexdigest()