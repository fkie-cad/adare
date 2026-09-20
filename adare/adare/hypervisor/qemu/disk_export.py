"""
Raw/vmdk disk image export for forensic ingestion (e.g. into Autopsy).

Independent of ADARE's own metadata-level filesystem diffing
(``adare.backend.experiment.filesystem_snapshot``) — this produces a
self-contained disk image external tools can mount directly, without needing
to follow a qcow2 backing chain.
"""

import logging
import subprocess
from pathlib import Path

from adare.hypervisor.exceptions import DiskConversionException

log = logging.getLogger(__name__)

#: Formats external forensic tools can ingest directly.
SUPPORTED_FORMATS = ('raw', 'vmdk')


def export_disk_image(
        overlay_disk_path: Path | str,
        dest_path: Path | str,
        fmt: str = 'raw',
        qemu_img_exe: str = 'qemu-img',
) -> Path:
    """Convert a qcow2 overlay into a self-contained ``fmt`` image at ``dest_path``.

    ``qemu-img convert`` resolves the qcow2 backing chain transparently, so the
    output merges the experiment overlay onto its base disk into one file —
    what external tools need, since they cannot follow a backing-file chain.

    Args:
        overlay_disk_path: The experiment's qcow2 overlay disk (not the base).
        dest_path: Destination file path; parent directories are created.
        fmt: Output format, one of :data:`SUPPORTED_FORMATS`.
        qemu_img_exe: Path to the qemu-img executable to invoke.

    Returns:
        ``dest_path``, for chaining.

    Raises:
        ValueError: If ``fmt`` is not supported.
        DiskConversionException: If ``qemu-img convert`` exits non-zero.
    """
    if fmt not in SUPPORTED_FORMATS:
        raise ValueError(f"export_disk_image: unsupported format '{fmt}', expected one of {SUPPORTED_FORMATS}")

    overlay_disk_path = Path(overlay_disk_path)
    dest_path = Path(dest_path)
    dest_path.parent.mkdir(parents=True, exist_ok=True)

    cmd = [qemu_img_exe, 'convert', '-O', fmt, str(overlay_disk_path), str(dest_path)]
    log.info(f"Exporting disk image: {' '.join(cmd)}")
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise DiskConversionException(str(overlay_disk_path), 'qcow2', fmt, result.stderr.strip())

    return dest_path
