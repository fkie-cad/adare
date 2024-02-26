import hashlib
from pathlib import Path
import yaml

def hash_file_sha256(filepath: Path):
    h = hashlib.sha256()
    with open(filepath.as_posix(), 'rb', buffering=0) as f:
        for b in iter(lambda : f.read(4096), b''):
            h.update(b)
    return h.hexdigest()

def hash_dict_sha256(data: dict):
    # write dict to yaml byte array
    yaml_data = yaml.dump(data).encode()
    h = hashlib.sha256()
    for b in iter(lambda : yaml_data.read(4096), b''):
        h.update(b)
    return h.hexdigest()


def hash_string_sha256(data: str, encoding='utf-8'):
    h = hashlib.sha256()
    h.update(data.encode(encoding=encoding))
    return h.hexdigest()

def combine_hashes(hashes: list):
    h = hashlib.sha256()
    for single_hash in hashes:
        h.update(single_hash.encode())
    return h.hexdigest()