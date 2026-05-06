"""ISO extraction utilities using pycdlib (pure Python, cross-platform)."""

import hashlib
import logging
from pathlib import Path

from adare.hypervisor.exceptions import HypervisorException

log = logging.getLogger(__name__)


# UEFI Shell auto-boot script for aarch64 Windows installation.
# NVRAM is pre-populated with Shell as Boot0000 (see firmware.py), so the
# firmware auto-launches Shell which then auto-executes this startup.nsh.
# Strategy: try Windows Boot Manager first (Phase 2 — only on NVMe after install),
# then generic EFI boot loader (Phase 1 — on Windows ISO).
# map -r forces device re-enumeration in case USB devices weren't mapped yet.
_STARTUP_NSH = "\r\n".join([
    "@echo -off",
    "map -r",
    r"FS0:\EFI\Microsoft\Boot\bootmgfw.efi",
    r"FS1:\EFI\Microsoft\Boot\bootmgfw.efi",
    r"FS2:\EFI\Microsoft\Boot\bootmgfw.efi",
    r"FS3:\EFI\Microsoft\Boot\bootmgfw.efi",
    r"FS0:\EFI\BOOT\BOOTAA64.EFI",
    r"FS1:\EFI\BOOT\BOOTAA64.EFI",
    r"FS2:\EFI\BOOT\BOOTAA64.EFI",
    r"FS3:\EFI\BOOT\BOOTAA64.EFI",
    "",
])


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
        raise FileNotFoundError(f'{iso_file_path} not found via {mode}') from None

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
        upper = upper + '.;1' if '.' not in upper else upper + ';1'
        iso_parts.append(upper)
    return '/' + '/'.join(iso_parts)


def create_cidata_iso(autoinstall_dir: Path, output_path: Path) -> Path:
    """Create a minimal ISO with volume label 'cidata' for cloud-init NoCloud.

    Cloud-init auto-detects an attached drive with the label 'cidata' and reads
    user-data / meta-data from it. Used as the autoinstall datasource for both
    x86_64 and aarch64; avoids the deprecated `ds=nocloud-net;seedfrom=...` HTTP
    flow which is unreliable on cloud-init 24+ (Ubuntu 25.10 / 26.04).

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


def create_autounattend_iso(xml_content: bytes, output_path: Path) -> Path:
    """Create a small ISO9660 image containing Autounattend.xml.

    Used on ARM64 where there's no floppy controller. Windows Setup searches
    optical media (CD-ROM) for Autounattend.xml, so we attach this ISO as
    a USB cdrom device.

    Args:
        xml_content: UTF-8 encoded Autounattend.xml content
        output_path: Where to write the ISO file

    Returns:
        Path to the created ISO
    """
    import io

    import pycdlib

    iso = pycdlib.PyCdlib()
    iso.new(
        interchange_level=3,
        sys_ident='LINUX',
        vol_ident='AAINSTALL',
        joliet=3,
        rock_ridge='1.09',
    )
    iso.add_fp(
        fp=io.BytesIO(xml_content),
        length=len(xml_content),
        iso_path='/AUTOUNATTEND.XML;1',
        joliet_path='/Autounattend.xml',
        rr_name='Autounattend.xml',
    )
    iso.write(str(output_path))
    iso.close()

    log.info(f'Created Autounattend ISO: {output_path} ({output_path.stat().st_size} bytes)')
    return output_path


def create_tools_iso(xml_content: bytes, virtio_iso_path: Path, output_path: Path) -> Path:
    """Create a combined ISO containing Autounattend.xml and virtio-win guest tools.

    Matches UTM's proven approach for ARM64: bundle the answer file and guest tools
    into a single ISO, attached as the second USB CD-ROM. This reduces the USB
    CD-ROM count from 3 to 2, which is critical for Windows Setup to find
    the Autounattend.xml.

    Uses system ISO tools (hdiutil on macOS, mkisofs/genisoimage on Linux)
    matching UTM's exact mkisofs flags. Falls back to pycdlib if unavailable.

    Args:
        xml_content: UTF-8 encoded Autounattend.xml content
        virtio_iso_path: Path to the virtio-win ISO (to extract guest tools exe)
        output_path: Where to write the combined ISO

    Returns:
        Path to the created ISO
    """
    import tempfile

    with tempfile.TemporaryDirectory(prefix='adare-toolsiso-') as tmpdir:
        tools_dir = Path(tmpdir) / 'tools'
        tools_dir.mkdir()

        (tools_dir / 'Autounattend.xml').write_bytes(xml_content)
        (tools_dir / 'startup.nsh').write_bytes(_STARTUP_NSH.encode('ascii'))

        # Guest tools exe bundling disabled - causes Windows Setup crash on ARM64
        # (likely ISO size/format issue with hdiutil). Guest tools installed
        # separately after first boot instead.
        # _extract_guest_tools_exe(virtio_iso_path, tools_dir)

        _build_tools_iso(tools_dir, output_path)

    log.info(f'Created tools ISO: {output_path} ({output_path.stat().st_size} bytes)')
    return output_path


def _extract_guest_tools_exe(virtio_iso_path: Path, output_dir: Path) -> None:
    """Extract virtio-win-guest-tools.exe from the virtio-win ISO.

    Tries Joliet, Rock Ridge, then scans ISO9660 root directory.
    """
    import pycdlib
    from pycdlib.pycdlibexception import PyCdlibException

    exe_name = 'virtio-win-guest-tools.exe'
    output_file = output_dir / exe_name

    iso = pycdlib.PyCdlib()
    try:
        iso.open(str(virtio_iso_path))
    except PyCdlibException as e:
        raise ISOExtractionError(str(virtio_iso_path), f'Failed to open: {e}') from e

    try:
        # Try direct paths: Joliet, Rock Ridge
        for mode, path in [
            ('joliet_path', f'/{exe_name}'),
            ('rr_path', f'/{exe_name}'),
        ]:
            try:
                with open(output_file, 'wb') as f:
                    iso.get_file_from_iso_fp(f, **{mode: path})
                log.info(f'Extracted {exe_name} using {mode}')
                return
            except PyCdlibException:
                continue

        # Fallback: scan ISO9660 root directory for the exe
        # (virtio-win ISO may lack Joliet; ISO9660 names are mangled)
        for child in iso.list_children(iso_path='/'):
            ident = child.file_identifier().decode('ascii', errors='replace')
            if ident in ('.', '..'):
                continue
            if 'VIRTIO' in ident.upper() and ident.upper().endswith('.EXE;1'):
                with open(output_file, 'wb') as f:
                    iso.get_file_from_iso_fp(f, iso_path=f'/{ident}')
                log.info(f'Extracted {ident} as {exe_name} (ISO9660 scan)')
                return

        raise ISOExtractionError(
            str(virtio_iso_path),
            f'{exe_name} not found in virtio-win ISO'
        )
    finally:
        iso.close()


def _build_tools_iso(source_dir: Path, output_path: Path) -> None:
    """Build an ISO from a directory using platform-appropriate tools.

    macOS: hdiutil makehybrid (always available)
    Linux: mkisofs or genisoimage (matching UTM's exact flags)
    Fallback: pycdlib (pure Python)
    """
    import platform
    import shutil
    import subprocess

    if platform.system() == 'Darwin':
        subprocess.run(
            ['hdiutil', 'makehybrid', '-iso', '-joliet',
             '-default-volume-name', 'AAINSTALL',
             '-o', str(output_path), str(source_dir)],
            check=True, capture_output=True,
        )
        return

    for tool in ('mkisofs', 'genisoimage'):
        if shutil.which(tool):
            subprocess.run(
                [tool, '-J', '-rational-rock', '-full-iso9660-filenames',
                 '-V', 'AAINSTALL', '-quiet',
                 '-o', str(output_path), str(source_dir)],
                check=True, capture_output=True,
            )
            return

    _build_tools_iso_pycdlib(source_dir, output_path)


def _build_tools_iso_pycdlib(source_dir: Path, output_path: Path) -> None:
    """Build an ISO from a directory using pycdlib (fallback when system tools unavailable)."""
    import io

    import pycdlib

    iso = pycdlib.PyCdlib()
    iso.new(
        interchange_level=3,
        sys_ident='LINUX',
        vol_ident='AAINSTALL',
        joliet=3,
        rock_ridge='1.09',
    )

    for file_path in sorted(source_dir.iterdir()):
        if not file_path.is_file():
            continue
        content = file_path.read_bytes()
        name = file_path.name
        iso_name = name.upper().replace('-', '_')
        if '.' not in iso_name:
            iso_name += '.;1'
        else:
            iso_name += ';1'
        iso.add_fp(
            fp=io.BytesIO(content),
            length=len(content),
            iso_path=f'/{iso_name}',
            joliet_path=f'/{name}',
            rr_name=name,
        )

    iso.write(str(output_path))
    iso.close()


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
