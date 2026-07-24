"""CLI handler for `adare vm doctor` — system-tool preflight for QEMU VM creation.

Locates the system-level (non-pip) tools that `adare vm create` needs and
reports what's found vs missing. Detect-and-report only — never
apt/brew-installs anything, and never exits non-zero, since this is meant to
run unattended at the end of `make install`.
"""

from __future__ import annotations

import platform
import shutil

from adare.console import console, print_error_message, print_success_message
from adare.hypervisor.exceptions import HypervisorException


def _install_hint(darwin: str, linux: str) -> str:
    return darwin if platform.system() == 'Darwin' else linux


def _check_binary(name: str, label: str, hint: str, missing: list[str]) -> None:
    path = shutil.which(name)
    if path:
        console.print(f'[green]✓ {label} found[/green]: {path}')
    else:
        console.print(f'[red]✗ {label} not found[/red]. {hint}')
        missing.append(f'{label}: {hint}')


def exec_vm_doctor(arguments):
    """Report on system-level QEMU/VM-creation tool availability."""
    missing: list[str] = []

    host_arch = platform.machine().lower()
    qemu_arch = 'aarch64' if host_arch in ('arm64', 'aarch64') else host_arch
    is_arm_host = host_arch in ('arm64', 'aarch64')

    _check_binary(
        f'qemu-system-{qemu_arch}', f'qemu-system-{qemu_arch}',
        _install_hint(
            'Install with: brew install qemu',
            'Install with: sudo apt install qemu-system-x86 (Debian/Ubuntu) or '
            'sudo dnf install qemu-system-x86-core (Fedora)',
        ),
        missing,
    )
    _check_binary(
        'qemu-img', 'qemu-img',
        _install_hint('Install with: brew install qemu', 'Usually included with QEMU.'),
        missing,
    )

    try:
        from adare.hypervisor.qemu.firmware import find_ovmf_firmware
        code_path, _vars_path = find_ovmf_firmware(qemu_arch)
        console.print(f'[green]✓ OVMF firmware found[/green]: {code_path}')
    except HypervisorException:
        hint = _install_hint(
            'Install with: brew install qemu (includes OVMF)',
            'Install with: sudo apt install ovmf (Debian/Ubuntu) or sudo dnf install edk2-ovmf (Fedora)',
        )
        console.print(f'[red]✗ OVMF firmware not found[/red]. {hint}')
        missing.append(f'OVMF firmware: {hint}')

    # swtpm — informational only, TPM model already adapts per-arch at VM-create time.
    swtpm_path = shutil.which('swtpm')
    if swtpm_path:
        console.print(f'[green]✓ swtpm found[/green]: {swtpm_path}')
    else:
        console.print('[yellow]! swtpm not found[/yellow] (optional — Windows TPM requirement '
                      'will be bypassed via registry hack if absent)')

    try:
        import libvirt  # noqa: F401
        console.print('[green]✓ libvirt Python binding importable[/green]')
    except ImportError:
        hint = _install_hint(
            'Install with: brew install libvirt',
            'Install with: sudo apt install libvirt-dev (Debian/Ubuntu) or sudo dnf install libvirt-devel (Fedora)',
        )
        console.print(f'[red]✗ libvirt Python binding not importable[/red]. {hint} '
                      f'then reinstall with: uv sync --extra qemu')
        missing.append(f'libvirt Python binding: {hint}, then `uv sync --extra qemu`')

    # aarch64-only: Win11-ARM64 legacy-boot ISO toolchain (see iso_utils.create_legacy_boot_iso).
    if is_arm_host:
        _check_binary(
            'wimlib-imagex', 'wimlib-imagex',
            _install_hint(
                'Install with: brew install wimlib',
                'Install with: sudo apt install wimtools (Debian/Ubuntu) or sudo dnf install wimlib-utils (Fedora)',
            ),
            missing,
        )
        if shutil.which('7z') or shutil.which('7zz') or shutil.which('7za'):
            path = shutil.which('7z') or shutil.which('7zz') or shutil.which('7za')
            console.print(f'[green]✓ 7z found[/green]: {path}')
        else:
            hint = _install_hint(
                'Install with: brew install p7zip',
                'Install with: sudo apt install p7zip-full (Debian/Ubuntu) or sudo dnf install p7zip (Fedora)',
            )
            console.print(f'[red]✗ 7z (or 7zz/7za) not found[/red]. {hint}')
            missing.append(f'7z: {hint}')
        _check_binary(
            'xorriso', 'xorriso',
            _install_hint(
                'Install with: brew install xorriso',
                'Install with: sudo apt install xorriso (Debian/Ubuntu) or sudo dnf install xorriso (Fedora)',
            ),
            missing,
        )

    if missing:
        print_error_message(
            title='Some QEMU/system tools are missing (adare vm create may fail until installed)',
            next_steps=missing,
        )
    else:
        print_success_message(title='All QEMU/system tools found')
