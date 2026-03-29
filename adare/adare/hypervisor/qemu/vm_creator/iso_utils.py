"""ISO extraction utilities using pycdlib (pure Python, cross-platform)."""

import hashlib
from pathlib import Path

from adare.hypervisor.exceptions import HypervisorException

import logging
log = logging.getLogger(__name__)


class ISOExtractionError(HypervisorException):
    """Raised when ISO extraction fails."""

    def __init__(self, iso_path: str, detail: str):
        message = f"Failed to extract from ISO '{iso_path}': {detail}"
        super().__init__(message)


def extract_kernel_and_initrd(
    iso_path: Path,
    kernel_iso_path: str,
    initrd_iso_path: str,
    output_dir: Path,
) -> tuple[Path, Path]:
    """Extract kernel (vmlinuz) and initrd from an Ubuntu Server ISO.

    Uses pycdlib for pure-Python ISO reading - works on Linux and macOS
    without xorriso, 7z, or mount.

    Args:
        iso_path: Path to the Ubuntu Server ISO file
        kernel_iso_path: Path to vmlinuz inside the ISO (e.g. '/casper/vmlinuz')
        initrd_iso_path: Path to initrd inside the ISO (e.g. '/casper/initrd')
        output_dir: Directory to write extracted files to

    Returns:
        Tuple of (kernel_path, initrd_path) on the local filesystem

    Raises:
        ISOExtractionError: If extraction fails
    """
    import pycdlib

    output_dir.mkdir(parents=True, exist_ok=True)
    kernel_out = output_dir / 'vmlinuz'
    initrd_out = output_dir / 'initrd'

    log.info(f'Extracting kernel and initrd from {iso_path}')

    iso = pycdlib.PyCdlib()
    try:
        iso.open(str(iso_path))
    except pycdlib.PyCdlibException as e:
        raise ISOExtractionError(str(iso_path), f'Failed to open ISO: {e}') from e

    try:
        # Try Joliet first (longer filenames), fall back to Rock Ridge, then ISO9660
        for extract_mode in ('joliet_path', 'rr_path', 'iso_path'):
            try:
                _extract_file(iso, extract_mode, kernel_iso_path, kernel_out)
                _extract_file(iso, extract_mode, initrd_iso_path, initrd_out)
                log.info(f'Extracted kernel and initrd using {extract_mode}')
                return kernel_out, initrd_out
            except (pycdlib.PyCdlibException, FileNotFoundError):
                continue

        # If all modes failed, try ISO9660 with uppercase 8.3 names
        try:
            iso9660_kernel = _to_iso9660_path(kernel_iso_path)
            iso9660_initrd = _to_iso9660_path(initrd_iso_path)
            _extract_file(iso, 'iso_path', iso9660_kernel, kernel_out)
            _extract_file(iso, 'iso_path', iso9660_initrd, initrd_out)
            log.info('Extracted kernel and initrd using ISO9660 8.3 names')
            return kernel_out, initrd_out
        except (pycdlib.PyCdlibException, FileNotFoundError):
            pass

        raise ISOExtractionError(
            str(iso_path),
            f'Could not find {kernel_iso_path} and {initrd_iso_path} in the ISO. '
            'The ISO may not be an Ubuntu Server installation image.'
        )
    finally:
        iso.close()


def _extract_file(iso, mode: str, iso_file_path: str, output_path: Path) -> None:
    """Extract a single file from an opened ISO."""
    import pycdlib

    kwargs = {mode: iso_file_path}
    try:
        iso.get_record(**kwargs)
    except pycdlib.PyCdlibException:
        raise FileNotFoundError(f'{iso_file_path} not found via {mode}')

    with open(output_path, 'wb') as f:
        iso.get_file_from_iso_fp(f, **kwargs)

    log.debug(f'Extracted {iso_file_path} -> {output_path} ({output_path.stat().st_size} bytes)')


def _to_iso9660_path(path: str) -> str:
    """Convert a Unix path to ISO9660 Level 1 format (uppercase, 8.3, with version).

    Example: /casper/vmlinuz -> /CASPER/VMLINUZ.;1
    """
    parts = path.strip('/').split('/')
    iso_parts = []
    for part in parts:
        upper = part.upper()
        if '.' not in upper:
            upper = upper + '.;1'
        else:
            upper = upper + ';1'
        iso_parts.append(upper)
    return '/' + '/'.join(iso_parts)


def create_cidata_iso(autoinstall_dir: Path, output_path: Path) -> Path:
    """Create a minimal ISO with volume label 'cidata' for cloud-init NoCloud.

    Cloud-init auto-detects an attached drive with the label 'cidata' and reads
    user-data / meta-data from it. This avoids the need for direct kernel boot
    with ds=nocloud-net, which doesn't work reliably on aarch64 UEFI.

    Args:
        autoinstall_dir: Directory containing user-data and meta-data files
        output_path: Where to write the ISO file

    Returns:
        Path to the created ISO
    """
    import pycdlib

    user_data = (autoinstall_dir / 'user-data').read_bytes()
    meta_data = (autoinstall_dir / 'meta-data').read_bytes()

    iso = pycdlib.PyCdlib()
    iso.new(
        interchange_level=3,
        sys_ident='LINUX',
        vol_ident='cidata',
        joliet=3,
        rock_ridge='1.09',
    )

    iso.add_fp(
        fp=__import__('io').BytesIO(user_data),
        length=len(user_data),
        iso_path='/USER_DATA.;1',
        joliet_path='/user-data',
        rr_name='user-data',
    )
    iso.add_fp(
        fp=__import__('io').BytesIO(meta_data),
        length=len(meta_data),
        iso_path='/META_DATA.;1',
        joliet_path='/meta-data',
        rr_name='meta-data',
    )

    iso.write(str(output_path))
    iso.close()

    log.info(f'Created cidata ISO: {output_path} ({output_path.stat().st_size} bytes)')
    return output_path


def verify_iso_hash(iso_path: Path, expected_sha256: str) -> bool:
    """Verify the SHA256 hash of an ISO file.

    Args:
        iso_path: Path to the ISO file
        expected_sha256: Expected SHA256 hex digest

    Returns:
        True if hash matches
    """
    if not expected_sha256:
        log.warning(f'No SHA256 hash provided for {iso_path}, skipping verification')
        return True

    log.info(f'Verifying SHA256 hash of {iso_path}...')
    sha256 = hashlib.sha256()
    with open(iso_path, 'rb') as f:
        while True:
            chunk = f.read(8192)
            if not chunk:
                break
            sha256.update(chunk)

    actual = sha256.hexdigest()
    if actual != expected_sha256:
        log.error(f'SHA256 mismatch for {iso_path}: expected {expected_sha256}, got {actual}')
        return False

    log.info('SHA256 hash verified successfully')
    return True
