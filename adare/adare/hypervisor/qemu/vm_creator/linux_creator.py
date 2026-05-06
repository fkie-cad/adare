"""Linux VM creation orchestrator - Ubuntu autoinstall via QEMU direct kernel boot."""

import logging
import platform
import subprocess
import tempfile
from pathlib import Path

from adare.config.configdirectory import QEMU_CACHE_DIR
from adare.console import console, print_section, print_step
from adare.helperfunctions.web.download import download
from adare.hypervisor.qemu.firmware import find_ovmf_firmware
from adare.hypervisor.qemu.vm_creator.autoinstall import write_autoinstall_dir
from adare.hypervisor.qemu.vm_creator.base_creator import BaseVMCreator, VMCreationError
from adare.hypervisor.qemu.vm_creator.iso_utils import (
    ISOExtractionError,
    create_cidata_iso,
    extract_kernel_and_initrd,
    verify_iso_hash,
)
from adare.hypervisor.qemu.vm_creator.os_catalog import OsDefinition, SetupLevel
from adare.hypervisor.qemu.vm_creator.progress import wait_for_qemu_exit
from adare.hypervisor.qemu.vm_creator.qmp_utils import qemu_params_for_arch

log = logging.getLogger(__name__)


class LinuxVMCreationError(VMCreationError):
    """Raised when Linux VM creation fails."""

    def __init__(self, detail: str):
        super().__init__(f"Linux: {detail}")


class LinuxVMCreator(BaseVMCreator):
    """Create a fully configured Linux VM from an Ubuntu Server ISO.

    Orchestrates the full creation flow:
    1. Check prerequisites
    2. Download ISO (with caching)
    3. Extract kernel/initrd from ISO
    4. Generate autoinstall config + cidata ISO
    5. Create disk image
    6. Boot QEMU with direct kernel + cidata ISO
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

            cidata_path = create_cidata_iso(
                autoinstall_dir, tmpdir_path / 'cidata.iso',
            )
            print_step(f'Created cidata ISO for autoinstall: [dim]{cidata_path}[/dim]')

            try:
                _run_qemu_installation(
                    iso_path=self.iso_path,
                    kernel_path=kernel_path,
                    initrd_path=initrd_path,
                    cidata_path=cidata_path,
                    disk_path=disk_path,
                    os_def=self.os_def,
                    ram_mb=self.ram_mb,
                    cpus=self.cpus,
                    nvram_path=nvram_path,
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
) -> Path:
    """Create a fully configured Linux VM from an Ubuntu Server ISO.

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
    cidata_path: Path,
    disk_path: Path,
    os_def: OsDefinition,
    ram_mb: int,
    cpus: int,
    nvram_path: Path | None = None,
) -> None:
    """Boot QEMU with direct kernel boot + cidata ISO autoinstall.

    cloud-init auto-detects the attached drive labelled `cidata` as a NoCloud
    datasource regardless of architecture, so the same flow works for x86_64
    and aarch64. The `autoinstall` kernel parameter tells Subiquity to skip
    the confirmation prompt and run unattended.
    """
    arch_params = qemu_params_for_arch(os_def)
    needs_uefi = os_def.requires_uefi or os_def.architecture == 'aarch64'
    console_dev = 'ttyAMA0' if os_def.architecture == 'aarch64' else 'ttyS0'

    kernel_cmdline = f'autoinstall console={console_dev} ---'

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
        # Direct kernel boot — passes 'autoinstall' to Subiquity
        '-kernel', str(kernel_path),
        '-initrd', str(initrd_path),
        '-append', kernel_cmdline,
        # cidata ISO — cloud-init NoCloud datasource (auto-detected by label)
        '-drive', f'file={cidata_path},format=raw,if=virtio,readonly=on',
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
        '-serial', f'file:{disk_path.parent / (disk_path.stem + "_install.log")}',
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
    print_section('Installation')
    print_step('Starting unattended installation [dim](this may take 15-45 minutes)[/dim]')

    process = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )

    try:
        with console.status(f'  [cyan]{disk_path.stem}[/cyan] installing...', spinner='dots') as status:
            wait_for_qemu_exit(
                process,
                timeout_minutes=60,
                label=f'{disk_path.stem} installation',
                status=status,
            )
    except (TimeoutError, subprocess.CalledProcessError):
        raise
    except KeyboardInterrupt:
        console.print('\n  [bold red]Installation interrupted by user[/bold red]')
        process.terminate()
        process.wait(timeout=30)
        raise LinuxVMCreationError('Installation interrupted by user') from None
