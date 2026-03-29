"""CLI handlers for `adare manage os-profile` commands."""

import shutil
from pathlib import Path

import yaml

from adare.config.configdirectory import OS_PROFILES_DIR
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
