"""Abstract base class for VM creation flows using the Template Method pattern.

Each concrete creator (Linux, Windows, Manual) implements the OS-specific steps
while inheriting the shared orchestration, disk setup, cleanup, and UI logic.
"""

from abc import ABC, abstractmethod
from datetime import datetime
from pathlib import Path

from adare.config.configdirectory import VMS_DIR
from adare.console import console, print_section, print_step, print_vm_config_panel
from adare.hypervisor.exceptions import HypervisorException
from adare.hypervisor.qemu.firmware import create_nvram_for_vm
from adare.hypervisor.qemu.vm_creator.disk_helpers import create_qcow2_disk
from adare.hypervisor.qemu.vm_creator.os_catalog import OsDefinition, SetupLevel, default_host_cpus
from adare.hypervisor.qemu.vm_creator.prerequisites import check_prerequisites

import logging
log = logging.getLogger(__name__)


class VMCreationError(HypervisorException):
    """Base exception for VM creation failures."""

    def __init__(self, detail: str):
        message = f"VM creation failed: {detail}"
        super().__init__(message)


class BaseVMCreator(ABC):
    """Abstract base for VM creation flows using Template Method pattern.

    Subclasses must implement:
        _ensure_iso()         -- acquire or validate the installer ISO
        _run_installation()   -- execute the OS-specific installation inside QEMU

    The ``create()`` method orchestrates the full flow in a fixed sequence:
        1. Print configuration panel
        2. Check prerequisites
        3. Ensure ISO availability
        4. Create disk image (and optional NVRAM)
        5. Run installation
        6. Print success / clean up on failure
    """

    def __init__(
        self,
        os_def: OsDefinition,
        vm_name: str | None = None,
        disk_size: str | None = None,
        ram_mb: int | None = None,
        cpus: int | None = None,
        force: bool = False,
        vm_dir: Path | None = None,
        iso_path: Path | None = None,
        setup_level: SetupLevel = SetupLevel.FULL,
    ):
        self.os_def = os_def
        self.vm_name = vm_name or self._default_vm_name()
        self.disk_size = disk_size or os_def.default_disk_size
        self.ram_mb = ram_mb or os_def.default_ram_mb
        self.cpus = cpus or os_def.default_cpus or default_host_cpus()
        self.force = force
        self.vm_dir = vm_dir
        self.iso_path = iso_path
        self.setup_level = setup_level

    # ── Template method ──────────────────────────────────────────────

    def create(self) -> Path:
        """Template method -- orchestrates the creation flow.

        Returns:
            Path to the created qcow2 disk image.
        """
        self._print_config_panel()
        self._check_prerequisites()
        self._ensure_iso()
        disk_path, nvram_path = self._create_disk()
        try:
            self._run_installation(disk_path, nvram_path)
        except (KeyboardInterrupt, HypervisorException):
            self._cleanup_on_failure(disk_path, nvram_path)
            raise
        self._validate_disk_after_install(disk_path)
        self._print_success(disk_path)
        return disk_path

    # ── Abstract hooks ───────────────────────────────────────────────

    @abstractmethod
    def _ensure_iso(self) -> None:
        """Acquire or validate the installer ISO.

        Linux creators download and cache; Windows validates the user-supplied
        path and downloads virtio-win; Manual just validates the path.
        Implementations should set ``self.iso_path`` as needed.
        """

    @abstractmethod
    def _run_installation(self, disk_path: Path, nvram_path: Path | None) -> None:
        """Execute the OS-specific installation inside QEMU.

        Args:
            disk_path:  Path to the qcow2 disk image.
            nvram_path: Path to the NVRAM file (None when UEFI is not required).
        """

    # ── Shared helpers ───────────────────────────────────────────────

    def _default_vm_name(self) -> str:
        """Generate a default VM name from the OS definition and current date."""
        date_str = datetime.now().strftime('%Y%m%d')
        return f'{self.os_def.name}-{date_str}'

    def _default_cpus(self) -> int:
        """Return a reasonable CPU count for a VM based on the host."""
        return self.os_def.default_cpus or default_host_cpus()

    def _print_config_panel(self) -> None:
        """Print a Rich panel summarising the VM configuration."""
        print_vm_config_panel(f'VM Creation: {self.vm_name}', [
            ('OS', self.os_def.display_name),
            ('Architecture', self.os_def.architecture),
            ('Disk', self.disk_size),
            ('RAM', f'{self.ram_mb} MB'),
            ('CPUs', str(self.cpus)),
        ])

    def _check_prerequisites(self) -> None:
        """Verify that the host has all required tools and resources."""
        check_prerequisites(self.os_def, iso_path=self.iso_path)

    def _create_disk(self) -> tuple[Path, Path | None]:
        """Create the qcow2 disk image and optional NVRAM file.

        Returns:
            (disk_path, nvram_path) -- nvram_path is None when UEFI is not required.

        Raises:
            VMCreationError: If the disk already exists and ``force`` is False.
        """
        print_section('Disk Setup')
        target_dir = self.vm_dir or VMS_DIR
        disk_path = target_dir / f'{self.vm_name}.qcow2'
        disk_path.parent.mkdir(parents=True, exist_ok=True)

        if disk_path.exists():
            if self.force:
                print_step(f'[yellow]Removing existing disk image[/yellow]: [dim]{disk_path}[/dim]')
                disk_path.unlink()
                nvram_file = target_dir / f'{self.vm_name}-nvram.fd'
                if nvram_file.exists():
                    nvram_file.unlink()
            else:
                raise VMCreationError(
                    f'Disk image already exists: {disk_path}. '
                    f'Use --force to overwrite or --name to use a different name.'
                )

        create_qcow2_disk(disk_path, self.disk_size)

        # Create NVRAM if UEFI required (aarch64 always needs UEFI -- no BIOS)
        needs_uefi = self.os_def.requires_uefi or self.os_def.architecture == 'aarch64'
        nvram_path = None
        if needs_uefi:
            nvram_path = Path(create_nvram_for_vm(
                self.vm_name, target_dir, self.os_def.architecture,
            ))

        return disk_path, nvram_path

    def _validate_disk_after_install(self, disk_path: Path) -> None:
        """Verify the disk image exists and was written to after installation.

        Catches cases where the disk file was deleted externally during the
        QEMU process (Unix open-fd semantics allow the process to continue
        but the file is gone after exit).
        """
        if not disk_path.exists():
            raise VMCreationError(
                f'Disk image vanished during installation: {disk_path}\n'
                f'The file was deleted by an external process while QEMU was running.'
            )
        size = disk_path.stat().st_size
        if size < 1_000_000:  # < 1MB means QEMU never wrote to it
            raise VMCreationError(
                f'Disk image appears empty after installation ({size} bytes): {disk_path}\n'
                f'QEMU may have failed to start or the installation did not complete.'
            )

    def _cleanup_on_failure(self, disk_path: Path, nvram_path: Path | None) -> None:
        """Remove disk and NVRAM files after a failed installation."""
        if disk_path.exists():
            disk_path.unlink()
        if nvram_path is not None and nvram_path.exists():
            nvram_path.unlink()

    def _print_success(self, disk_path: Path) -> None:
        """Print a success message with the path to the created disk image."""
        console.print(f'\n[bold green]VM disk image created:[/bold green] {disk_path}')
