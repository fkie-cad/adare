"""CLI handler for `adare vm create` command."""

import logging
from dataclasses import replace
from pathlib import Path

from adare.console import print_error_message, print_success_message
from adare.hypervisor.qemu.vm_creator.os_catalog import OsDefinition, SetupLevel, default_host_cpus, get_os_definition
from adarelib.helper.yaml import dict_to_yaml

log = logging.getLogger(__name__)


def _generate_environment_file(
    disk_path: Path,
    os_def: OsDefinition,
    vm_name: str,
    env_name: str | None = None,
) -> Path:
    """Generate an environment YAML file for the newly created VM."""
    env_content = {
        'vm': str(disk_path),
        'os': {
            'os': os_def.display_name,
            'platform': os_def.platform,
            'distribution': os_def.distribution_label or os_def.distribution,
            'version': os_def.version,
            'language': 'English',
            'architecture': os_def.architecture,
        },
        'hypervisor': 'qemu',
    }

    filename = env_name or vm_name
    env_path = Path.cwd() / f'{filename}.yml'
    dict_to_yaml(env_path, env_content)
    return env_path


def exec_vm_create(arguments):
    """Create a new ADARE-ready VM from scratch.

    Handles both Linux (fully automated) and Windows (user-supplied ISO) flows.
    Produces a .qcow2 disk image and an environment YAML file.
    """
    os_name = arguments.os_name
    iso = getattr(arguments, 'iso', None)
    vm_name = getattr(arguments, 'name', None)
    disk_size = getattr(arguments, 'disk_size', None)
    ram = getattr(arguments, 'ram', None)
    cpus = getattr(arguments, 'cpus', None)
    force = getattr(arguments, 'force', False)
    vm_dir_raw = getattr(arguments, 'vm_dir', None)
    vm_dir = Path(vm_dir_raw).resolve() if vm_dir_raw else None
    setup_level = SetupLevel[getattr(arguments, 'setup_level', 'full').upper()]
    env_name = getattr(arguments, 'env_name', None)
    interactive = getattr(arguments, 'interactive', False)
    arch = getattr(arguments, 'arch', None)

    # Look up OS definition
    try:
        os_def = get_os_definition(os_name)
    except KeyError as e:
        print_error_message(
            title=str(e),
            next_steps=[
                'Run: adare manage os-profile list',
                'Example: adare vm create ubuntu2404',
            ],
        )
        return

    # Override architecture if --arch was specified
    if arch is not None:
        os_def = replace(os_def, architecture=arch)

    iso_path = Path(iso).resolve() if iso else None

    # Dispatch to the right creator — check install_mode before platform
    if os_def.install_mode == 'manual':
        if iso_path is None:
            print_error_message(
                title=f'ISO required for manual install of {os_def.display_name}',
                next_steps=[
                    f'Provide the ISO: adare vm create {os_name} --iso /path/to/installer.iso',
                ],
            )
            return

        from adare.hypervisor.qemu.vm_creator.manual_creator import create_manual_vm

        disk_path = create_manual_vm(
            os_def=os_def,
            iso_path=iso_path,
            vm_name=vm_name,
            disk_size=disk_size,
            ram_mb=ram,
            cpus=cpus,
            force=force,
            vm_dir=vm_dir,
            setup_level=setup_level,
        )
    elif os_def.platform == 'linux':
        from adare.hypervisor.qemu.vm_creator.linux_creator import create_linux_vm

        disk_path = create_linux_vm(
            os_def=os_def,
            vm_name=vm_name,
            disk_size=disk_size,
            ram_mb=ram,
            cpus=cpus,
            iso_path=iso_path,
            force=force,
            vm_dir=vm_dir,
            setup_level=setup_level,
        )
    elif os_def.platform == 'windows':
        if iso_path is None:
            print_error_message(
                title=f'Windows ISO required for {os_def.display_name}',
                next_steps=[
                    f'Provide the ISO path: adare vm create {os_name} --iso /path/to/windows.iso',
                    'Download from Microsoft (requires a valid license)',
                ],
            )
            return

        from adare.hypervisor.qemu.vm_creator.windows_creator import create_windows_vm

        disk_path = create_windows_vm(
            os_def=os_def,
            iso_path=iso_path,
            vm_name=vm_name,
            disk_size=disk_size,
            ram_mb=ram,
            cpus=cpus,
            force=force,
            vm_dir=vm_dir,
            setup_level=setup_level,
        )
    else:
        print_error_message(title=f"Unsupported platform: {os_def.platform}")
        return

    # Run interactive post-install session if requested (only for automated installs)
    if interactive and os_def.install_mode != 'manual':
        from adare.hypervisor.qemu.vm_creator.interactive import run_post_install_session

        nvram_path = disk_path.with_name(disk_path.stem + '_VARS.fd')
        if not nvram_path.exists():
            nvram_path = None

        run_post_install_session(
            disk_path=disk_path,
            nvram_path=nvram_path,
            os_def=os_def,
            ram_mb=ram or os_def.default_ram_mb,
            cpus=cpus or os_def.default_cpus or default_host_cpus(),
        )

    final_name = vm_name or disk_path.stem

    try:
        env_file_path = _generate_environment_file(disk_path, os_def, final_name, env_name=env_name)
        env_next_steps = [
            f'Load environment: adare environment load {env_file_path} --no-copy',
            'Then: adare experiment load <playbook> && adare experiment run',
        ]
    except OSError as e:
        log.warning('Failed to generate environment file: %s', e)
        env_next_steps = [
            'Create an environment YAML referencing this VM',
            'Then: adare environment load <env.yml> --no-copy',
        ]

    if os_def.install_mode == 'manual':
        tip = 'This VM was installed manually. Configure SSH/guest agent access for full ADARE integration.'
    elif setup_level == SetupLevel.BARE:
        tip = 'No guest tools or agent software installed (--setup bare).'
    elif setup_level == SetupLevel.BASE:
        tip = 'Guest tools installed. No Python environment (--setup base).'
    elif setup_level == SetupLevel.AGENT:
        tip = 'adarevm agent pre-installed. Ready for immediate experiment execution.'
    else:
        tip = 'Python environment pre-installed. Ready for experiments.'

    print_success_message(
        title=f'VM "{final_name}" created successfully!',
        location=str(disk_path),
        next_steps=env_next_steps,
        tip=tip,
    )
