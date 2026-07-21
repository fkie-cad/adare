"""ISO extraction utilities using pycdlib (pure Python, cross-platform)."""

import hashlib
import logging
from pathlib import Path

from adare.hypervisor.exceptions import HypervisorException

log = logging.getLogger(__name__)


# Marker file that identifies the ADARE legacy-boot override ISO (see
# create_legacy_boot_iso). Its presence on a mapped filesystem tells startup.nsh
# to boot that volume's Windows Boot Manager — which carries a patched boot.wim
# that forces Windows Setup into legacy mode on Win11 24H2/25H2 (ConX).
_LEGACY_BOOT_MARKER = 'ADARELGB.MRK'

# Number of UEFI filesystem handles (FS0..FSn-1) to probe. QEMU install phases
# attach at most a handful of USB CD-ROMs + the NVMe disk, so 10 is ample.
_FS_PROBE_COUNT = 10


def _build_startup_nsh() -> str:
    """Build the UEFI Shell auto-boot script for aarch64 Windows installation.

    NVRAM is pre-populated with Shell as Boot0000 (see firmware.py), so the
    firmware auto-launches Shell which then auto-executes this startup.nsh.

    Boot strategy, in order:
      1. If any mapped filesystem carries the legacy-boot marker (install phase
         only — the override ISO is attached only while booting from ISO), boot
         that volume's Windows Boot Manager. This loads the patched boot.wim.
      2. Otherwise fall back to the Windows Boot Manager / generic EFI loader on
         the remaining volumes — this is the post-install disk boot (Phase 2),
         where no override ISO (and thus no marker) is present.

    map -r forces device re-enumeration in case USB devices weren't mapped yet.
    Flat `if exist ... then / endif` blocks are used instead of a `for` loop to
    stay within the most conservative UEFI Shell syntax.
    """
    lines = ['@echo -off', 'map -r']
    for i in range(_FS_PROBE_COUNT):
        lines.append(f'if exist FS{i}:\\{_LEGACY_BOOT_MARKER} then')
        lines.append(f'  FS{i}:\\EFI\\BOOT\\BOOTAA64.EFI')
        lines.append('endif')
    for i in range(4):
        lines.append(rf'FS{i}:\EFI\Microsoft\Boot\bootmgfw.efi')
    for i in range(4):
        lines.append(rf'FS{i}:\EFI\BOOT\BOOTAA64.EFI')
    lines.append('')
    return '\r\n'.join(lines)


_STARTUP_NSH = _build_startup_nsh()


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
    """Extract kernel (vmlinuz) and initrd from an installation ISO.

    Uses pycdlib for pure-Python ISO reading - works on Linux and macOS
    without xorriso, 7z, or mount.

    Args:
        iso_path: Path to the installation ISO file
        kernel_iso_path: Path to vmlinuz inside the ISO (e.g. ``/casper/vmlinuz``,
            ``/install.amd/vmlinuz``, ``/images/pxeboot/vmlinuz``)
        initrd_iso_path: Path to initrd inside the ISO
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
            'The ISO does not appear to contain a kernel/initrd at the '
            'expected locations for this distro.'
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


def create_seed_iso(autoinstall_dir: Path, output_path: Path, *, label: str = 'cidata') -> Path:
    """Create a seed ISO from every file in ``autoinstall_dir``.

    The volume label drives auto-detection by the target installer:

    * ``cidata`` — cloud-init NoCloud (Ubuntu Subiquity, Arch w/ cloud-init).
    * ``OEMDRV`` — debian-installer (preseed.cfg) and Anaconda (ks.cfg).
    * any label — AutoYaST and friends that take a device path on the kernel
      command line; the label is then informational.

    Joliet long-name and Rock Ridge entries are emitted so the guest sees the
    canonical filenames (``user-data``, ``preseed.cfg``, ``ks.cfg``,
    ``autoinst.xml``, ...) regardless of which name namespace it consults.

    Args:
        autoinstall_dir: Directory whose files become the ISO contents
        output_path: Where to write the ISO file
        label: Volume label (max 32 chars, ``-V`` semantics)

    Returns:
        Path to the created ISO
    """
    import io

    import pycdlib

    iso = pycdlib.PyCdlib()
    iso.new(
        interchange_level=3,
        sys_ident='LINUX',
        vol_ident=label,
        joliet=3,
        rock_ridge='1.09',
    )

    for entry in sorted(autoinstall_dir.iterdir()):
        if not entry.is_file():
            continue
        content = entry.read_bytes()
        name = entry.name
        iso_name = name.upper().replace('-', '_').replace('.', '_', name.count('.') - 1)
        iso_name = iso_name + ('.;1' if '.' not in iso_name else ';1')
        iso.add_fp(
            fp=io.BytesIO(content),
            length=len(content),
            iso_path=f'/{iso_name}',
            joliet_path=f'/{name}',
            rr_name=name,
        )

    iso.write(str(output_path))
    iso.close()

    log.info(f'Created seed ISO ({label}): {output_path} ({output_path.stat().st_size} bytes)')
    return output_path


def create_cidata_iso(autoinstall_dir: Path, output_path: Path) -> Path:
    """Create a 'cidata'-labeled seed ISO (cloud-init NoCloud).

    Thin wrapper around :func:`create_seed_iso` for callers that specifically
    want the historical Subiquity / cloud-init layout.
    """
    return create_seed_iso(autoinstall_dir, output_path, label='cidata')


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


def _build_tools_iso(
    source_dir: Path,
    output_path: Path,
    *,
    volume_label: str = 'AAINSTALL',
    udf: bool = False,
) -> None:
    """Build an ISO from a directory using platform-appropriate tools.

    macOS: hdiutil makehybrid (always available)
    Linux: mkisofs or genisoimage (matching UTM's exact flags)
    Fallback: pycdlib (pure Python)

    Args:
        volume_label: ISO volume identifier.
        udf: If True, emit a UDF filesystem in addition to ISO9660/Joliet. The
            legacy-boot override ISO uses this so edk2 reads it exactly like a
            stock Windows ISO (which is UDF) — preserving the nested \\EFI and
            \\sources tree and long/cased filenames the Windows Boot Manager
            expects. The pycdlib fallback cannot produce UDF and is not used for
            bootable media.
    """
    import platform
    import shutil
    import subprocess

    if platform.system() == 'Darwin':
        cmd = ['hdiutil', 'makehybrid', '-iso', '-joliet']
        if udf:
            cmd += ['-udf', '-udf-volume-name', volume_label]
        cmd += ['-default-volume-name', volume_label,
                '-o', str(output_path), str(source_dir)]
        subprocess.run(cmd, check=True, capture_output=True)
        return

    for tool in ('mkisofs', 'genisoimage'):
        if shutil.which(tool):
            cmd = [tool, '-J', '-rational-rock', '-full-iso9660-filenames']
            if udf:
                cmd += ['-udf']
            cmd += ['-V', volume_label, '-quiet', '-o', str(output_path), str(source_dir)]
            subprocess.run(cmd, check=True, capture_output=True)
            return

    if udf:
        raise ISOExtractionError(
            str(output_path),
            'No system ISO tool (hdiutil/mkisofs/genisoimage) available to build '
            'a UDF bootable ISO; pycdlib fallback cannot produce bootable media.',
        )
    _build_tools_iso_pycdlib(source_dir, output_path)


# ---------------------------------------------------------------------------
# Legacy-boot override ISO (Win11 24H2/25H2 "ConX" setup workaround)
# ---------------------------------------------------------------------------
# Windows 11 24H2/25H2 ship a redesigned Setup front-end ("ConX", SetupPrep.exe)
# that no longer honors an Autounattend.xml supplied on removable media — Setup
# stalls interactively at the product-key/OOBE screens. The community-confirmed
# fix is to force the *legacy* setup.exe path by placing a winpeshl.ini inside
# the WinPE image (boot.wim) that runs `setup.exe /legacy`.
#
# The Windows ISO is attached read-only and its install.wim is >4 GB inside a
# UDF filesystem, so we do NOT rebuild it. Instead we build a small override ISO
# carrying only a *patched* boot.wim plus the ISO's EFI boot tree; the UEFI Shell
# boots this override (identified by a marker file), WinPE runs setup.exe /legacy,
# and Setup finds the untouched install.wim on the original ISO (still attached).

_WINPESHL_INI = (
    '[LaunchApps]\r\n'
    '%SystemDrive%\\sources\\setup.exe, /legacy\r\n'
)

# boot.wim image index that Windows install media boots ("Windows Setup"); the
# generic "Windows PE" image (index 1) does not carry setup.exe.
_SETUP_WIM_INDEX = 2


def create_legacy_boot_iso(
    windows_iso_path: Path,
    xml_content: bytes,
    output_path: Path,
) -> Path:
    """Build a UEFI-bootable override ISO that forces Windows Setup into legacy mode.

    Extracts the EFI boot tree and boot.wim from ``windows_iso_path``, injects a
    winpeshl.ini (``setup.exe /legacy``) into the boot.wim "Windows Setup" image,
    and packages them — with the legacy-boot marker and the Autounattend.xml — as
    a small UDF ISO. The original Windows ISO is left untouched and must stay
    attached alongside this override to supply install.wim.

    Requires ``wimlib-imagex`` (patch boot.wim) and ``7z`` (read the UDF source
    ISO). Both are validated by check_prerequisites for aarch64 Windows builds.
    """
    import subprocess
    import tempfile

    with tempfile.TemporaryDirectory(prefix='adare-legacyboot-') as tmpdir:
        tmp = Path(tmpdir)
        stage = tmp / 'iso'
        stage.mkdir()

        # 1. Extract the EFI boot tree + boot.wim from the (UDF) Windows ISO.
        #    7z reads UDF; the paths are lowercase as stored on the ISO.
        _extract_with_7z(windows_iso_path, ['efi', 'sources/boot.wim'], stage)

        boot_wim = stage / 'sources' / 'boot.wim'
        if not boot_wim.is_file():
            raise ISOExtractionError(
                str(windows_iso_path),
                'sources/boot.wim not found in Windows ISO — cannot build legacy-boot ISO.',
            )

        # 2. Patch the "Windows Setup" image with winpeshl.ini -> setup.exe /legacy.
        winpeshl = tmp / 'winpeshl.ini'
        winpeshl.write_bytes(_WINPESHL_INI.encode('ascii'))
        subprocess.run(
            ['wimlib-imagex', 'update', str(boot_wim), str(_SETUP_WIM_INDEX),
             '--command', f'add {winpeshl} /Windows/System32/winpeshl.ini'],
            check=True, capture_output=True,
        )

        # 3. Add the marker (so startup.nsh boots this volume) + the answer file.
        (stage / _LEGACY_BOOT_MARKER).write_bytes(b'ADARE legacy-boot override\r\n')
        (stage / 'Autounattend.xml').write_bytes(xml_content)

        # 4. Build the bootable override ISO (UDF, like a stock Windows ISO).
        _build_tools_iso(stage, output_path, volume_label='AABOOT', udf=True)

    log.info(f'Created legacy-boot override ISO: {output_path} ({output_path.stat().st_size} bytes)')
    return output_path


def _extract_with_7z(archive: Path, members: list[str], dest_dir: Path) -> None:
    """Extract specific members from an archive into dest_dir, preserving paths.

    Uses 7z (handles UDF Windows ISOs, including >4 GB sibling files that trip up
    xorriso). Raises ISOExtractionError if 7z is missing or the extract fails.
    """
    import shutil
    import subprocess

    sevenzip = shutil.which('7z') or shutil.which('7zz') or shutil.which('7za')
    if not sevenzip:
        raise ISOExtractionError(
            str(archive),
            '7z not found — required to extract boot files from the Windows ISO. '
            'Install with: brew install p7zip (macOS) / apt install p7zip-full (Linux).',
        )
    result = subprocess.run(
        [sevenzip, 'x', str(archive), f'-o{dest_dir}', '-y', *members],
        capture_output=True, text=True,
    )
    if result.returncode != 0:
        raise ISOExtractionError(
            str(archive),
            f'7z extract failed ({result.returncode}): {result.stderr.strip() or result.stdout.strip()}',
        )


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
