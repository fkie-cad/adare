"""Work-overlay create + flatten — shared by interactive extend and provisioning.

Both ``env extend --interactive`` and recipe build-time provisioning need the
same two-step trick: boot a throwaway qcow2 overlay backed by an immutable base,
then flatten the result into a standalone qcow2 with no backing file.

Overlay-then-flatten (rather than clone-then-mutate) buys two things:

* **Peak disk.** Flattening a 10 GB overlay over a 51 GB base peaks at ~61 GB
  instead of the ~96 GB a full clone plus its output would need.
* **A provably unmutated base.** The base is only ever opened read-only through
  the overlay's backing chain, so a failed provisioning run cannot corrupt the
  cached base disk that took two hours to install.

Extracted here so the two callers cannot drift apart on backing-file flags or on
the "no backing file in the output" invariant.
"""

import logging
import subprocess
from pathlib import Path

from adare.config import HYPERVISOR_CONFIGS
from adare.console import print_step
from adare.hypervisor.exceptions import HypervisorException
from adare.hypervisor.qemu.vm_creator.disk_helpers import (
    DiskCompressionError,
    compress_qcow2_zstd,
)

log = logging.getLogger(__name__)

__all__ = ['create_work_overlay', 'flatten_overlay']


def create_work_overlay(base_disk: Path, overlay_path: Path) -> Path:
    """Create a qcow2 overlay at *overlay_path* backed by *base_disk*.

    The backing path is recorded absolute, mirroring
    ``hypervisor/qemu/mixins/disk.py`` for the cross-directory / external case:
    a relative backing path breaks the moment the overlay is read from a
    different working directory.

    Returns:
        *overlay_path*, for call-site convenience.

    Raises:
        HypervisorException: If *base_disk* is missing or ``qemu-img create``
            fails.
    """
    base_disk = base_disk.resolve()
    if not base_disk.is_file():
        raise HypervisorException(f'Base disk not found: {base_disk}')

    qemu_img = HYPERVISOR_CONFIGS['qemu']['qemu_img_exe']
    create_cmd = [
        qemu_img, 'create', '-f', 'qcow2', '-F', 'qcow2',
        '-b', str(base_disk), str(overlay_path),
    ]
    log.info('Creating work overlay: %s', ' '.join(create_cmd))
    result = subprocess.run(create_cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise HypervisorException(
            f'Failed to create work overlay: {result.stderr.strip()}'
        )
    return overlay_path


def flatten_overlay(overlay_path: Path, dest_disk: Path, compress: bool = True) -> Path:
    """Flatten *overlay_path* and its backing chain into a standalone *dest_disk*.

    The output has **no backing file** — it is an immutable base exactly like
    ``vm create`` output, and flows through the identical experiment-runtime path.
    (A persistent overlay would be invisible at runtime: the runtime overlay
    machinery always rebuilds on the TRUE base and refuses to chain.)

    Args:
        overlay_path: The overlay to flatten. Read only.
        dest_disk: Destination standalone qcow2.
        compress: Zstd-compress the output. Compression is transparent to readers
            (QEMU decompresses on read), so it is a correctness-equivalent
            drop-in. On compression failure this falls back to a plain flatten
            rather than losing a completed build.

    Returns:
        *dest_disk*.

    Raises:
        HypervisorException: If the plain ``qemu-img convert`` fallback also
            fails.
    """
    if compress:
        try:
            compress_qcow2_zstd(overlay_path, dest_disk)
            print_step(f'Flattened + compressed standalone disk: [dim]{dest_disk}[/dim]')
            return dest_disk
        except DiskCompressionError as e:
            log.warning('Disk compression failed, falling back to plain flatten: %s', e)
            print_step(
                f'[yellow]Disk compression failed, falling back to plain flatten:[/yellow] {e}'
            )
            dest_disk.unlink(missing_ok=True)

    qemu_img = HYPERVISOR_CONFIGS['qemu']['qemu_img_exe']
    convert_cmd = [qemu_img, 'convert', '-O', 'qcow2', str(overlay_path), str(dest_disk)]
    log.info('Flattening overlay: %s', ' '.join(convert_cmd))
    result = subprocess.run(convert_cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise HypervisorException(
            f'Failed to flatten overlay into standalone disk: {result.stderr.strip()}'
        )
    print_step(f'Flattened standalone disk: [dim]{dest_disk}[/dim]')
    return dest_disk
