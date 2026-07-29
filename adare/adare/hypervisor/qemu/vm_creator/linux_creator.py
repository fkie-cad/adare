"""Linux VM creation orchestrator — unattended installs via QEMU direct kernel boot.

Supports any installer family declared in ``OsDefinition.installer`` (Subiquity,
preseed, kickstart, AutoYaST, archinstall-over-cloud-init). The seed medium and
kernel command line are chosen per OS, so a single orchestrator drives all of
them.
"""

import logging
import os
import platform
import subprocess
import tempfile
from pathlib import Path

from adare.config.configdirectory import QEMU_CACHE_DIR
from adare.console import console, print_section, print_step
from adare.helperfunctions.web.download import download
from adare.hypervisor.qemu.firmware import find_ovmf_firmware
from adare.hypervisor.qemu.vm_creator.autoinstall import seed_filename, write_autoinstall_dir
from adare.hypervisor.qemu.vm_creator.base_creator import BaseVMCreator, VMCreationError
from adare.hypervisor.qemu.vm_creator.iso_utils import (
    ISOExtractionError,
    create_seed_iso,
    extract_kernel_and_initrd,
    verify_iso_hash,
)
from adare.hypervisor.qemu.vm_creator.os_catalog import OsDefinition, SetupLevel
from adare.hypervisor.qemu.vm_creator.progress import (
    QemuInstallTerminated,
    terminate_qemu_on_exit,
    wait_for_qemu_exit,
)
from adare.hypervisor.qemu.vm_creator.qmp_utils import qemu_params_for_arch
from adare.hypervisor.qemu.vm_creator.seed_http import SeedHTTPServer

log = logging.getLogger(__name__)

# Wall-clock ceiling for one unattended install. It is a hang detector, not a
# budget: a healthy install that merely runs long must not be killed. 60 minutes
# was too low — a Fedora Workstation netinst pulls ~1900 RPMs and spends ~50 min
# on download plus scriptlets before it ever reaches %post, and a Kubuntu build
# fetches the whole `kubuntu-desktop` set from the archive. Override per run with
# ADARE_VM_INSTALL_TIMEOUT_MINUTES.
_DEFAULT_INSTALL_TIMEOUT_MINUTES = 150


def _install_timeout_minutes() -> int:
    """Install timeout in minutes, overridable via ``ADARE_VM_INSTALL_TIMEOUT_MINUTES``."""
    raw = os.environ.get('ADARE_VM_INSTALL_TIMEOUT_MINUTES', '').strip()
    if not raw:
        return _DEFAULT_INSTALL_TIMEOUT_MINUTES
    try:
        minutes = int(raw)
        if minutes <= 0:
            raise ValueError('must be a positive number of minutes')
    except ValueError as e:
        log.warning(
            'Ignoring ADARE_VM_INSTALL_TIMEOUT_MINUTES=%r (%s); using %d',
            raw, e, _DEFAULT_INSTALL_TIMEOUT_MINUTES,
        )
        return _DEFAULT_INSTALL_TIMEOUT_MINUTES
    return minutes


# Installer-specific "this install did not finish" markers, matched against the
# serial console log after QEMU exits.
#
# QEMU exits 0 whenever the guest powers down — on SIGTERM, on a closed QEMU
# window, and on an installer that gives up and powers off. A zero exit is
# therefore NOT evidence that the install completed: without this check a
# half-installed disk gets hashed and registered as a usable environment, which
# for a forensic baseline is worse than a loud failure. Keep the patterns narrow
# and installer-specific — UEFI/kernel logs are full of unrelated "Error:" lines.
_INSTALL_FAILURE_MARKERS = (
    # subiquity: drops to a rescue shell and waits forever
    'An error occurred. Press enter to start a shell',
    'install_fail',
    # curtin: in-target apt/dpkg step failed (exit 100 == apt error)
    "returned non-zero exit status 100",
    # Anaconda
    'The following error occurred while installing',
    'Kickstart error',
    # debian-installer
    'The installation step failed',
)


class LinuxVMCreationError(VMCreationError):
    """Raised when Linux VM creation fails."""

    def __init__(self, detail: str):
        super().__init__(f"Linux: {detail}")


def _assert_install_succeeded(install_log: Path) -> None:
    """Raise if the installer's serial log shows the install did not complete.

    Complements the QEMU exit code, which cannot distinguish "installer finished
    and rebooted" from "guest powered off mid-install" (both are exit 0).
    """
    try:
        text = install_log.read_text(encoding='utf-8', errors='replace')
    except OSError as e:
        log.warning('Could not read install log %s: %s', install_log, e)
        return

    for marker in _INSTALL_FAILURE_MARKERS:
        if marker in text:
            raise LinuxVMCreationError(
                f'installer reported failure ({marker!r}) — see {install_log}. '
                f'The disk is incomplete and has not been kept.'
            )


class LinuxVMCreator(BaseVMCreator):
    """Create a fully configured Linux VM from an installation ISO.

    Orchestrates the full creation flow:
    1. Check prerequisites
    2. Download ISO (with caching)
    3. Extract kernel/initrd from ISO
    4. Generate autoinstall config + seed ISO
    5. Create disk image
    6. Boot QEMU with direct kernel + seed ISO
    7. Wait for installation to complete (VM self-shutdown)
    8. Return path to the finished qcow2 disk image
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    def _ensure_iso(self) -> None:
        """Download or locate the cached ISO, verify its hash."""
        print_section('ISO & Prerequisites')
        if self.iso_path is not None:
            if not self.iso_path.is_file():
                raise LinuxVMCreationError(f'ISO file not found: {self.iso_path}')
        elif self.os_def.iso_url:
            self.iso_path = _download_and_cache_iso(self.os_def)
        else:
            raise LinuxVMCreationError(
                f'No ISO URL for {self.os_def.display_name}. '
                f'Use: adare vm create {self.os_def.name} --iso /path/to/iso'
            )

    def _run_installation(self, disk_path: Path, nvram_path: Path | None) -> None:
        """Extract kernel, generate autoinstall, boot QEMU, and wait for install."""
        with tempfile.TemporaryDirectory(prefix='adare-vmcreate-') as tmpdir:
            tmpdir_path = Path(tmpdir)

            autoinstall_dir = write_autoinstall_dir(
                os_def=self.os_def,
                vm_name=self.vm_name,
                output_dir=tmpdir_path / 'autoinstall',
                setup_level=self.setup_level,
            )

            try:
                kernel_path, initrd_path = extract_kernel_and_initrd(
                    iso_path=self.iso_path,
                    kernel_iso_path=self.os_def.kernel_path_in_iso,
                    initrd_iso_path=self.os_def.initrd_path_in_iso,
                    output_dir=tmpdir_path / 'boot',
                )
            except ISOExtractionError:
                raise
            except (OSError, ValueError) as e:
                raise LinuxVMCreationError(f'Kernel extraction failed: {e}') from e

            # The seed CD-ROM is attached unconditionally, including when
            # ``seed_transport == 'http'``. It looks redundant there — ubiquity and
            # 18.04's d-i fetch the answer file from ``url=`` and never read the
            # label — but this is the configuration the 18.04 install was actually
            # validated against, so it stays. If you are ever chasing a partman
            # complaint about an ambiguous target, note that the extra drive is a
            # second block device the recipe can see: pin ``partman-auto/disk`` to
            # ``/dev/vda`` in the preseed rather than detaching the seed here.
            seed_path = create_seed_iso(
                autoinstall_dir,
                tmpdir_path / 'seed.iso',
                label=self.os_def.seed_label,
            )
            print_step(
                f'Created seed ISO ([dim]{self.os_def.seed_label}[/dim]) for '
                f'autoinstall: [dim]{seed_path}[/dim]'
            )

            try:
                _run_qemu_installation(
                    iso_path=self.iso_path,
                    kernel_path=kernel_path,
                    initrd_path=initrd_path,
                    seed_path=seed_path,
                    seed_dir=autoinstall_dir,
                    disk_path=disk_path,
                    os_def=self.os_def,
                    ram_mb=self.ram_mb,
                    cpus=self.cpus,
                    nvram_path=nvram_path,
                    allow_emulation=self.allow_emulation,
                )
            except (TimeoutError, subprocess.CalledProcessError) as e:
                raise LinuxVMCreationError(str(e)) from e


def create_linux_vm(
    os_def: OsDefinition,
    vm_name: str | None = None,
    disk_size: str | None = None,
    ram_mb: int | None = None,
    cpus: int | None = None,
    iso_path: Path | None = None,
    force: bool = False,
    vm_dir: Path | None = None,
    setup_level: SetupLevel = SetupLevel.FULL,
    compress: bool = True,
    allow_emulation: bool = False,
) -> Path:
    """Create a fully configured Linux VM from an installation ISO.

    Convenience wrapper around ``LinuxVMCreator`` for backward compatibility.
    """
    creator = LinuxVMCreator(
        os_def=os_def,
        vm_name=vm_name,
        disk_size=disk_size,
        ram_mb=ram_mb,
        cpus=cpus,
        force=force,
        vm_dir=vm_dir,
        iso_path=iso_path,
        setup_level=setup_level,
        compress=compress,
        allow_emulation=allow_emulation,
    )
    return creator.create()


def _download_and_cache_iso(os_def: OsDefinition) -> Path:
    """Download the ISO if not already cached, verify its hash."""
    QEMU_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    iso_path = QEMU_CACHE_DIR / os_def.iso_filename

    if iso_path.exists():
        print_step(f'Using cached ISO: [dim]{iso_path}[/dim]')
        if os_def.iso_sha256 and not verify_iso_hash(iso_path, os_def.iso_sha256):
            print_step('[yellow]Cached ISO hash mismatch, re-downloading...[/yellow]')
            iso_path.unlink()
        else:
            return iso_path

    print_step(f'Downloading {os_def.display_name} ISO...')
    download(os_def.iso_url, iso_path)

    if os_def.iso_sha256 and not verify_iso_hash(iso_path, os_def.iso_sha256):
        iso_path.unlink()
        raise LinuxVMCreationError(
            f'Downloaded ISO failed SHA256 verification. '
            f'Expected: {os_def.iso_sha256}'
        )

    return iso_path


def _run_qemu_installation(
    iso_path: Path,
    kernel_path: Path,
    initrd_path: Path,
    seed_path: Path,
    disk_path: Path,
    os_def: OsDefinition,
    ram_mb: int,
    cpus: int,
    nvram_path: Path | None = None,
    seed_dir: Path | None = None,
    allow_emulation: bool = False,
) -> None:
    """Boot QEMU with direct kernel boot + seed medium for unattended install.

    The seed medium carries the rendered installer config (cloud-init NoCloud,
    preseed, kickstart, AutoYaST, ...). Each installer family announces
    itself through ``os_def.kernel_cmdline`` and ``os_def.seed_label``; the
    label drives auto-detection (``cidata`` for cloud-init, ``OEMDRV`` for
    debian-installer / Anaconda) while the cmdline carries any extra hints
    (``inst.ks=``, ``autoyast=``, ``auto=true preseed/file=...``).

    Installers that cannot auto-load their answer file from a labelled drive
    (Ubuntu 18.04's debian-installer, ubiquity on the desktop ISOs) declare
    ``seed_transport: http``: ``seed_dir`` is then also served over HTTP on an
    ephemeral host port for the duration of the install and a ``url=`` fetch hint
    is spliced into the kernel command line.
    """
    arch_params = qemu_params_for_arch(os_def, allow_emulation)
    needs_uefi = os_def.requires_uefi or os_def.architecture == 'aarch64'
    console_dev = 'ttyAMA0' if os_def.architecture == 'aarch64' else 'ttyS0'

    install_log = disk_path.parent / (disk_path.stem + '_install.log')

    seed_server: SeedHTTPServer | None = None
    if os_def.seed_transport == 'http':
        if seed_dir is None:
            raise LinuxVMCreationError(
                f'{os_def.name} declares seed_transport: http but no seed directory '
                f'was rendered'
            )
        seed_server = SeedHTTPServer(seed_dir).start()

    try:
        kernel_cmdline = os_def.kernel_cmdline.format(console=console_dev)

        if seed_server is not None:
            # QEMU user-mode networking always maps the host to 10.0.2.2.
            seed_url = f'http://10.0.2.2:{seed_server.port}/{seed_filename(os_def)}'
            # `---` separates installer args from args handed to the installed
            # kernel, so the fetch hint has to land before it.
            if '---' in kernel_cmdline:
                kernel_cmdline = kernel_cmdline.replace('---', f'url={seed_url} ---', 1)
            else:
                kernel_cmdline = f'{kernel_cmdline} url={seed_url}'
            print_step(f'Serving the seed over HTTP for the installer: [dim]{seed_url}[/dim]')

        cmd = [
            arch_params['exe'],
            '-machine', arch_params['machine'],
            '-cpu', arch_params['cpu'],
            '-m', str(ram_mb),
            '-smp', str(cpus),
            # Disk
            '-drive', f'file={disk_path},format=qcow2,if=virtio,cache=writeback',
            # Ubuntu ISO as CD-ROM
            '-cdrom', str(iso_path),
            # Direct kernel boot — passes installer-specific cmdline to the guest
            '-kernel', str(kernel_path),
            '-initrd', str(initrd_path),
            '-append', kernel_cmdline,
            # Network (user mode)
            '-netdev', 'user,id=net0',
            '-device', 'virtio-net-pci,netdev=net0',
            # Display — show QEMU window so user can watch install progress
            '-display', 'cocoa' if platform.system() == 'Darwin' else 'gtk',
            # USB devices for input in display window
            '-device', 'qemu-xhci',
            '-device', 'usb-tablet',
            '-device', 'usb-kbd',
            # Virtio RNG for faster entropy
            '-device', 'virtio-rng-pci',
            # Serial console for installer log output
            '-serial', f'file:{install_log}',
            # Seed ISO — auto-detected by volume label (cidata / OEMDRV / ...)
            '-drive', f'file={seed_path},format=raw,if=virtio,readonly=on',
            # Exit QEMU on guest reboot (Subiquity reboots after install)
            '-no-reboot',
        ]
        cmd.extend(arch_params['vga_args'])

        if needs_uefi and nvram_path is not None:
            ovmf_code, _ = find_ovmf_firmware(os_def.architecture)
            pflash_args = [
                '-drive', f'if=pflash,format=raw,readonly=on,file={ovmf_code}',
                '-drive', f'if=pflash,format=raw,file={nvram_path}',
            ]
            machine_idx = cmd.index('-machine') + 2
            cmd[machine_idx:machine_idx] = pflash_args

        log.info(f'Starting QEMU installation: {" ".join(cmd)}')
        timeout_minutes = _install_timeout_minutes()
        print_section('Installation')
        print_step(
            'Starting unattended installation [dim](15-45 min for a server ISO; a '
            'Fedora Workstation netinst or a kubuntu-desktop build runs longer — '
            f'giving up after {timeout_minutes} min)[/dim]'
        )

        process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )

        label = f'{disk_path.stem} installation'
        try:
            # The context manager reaps QEMU on every exit path, signals
            # included — a bare `kill` of this process used to leave the
            # installer VM running as an orphan.
            with terminate_qemu_on_exit(process, label=label):
                with console.status(f'  [cyan]{disk_path.stem}[/cyan] installing...', spinner='dots') as status:
                    wait_for_qemu_exit(
                        process,
                        timeout_minutes=timeout_minutes,
                        label=label,
                        status=status,
                    )
                # A zero exit only means the guest powered down; confirm the
                # installer actually got to the end before the disk is trusted.
                _assert_install_succeeded(install_log)
        except (TimeoutError, subprocess.CalledProcessError):
            raise
        except KeyboardInterrupt:
            console.print('\n  [bold red]Installation interrupted by user[/bold red]')
            raise LinuxVMCreationError('Installation interrupted by user') from None
        except QemuInstallTerminated as e:
            console.print(f'\n  [bold red]Installation terminated:[/bold red] {e}')
            raise LinuxVMCreationError(f'Installation terminated: {e}') from None
    finally:
        if seed_server is not None:
            seed_server.stop()
