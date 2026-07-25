"""Shared disk image helpers for VM creators."""

import logging
import subprocess
from pathlib import Path

from adare.config import HYPERVISOR_CONFIGS
from adare.console import print_step
from adare.hypervisor.exceptions import HypervisorException
from adare.hypervisor.qemu.vm_creator.os_catalog import OsDefinition

log = logging.getLogger(__name__)


class DiskCreationError(HypervisorException):
    """Raised when qemu-img disk creation fails."""

    def __init__(self, detail: str):
        message = f"Disk creation failed: {detail}"
        super().__init__(message)


class DiskCompressionError(HypervisorException):
    """Raised when zstd-compressing a qcow2 disk fails."""

    def __init__(self, detail: str, stage: str):
        self.stage = stage  # 'convert' | 'check'
        super().__init__(f"Disk compression failed: {detail}")


def create_qcow2_disk(disk_path: Path, size: str) -> None:
    """Create an empty qcow2 disk image using qemu-img.

    Args:
        disk_path: Destination path for the new disk image.
        size: Size string understood by qemu-img (e.g. '60G', '80G').

    Raises:
        DiskCreationError: If ``qemu-img create`` exits with non-zero status.
    """
    qemu_img = HYPERVISOR_CONFIGS['qemu']['qemu_img_exe']
    cmd = [qemu_img, 'create', '-f', 'qcow2', str(disk_path), size]
    log.info(f'Creating disk image: {" ".join(cmd)}')

    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise DiskCreationError(f'qemu-img create failed: {result.stderr.strip()}')

    print_step(f'Created disk image: [dim]{disk_path}[/dim] ({size})')


def compress_qcow2_zstd(src: Path, dst: Path) -> None:
    """Convert ``src`` into a zstd-compressed qcow2 copy at ``dst``, then verify it.

    Compression is transparent to readers (QEMU decompresses on read), so the
    result is a correctness-equivalent drop-in replacement for ``src``.

    Raises:
        DiskCompressionError: If ``qemu-img convert`` or the post-conversion
            ``qemu-img check`` fails. On a failed check, ``dst`` is unlinked
            before raising so no corrupt artifact is left behind.
    """
    qemu_img = HYPERVISOR_CONFIGS['qemu']['qemu_img_exe']

    convert = subprocess.run(
        [qemu_img, 'convert', '-O', 'qcow2', '-c', '-o', 'compression_type=zstd',
         str(src), str(dst)],
        capture_output=True, text=True,
    )
    if convert.returncode != 0:
        raise DiskCompressionError(f'qemu-img convert failed: {convert.stderr.strip()}', stage='convert')

    check = subprocess.run(
        [qemu_img, 'check', str(dst)], capture_output=True, text=True,
    )
    if check.returncode != 0:
        dst.unlink(missing_ok=True)
        raise DiskCompressionError(f'qemu-img check failed on the compressed output: {check.stderr.strip()}', stage='check')


def disk_device_args(
    disk_path: Path,
    os_def: OsDefinition,
    *,
    bootindex: int = 0,
    drive_format: str = 'qcow2',
) -> list[str]:
    """Direct-QEMU -drive/-device args for the boot disk, per architecture.

    aarch64 → NVMe (native Windows driver, matches installation); writethrough
    cache (writeback corrupts under HVF). x86_64 → virtio-blk (viostor driver).
    """
    cache = 'writethrough' if os_def.architecture == 'aarch64' else 'writeback'
    args = ['-drive', f'file={disk_path},format={drive_format},if=none,id=hd0,cache={cache}']
    if os_def.architecture == 'aarch64':
        args += ['-device', f'nvme,drive=hd0,serial=boot,bootindex={bootindex}']
    else:
        args += ['-device', 'virtio-blk-pci,drive=hd0']
    return args
