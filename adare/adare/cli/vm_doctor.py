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


def _record(checks: list[dict], label: str, found: bool, path: str | None = None,
            hint: str | None = None, required: bool = True) -> None:
    """Record one tool check (rendered later as text, or emitted as data)."""
    checks.append({'name': label, 'found': found, 'required': required,
                   'path': path, 'hint': None if found else hint})


def _check_binary(name: str, label: str, hint: str, checks: list[dict]) -> None:
    path = shutil.which(name)
    _record(checks, label, bool(path), path, hint)


def _print_checks(checks: list[dict]) -> None:
    for check in checks:
        label = check['name']
        if check['found']:
            location = f": {check['path']}" if check['path'] else ''
            console.print(f'[green]✓ {label} found[/green]{location}')
        elif check['required']:
            console.print(f"[red]✗ {label} not found[/red]. {check['hint']}")
        else:
            console.print(f"[yellow]! {label} not found[/yellow] ({check['hint']})")


def exec_vm_doctor(arguments):
    """Report on system-level QEMU/VM-creation tool availability."""
    checks: list[dict] = []

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
        checks,
    )
    _check_binary(
        'qemu-img', 'qemu-img',
        _install_hint('Install with: brew install qemu', 'Usually included with QEMU.'),
        checks,
    )

    try:
        from adare.hypervisor.qemu.firmware import find_ovmf_firmware
        code_path, _vars_path = find_ovmf_firmware(qemu_arch)
        _record(checks, 'OVMF firmware', True, str(code_path))
    except HypervisorException:
        hint = _install_hint(
            'Install with: brew install qemu (includes OVMF)',
            'Install with: sudo apt install ovmf (Debian/Ubuntu) or sudo dnf install edk2-ovmf (Fedora)',
        )
        _record(checks, 'OVMF firmware', False, hint=hint)

    # swtpm — informational only, TPM model already adapts per-arch at VM-create time.
    swtpm_path = shutil.which('swtpm')
    _record(checks, 'swtpm', bool(swtpm_path), swtpm_path,
            'optional — Windows TPM requirement will be bypassed via registry hack if absent',
            required=False)

    try:
        import libvirt  # noqa: F401
        _record(checks, 'libvirt Python binding', True)
    except ImportError:
        hint = _install_hint(
            'Install with: brew install libvirt',
            'Install with: sudo apt install libvirt-dev (Debian/Ubuntu) or sudo dnf install libvirt-devel (Fedora)',
        )
        _record(checks, 'libvirt Python binding', False,
                hint=f'{hint}, then reinstall with: uv sync --extra qemu')

    # aarch64-only: Win11-ARM64 legacy-boot ISO toolchain (see iso_utils.create_legacy_boot_iso).
    if is_arm_host:
        _check_binary(
            'wimlib-imagex', 'wimlib-imagex',
            _install_hint(
                'Install with: brew install wimlib',
                'Install with: sudo apt install wimtools (Debian/Ubuntu) or sudo dnf install wimlib-utils (Fedora)',
            ),
            checks,
        )
        path = shutil.which('7z') or shutil.which('7zz') or shutil.which('7za')
        _record(checks, '7z', bool(path), path, _install_hint(
            'Install with: brew install p7zip',
            'Install with: sudo apt install p7zip-full (Debian/Ubuntu) or sudo dnf install p7zip (Fedora)',
        ))
        _check_binary(
            'xorriso', 'xorriso',
            _install_hint(
                'Install with: brew install xorriso',
                'Install with: sudo apt install xorriso (Debian/Ubuntu) or sudo dnf install xorriso (Fedora)',
            ),
            checks,
        )

    missing = [f"{c['name']}: {c['hint']}" for c in checks if c['required'] and not c['found']]

    from adare.cli.output import emit, is_structured_output
    if is_structured_output():
        # Still exit 0 when tools are missing: this runs unattended in `make install`.
        emit({'ok': not missing, 'host_arch': host_arch, 'checks': checks})
        return

    _print_checks(checks)
    if missing:
        print_error_message(
            title='Some QEMU/system tools are missing (adare vm create may fail until installed)',
            next_steps=missing,
        )
    else:
        print_success_message(title='All QEMU/system tools found')
