"""
Disk Utilities - Standalone functions for disk operations.
"""

import json
import logging
import os
import platform
import subprocess

log = logging.getLogger(__name__)


def try_cow_clone(source: str, dest: str) -> bool:
    """
    Try to materialize ``dest`` as a copy-on-write clone of ``source``.

    On copy-on-write filesystems (APFS on macOS, Btrfs/XFS reflink on Linux)
    this produces a real, standalone, byte-identical file that shares blocks
    with ``source`` until either side is written — so a 50 GB base costs ~0
    bytes on disk yet has *no* backing-file dependency: ``source`` can later be
    rebuilt or deleted without corrupting ``dest`` (the filesystem refcounts
    shared blocks).

    Intended for qcow2-to-qcow2 instance-base creation, where it replaces a
    full ``qemu-img convert``. The caller is expected to fall back to convert
    when this returns ``False`` (unsupported filesystem, non-qcow2 result,
    etc.).

    Args:
        source: Path to the source qcow2 file (e.g. a template).
        dest: Path where the clone should be created.

    Returns:
        True only if ``dest`` was created as a valid standalone qcow2 with no
        backing file; False on any failure (a partial ``dest`` is removed).
    """
    # Remove any pre-existing dest so the clone starts clean. The dest is a
    # per-instance ULID path so a collision is unlikely, but be safe.
    try:
        if os.path.exists(dest):
            os.remove(dest)
    except OSError as e:
        log.debug(f"Could not remove pre-existing clone dest {dest}: {e}")
        return False

    # macOS: cp -c uses clonefile(2) (APFS). Linux/other: cp --reflink=auto
    # reflinks where possible and falls back to a plain copy otherwise, so it
    # never errors on non-CoW filesystems — it just yields a full copy.
    if platform.system() == 'Darwin':
        args = ['cp', '-c', source, dest]
    else:
        args = ['cp', '--reflink=auto', source, dest]

    try:
        result = subprocess.run(args, capture_output=True, text=True, check=False)
    except (OSError, subprocess.SubprocessError) as e:
        log.debug(f"CoW clone command failed to run ({args[0]}): {e}")
        _remove_partial(dest)
        return False

    if result.returncode != 0 or not os.path.exists(dest):
        log.debug(
            f"CoW clone did not produce a file (rc={result.returncode}): "
            f"{result.stderr.strip()}"
        )
        _remove_partial(dest)
        return False

    # Cheap sanity gate: confirm the clone is a standalone qcow2 with no
    # backing file. If qemu-img is unavailable or the output is unexpected,
    # fail closed so the caller falls back to a known-good convert.
    if not _is_standalone_qcow2(dest):
        _remove_partial(dest)
        return False

    return True


def _remove_partial(dest: str) -> None:
    """Best-effort removal of a partially-created clone."""
    try:
        if os.path.exists(dest):
            os.remove(dest)
    except OSError as e:
        log.debug(f"Could not remove partial clone {dest}: {e}")


def _is_standalone_qcow2(path: str) -> bool:
    """Return True if ``path`` is a qcow2 file with no backing file."""
    try:
        result = subprocess.run(
            ['qemu-img', 'info', '--output=json', path],
            capture_output=True, text=True, check=False,
        )
    except (OSError, subprocess.SubprocessError) as e:
        log.debug(f"Could not probe clone {path} with qemu-img info: {e}")
        return False

    if result.returncode != 0:
        log.debug(f"qemu-img info failed on clone {path}: {result.stderr.strip()}")
        return False

    try:
        info = json.loads(result.stdout)
    except (ValueError, TypeError) as e:
        log.debug(f"Could not parse qemu-img info for clone {path}: {e}")
        return False

    if info.get('format') != 'qcow2':
        log.debug(f"Clone {path} is not qcow2 (format={info.get('format')})")
        return False
    if info.get('backing-filename'):
        log.debug(f"Clone {path} unexpectedly has a backing file")
        return False

    return True


def get_boot_mode_for_os(guest_os: str, architecture: str = 'x86_64') -> str:
    """
    Determine appropriate boot mode based on guest OS and architecture.

    Windows VMs work better with UEFI boot when converted from VirtualBox
    or other hypervisors. Linux VMs typically work fine with either BIOS
    or UEFI, so we default to BIOS for broader compatibility.
    aarch64 (ARM) always requires UEFI — there is no BIOS on ARM.

    Args:
        guest_os: Guest OS string (e.g., 'windows', 'linux', 'Windows_10')
        architecture: Guest architecture ('x86_64' or 'aarch64')

    Returns:
        'uefi' for Windows or aarch64, 'bios' for x86_64 Linux

    Example:
        >>> get_boot_mode_for_os('Windows_10')
        'uefi'
        >>> get_boot_mode_for_os('Ubuntu_22')
        'bios'
        >>> get_boot_mode_for_os('Ubuntu_22', 'aarch64')
        'uefi'
    """
    if architecture == 'aarch64':
        return 'uefi'
    if 'windows' in guest_os.lower():
        return 'uefi'
    return 'bios'
