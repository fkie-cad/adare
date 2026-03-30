"""CLI handlers for `adare manage os-profile` commands."""

import shutil
from pathlib import Path

import yaml

from adare.config.configdirectory import OS_PROFILES_DIR, VM_TEMPLATES_DIR
from adare.console import print_error_message, print_success_message
from adare.hypervisor.qemu.vm_creator.os_catalog import (
    OS_CATALOG,
    _BUILTIN_CATALOG,
    reload_catalog,
)

import logging
log = logging.getLogger(__name__)

_REQUIRED_FIELDS = {'name', 'platform', 'distribution', 'version'}


def exec_os_profile_list(arguments):
    """List all available OS profiles."""
    print(f'\n{"Name":<20} {"Display Name":<35} {"Platform":<10} {"Version":<10} {"Source"}')
    print('-' * 95)
    for name in sorted(OS_CATALOG):
        os_def = OS_CATALOG[name]
        source = 'built-in' if name in _BUILTIN_CATALOG else 'custom'
        print(f'{os_def.name:<20} {os_def.display_name:<35} {os_def.platform:<10} {os_def.version:<10} {source}')
    print()


def exec_os_profile_show(arguments):
    """Show detailed information about a specific OS profile."""
    name = arguments.name

    if name not in OS_CATALOG:
        print_error_message(
            title=f"Unknown OS profile: '{name}'",
            next_steps=[
                'Run: adare manage os-profile list',
                f'Available: {", ".join(sorted(OS_CATALOG.keys()))}',
            ],
        )
        return

    os_def = OS_CATALOG[name]
    source = 'built-in' if name in _BUILTIN_CATALOG else 'custom'

    # Resolve the template that would be used
    resolved_template = _resolve_template_path(os_def)

    fields = [
        ('Name', os_def.name),
        ('Display Name', os_def.display_name),
        ('Source', source),
        ('Platform', os_def.platform),
        ('Distribution', os_def.distribution),
        ('Distribution Label', os_def.distribution_label or '(none)'),
        ('Version', os_def.version),
        ('Architecture', os_def.architecture),
        ('Install Mode', os_def.install_mode),
        ('Requires UEFI', str(os_def.requires_uefi)),
        ('Requires TPM', str(os_def.requires_tpm)),
        ('ISO URL', os_def.iso_url or '(user must supply --iso)'),
        ('ISO SHA256', os_def.iso_sha256 or '(none)'),
        ('ISO Filename', os_def.iso_filename or '(none)'),
        ('Kernel Path in ISO', os_def.kernel_path_in_iso or '(none)'),
        ('Initrd Path in ISO', os_def.initrd_path_in_iso or '(none)'),
        ('Default Disk Size', os_def.default_disk_size),
        ('Default RAM (MB)', str(os_def.default_ram_mb)),
        ('Default CPUs', str(os_def.default_cpus) if os_def.default_cpus else 'auto'),
        ('Extra Packages', ', '.join(os_def.extra_packages) if os_def.extra_packages else '(none)'),
        ('Template (explicit)', os_def.template or '(default lookup)'),
        ('Resolved Template', resolved_template),
    ]

    max_label = max(len(label) for label, _ in fields)
    print()
    for label, value in fields:
        print(f'  {label:<{max_label}}  {value}')
    print()


def _resolve_template_path(os_def) -> str:
    """Resolve which template file would be used for this OS definition."""
    from adare.hypervisor.qemu.vm_creator.autoinstall import _TEMPLATE_MAP, TEMPLATES_DIR as LINUX_TEMPLATES_DIR
    from adare.hypervisor.qemu.vm_creator.windows_creator import _AUTOUNATTEND_MAP, TEMPLATES_DIR as WIN_TEMPLATES_DIR

    if os_def.install_mode == 'manual':
        return '(manual install -- no template)'

    # Check explicit template field
    if os_def.template:
        template_file = os_def.template
    elif os_def.platform == 'linux':
        template_file = _TEMPLATE_MAP.get(os_def.name)
        if template_file is None:
            distro_templates = {k: v for k, v in _TEMPLATE_MAP.items() if k.startswith(os_def.distribution)}
            template_file = distro_templates[max(distro_templates.keys())] if distro_templates else None
    elif os_def.platform == 'windows':
        template_file = _AUTOUNATTEND_MAP.get(os_def.name)
    else:
        return '(unknown platform)'

    if template_file is None:
        return '(no template found)'

    # Check user templates first, then built-in
    user_path = VM_TEMPLATES_DIR / template_file
    if user_path.is_file():
        return str(user_path)

    builtin_dir = WIN_TEMPLATES_DIR if os_def.platform == 'windows' else LINUX_TEMPLATES_DIR
    builtin_path = builtin_dir / template_file
    if builtin_path.is_file():
        return str(builtin_path)

    return f'{template_file} (not found on disk)'


def exec_os_profile_add(arguments):
    """Add a custom OS profile from a YAML file."""
    profile_path = Path(arguments.profile_file).resolve()

    try:
        data = yaml.safe_load(profile_path.read_text())
    except (OSError, yaml.YAMLError) as e:
        print_error_message(
            title=f'Failed to read profile: {e}',
            next_steps=['Check that the file is valid YAML'],
        )
        return

    if not isinstance(data, dict):
        print_error_message(
            title='Profile file must contain a YAML mapping',
            next_steps=['See existing profiles in appdata/os-profiles/ for examples'],
        )
        return

    missing = _REQUIRED_FIELDS - data.keys()
    if missing:
        print_error_message(
            title=f'Missing required fields: {", ".join(sorted(missing))}',
            next_steps=[f'Required fields: {", ".join(sorted(_REQUIRED_FIELDS))}'],
        )
        return

    name = data['name']
    dest = OS_PROFILES_DIR / f'{name}.yml'

    OS_PROFILES_DIR.mkdir(parents=True, exist_ok=True)
    shutil.copy2(profile_path, dest)
    reload_catalog()

    print_success_message(
        title=f'OS profile "{name}" added successfully',
        location=str(dest),
        next_steps=[
            f'Create a VM: adare vm create {name}',
            'List profiles: adare manage os-profile list',
        ],
    )


def exec_os_profile_remove(arguments):
    """Remove a custom OS profile."""
    name = arguments.name
    profile_path = OS_PROFILES_DIR / f'{name}.yml'

    if not profile_path.is_file():
        print_error_message(
            title=f'No custom profile found: {name}',
            next_steps=[
                'Run: adare manage os-profile list',
                'Only custom profiles can be removed (not built-in ones)',
            ],
        )
        return

    profile_path.unlink()
    reload_catalog()

    print_success_message(
        title=f'OS profile "{name}" removed successfully',
        next_steps=['Run: adare manage os-profile list'],
    )
