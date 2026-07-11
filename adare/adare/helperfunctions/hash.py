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
    h.update(yaml_data)
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


def hash_recipe(iso_sha256: str, answer_file_hash: str, identity: dict) -> str:
    """Compute the integrity anchor for a recipe environment.

    In recipe mode an environment's identity is its *build inputs*, not the
    byte-identical disk output (OS installs are never bit-reproducible). This
    combines the three inputs that determine a forensically equivalent build:

    * ``iso_sha256`` — expected SHA256 of the installer ISO.
    * ``answer_file_hash`` — SHA256 of the rendered unattended-install answer
      file (Autounattend.xml / autoinstall / preseed / kickstart / ...).
    * ``identity`` — a dict of the remaining inputs (OS profile identity, build
      params, and post-install steps), hashed order-insensitively via
      :func:`hash_dict_sha256`.

    Any change to any input yields a different recipe hash, which the caller
    treats as a new environment (never a silent in-place refresh).

    Args:
        iso_sha256: Expected SHA256 hex digest of the installer ISO.
        answer_file_hash: SHA256 hex digest of the rendered answer file.
        identity: Remaining recipe inputs to fold into the hash.

    Returns:
        SHA256 hex digest anchoring the recipe's integrity.
    """
    return combine_hashes([
        iso_sha256,
        answer_file_hash,
        hash_dict_sha256(identity),
    ])
