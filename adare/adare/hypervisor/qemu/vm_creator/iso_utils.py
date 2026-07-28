"""ISO extraction utilities using pycdlib (pure Python, cross-platform)."""

import hashlib
import logging
from pathlib import Path

from adare.hypervisor.exceptions import HypervisorException

log = logging.getLogger(__name__)


# UEFI Shell auto-boot script for aarch64 Windows installation.
# NVRAM is pre-populated with Shell as Boot0000 (see firmware.py), so the
# firmware auto-launches Shell which then auto-executes this startup.nsh.
#
# In the INSTALL phase the firmware auto-boots the legacy-boot override ISO
# directly via its El Torito UEFI record (a USB "HARDDRIVE" boot entry the
# firmware tries before the Shell), so startup.nsh is not reached then. This
# script matters for the POST-INSTALL disk boot (Phase 2, no override attached):
# try the Windows Boot Manager on the installed NVMe, then a generic loader.
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
# UDF filesystem, so we do NOT rebuild it. Instead we build a small, *bootable*
# override ISO that reproduces the stock ISO's exact UEFI boot chain — its El
# Torito boot image (efisys.bin), root bootmgr(fw).efi, \boot and \efi trees —
# but with a *patched* boot.wim. Attached as the first USB device, the firmware
# El-Torito-boots it (a USB "HARDDRIVE" entry tried before the Shell), WinPE runs
# setup.exe /legacy, and Setup finds the untouched install.wim on the original
# ISO (kept attached). Requires wimlib-imagex (patch boot.wim) + 7z (read the UDF
# source) + xorriso (build the El Torito ISO) — validated in check_prerequisites.

_WINPESHL_INI = (
    '[LaunchApps]\r\n'
    '%SystemDrive%\\sources\\setup.exe, /legacy\r\n'
)

# boot.wim image index that Windows install media boots ("Windows Setup"); the
# generic "Windows PE" image (index 1) does not carry setup.exe.
_SETUP_WIM_INDEX = 2

# Boot-chain members copied verbatim from the stock Windows ISO (everything the
# UEFI boot needs EXCEPT the >4 GB sources/install.wim, which stays on the
# original ISO). boot.wim is the only file we modify.
_BOOT_CHAIN_MEMBERS = ['efi', 'boot', 'bootmgr.efi', 'bootmgfw.efi', 'sources/boot.wim']

# Name of the El Torito UEFI boot image on the override ISO (Microsoft's FAT
# "efisys" image, extracted from the source ISO's boot catalog).
_EFI_BOOT_IMG = 'efisys.bin'


def create_legacy_boot_iso(
    windows_iso_path: Path,
    xml_content: bytes,
    output_path: Path,
) -> Path:
    """Build a UEFI El-Torito-bootable override ISO that forces legacy Windows Setup.

    Reproduces the stock ISO's boot chain with a boot.wim patched to run
    ``setup.exe /legacy`` (bypassing the 24H2/25H2 "ConX" front-end that ignores
    the answer file). The original Windows ISO is left untouched and must stay
    attached alongside this override to supply install.wim.
    """
    import shutil
    import subprocess
    import tempfile

    with tempfile.TemporaryDirectory(prefix='adare-legacyboot-') as tmpdir:
        tmp = Path(tmpdir)
        stage = tmp / 'iso'
        stage.mkdir()

        # 1. Extract the boot chain (not install.wim) from the (UDF) Windows ISO.
        _extract_with_7z(windows_iso_path, _BOOT_CHAIN_MEMBERS, stage)

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

        # 3. Extract the source ISO's El Torito UEFI boot image + add the answer file.
        _extract_eltorito_efi_image(windows_iso_path, stage / _EFI_BOOT_IMG)
        (stage / 'Autounattend.xml').write_bytes(xml_content)

        # 4. Build the bootable override ISO (El Torito UEFI, no emulation).
        _build_bootable_iso(stage, output_path, volume_label='AABOOT', efi_boot_img=_EFI_BOOT_IMG)

    log.info(f'Created legacy-boot override ISO: {output_path} ({output_path.stat().st_size} bytes)')
    return output_path


def _extract_eltorito_efi_image(iso_path: Path, output_path: Path) -> None:
    """Extract the UEFI El Torito boot image (efisys.bin) from a Windows ISO.

    Reads the boot image's LBA + load size from ``xorriso -report_el_torito`` and
    slices the bytes out of the ISO directly. This works even though xorriso can
    not read the ISO's UDF file tree — the El Torito catalog is addressed by LBA,
    independent of the filesystem.
    """
    import subprocess

    result = subprocess.run(
        ['xorriso', '-indev', str(iso_path), '-report_el_torito', 'plain'],
        capture_output=True, text=True,
    )
    lba = size_sectors = None
    for line in (result.stdout + '\n' + result.stderr).splitlines():
        if 'boot img' not in line.lower():
            continue
        fields = line.split(':', 1)[-1].split()
        # fields: [N, Pltf, B, Emul, Ld_seg, Hdpt, Ldsiz, LBA]
        if len(fields) >= 8 and fields[1].upper() == 'UEFI':
            size_sectors, lba = int(fields[6]), int(fields[7])
            break
    if lba is None or not size_sectors:
        raise ISOExtractionError(
            str(iso_path),
            'No UEFI El Torito boot image found in Windows ISO — cannot build bootable override.',
        )
    # LBA is in 2048-byte ISO sectors; load size is in 512-byte virtual sectors.
    with open(iso_path, 'rb') as f:
        f.seek(lba * 2048)
        data = f.read(size_sectors * 512)
    if len(data) != size_sectors * 512:
        raise ISOExtractionError(str(iso_path), 'Short read extracting El Torito boot image.')
    output_path.write_bytes(data)


def _build_bootable_iso(
    source_dir: Path,
    output_path: Path,
    *,
    volume_label: str,
    efi_boot_img: str,
) -> None:
    """Build a UEFI El-Torito-bootable ISO from source_dir using xorriso.

    xorriso is cross-platform (macOS/Linux/Windows); the only host-specific part
    is installation, hinted by check_prerequisites. ``efi_boot_img`` is a path
    (relative to source_dir) to the no-emulation UEFI El Torito boot image.
    """
    import shutil
    import subprocess

    if not shutil.which('xorriso'):
        raise ISOExtractionError(
            str(output_path),
            'xorriso not found — required to build the bootable legacy-boot ISO. '
            'Install with: brew install xorriso (macOS) / apt install xorriso (Linux).',
        )
    subprocess.run(
        ['xorriso', '-as', 'mkisofs', '-iso-level', '3', '-R', '-J', '-joliet-long',
         '-V', volume_label, '-e', efi_boot_img, '-no-emul-boot',
         '-o', str(output_path), str(source_dir)],
        check=True, capture_output=True,
    )


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


def iso_sha256(iso_path: Path) -> str:
    """Return the SHA256 hex digest of an ISO file.

    Exists so a mismatch error can name the *actual* digest alongside the
    declared one without hashing a multi-gigabyte file a second time in the
    caller. :func:`verify_iso_hash` only answers yes/no.
    """
    digest = hashlib.sha256()
    with open(iso_path, 'rb') as f:
        while True:
            chunk = f.read(8192)
            if not chunk:
                break
            digest.update(chunk)
    return digest.hexdigest()


def verify_iso_hash(iso_path: Path, expected_sha256: str) -> bool:
    """Verify the SHA256 hash of an ISO file.

    Note the comparison is case-SENSITIVE, which is why every caller normalizes
    the declared digest through
    :func:`adare.services.recipe_contract.normalized_iso_sha256` first: an
    uppercase digest that slipped past a case-insensitive gate would otherwise
    describe an environment that can never build.

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
