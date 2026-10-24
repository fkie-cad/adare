"""CLI handler for `adare vm create` command."""

import logging
from dataclasses import replace
from pathlib import Path

from adare.console import print_error_message, print_success_message
from adare.hypervisor.qemu.vm_creator.dispatch import (
    GUI_INSTALL_MODES,
    DispatchError,
    GuiBuildOptions,
    create_vm_disk,
)
from adare.hypervisor.qemu.vm_creator.os_catalog import OsDefinition, SetupLevel, default_host_cpus, get_os_definition
from adare.services.environment_recipe import build_baked_environment_file, build_recipe_environment_file

log = logging.getLogger(__name__)


def _use_recipe(os_def: OsDefinition, recipe_flag: bool | None) -> bool:
    """Decide recipe vs baked. Explicit flag wins; else Windows defaults to
    recipe (rebuildable on eval/login expiry), Linux defaults to baked."""
    if recipe_flag is not None:
        return recipe_flag
    return os_def.platform == 'windows'


def _in_managed_storage(disk_path: Path) -> bool:
    from adare.config.configdirectory import VMS_DIR

    try:
        return disk_path.resolve().parent == VMS_DIR.resolve()
    except OSError:
        return False


def _image_name(vm_name: str | None, os_def: OsDefinition, force: bool) -> str | None:
    """The new image's name (``<profile>-<YYYYMMDD>`` by default), or None if it is taken."""
    from datetime import datetime

    name = vm_name or f'{os_def.name}-{datetime.now():%Y%m%d}'
    return name if _free_image_name(name, force) else None


def _free_image_name(name: str, force: bool) -> bool:
    """Make sure *name* can take a new image; False (after printing why) if not.

    Images never change: with --force a registered image of that name is retired
    (kept as ``<name>-<sha12>`` for the environments using it) before the build
    reuses its disk path.
    """
    from adare.backend.vm import database as vm_database

    registered = vm_database.get_image(name)
    if registered is None:
        return True
    if not force:
        print_error_message(
            title=f'An image named "{name}" is already registered',
            next_steps=[
                f'Build under another name: --name {name}-2',
                'Or add --force: the registered image is kept as '
                f'"{name}-{registered["hash"][:12]}" for the environments using it',
            ],
        )
        return False
    from adare.backend.vm.registration import retire_image

    retire_image(registered['id'])
    return True


def _register_image(disk_path: Path, os_def: OsDefinition, setup_level: SetupLevel, iso_path: Path | None) -> str:
    """Write the image record next to *disk_path*, register the image; returns the disk sha256."""
    from adare.backend.vm import image_record
    from adare.backend.vm.registration import register_built_image
    from adare.console import print_step
    from adare.helperfunctions.digest_cache import cached_file_sha256
    from adare.services.environment_recipe import os_block

    print_step(f'Hashing disk for integrity (this may take a while for large disks): [dim]{disk_path}[/dim]')
    sha256 = cached_file_sha256(disk_path)
    iso_filename: str | None
    iso_sha256: str | None
    if iso_path is not None:
        iso_filename, iso_sha256 = iso_path.name, cached_file_sha256(iso_path)
    else:
        iso_filename, iso_sha256 = os_def.iso_filename or None, os_def.iso_sha256 or None
    record = image_record.new_record(
        disk=disk_path,
        sha256=sha256,
        hypervisor='qemu',
        os_block=os_block(os_def),
        build=image_record.build_entry(
            os_def=os_def, setup_level=setup_level, iso_filename=iso_filename, iso_sha256=iso_sha256
        ),
    )
    image_record.write_record(disk_path, record)
    register_built_image(disk_path, record, managed=_in_managed_storage(disk_path))
    print_step(f'Image registered with its record: [dim]{image_record.record_path(disk_path)}[/dim]')
    return sha256


def _success_tip(os_def: OsDefinition, setup_level: SetupLevel) -> str:
    """What the finished VM has (and lacks), by install mode and setup level."""
    if os_def.install_mode == 'gui-auto':
        return (
            'This VM was installed by the GUI agent. The generated playbook can be '
            'edited and replayed; see the install report for a screenshot walkthrough. '
            'It has no guest agent or autologin yet, so ADARE cannot drive it as it is.'
        )
    if os_def.install_mode == 'playbook':
        return (
            'This VM was installed by deterministic playbook replay driven by '
            'cv-server OCR (no vision LLM). The per-step screenshots next to the '
            'disk show exactly what was clicked. '
            + (
                'No guest agent, autologin or other ADARE setup was added (--setup bare): '
                'ADARE cannot drive this VM as it is.'
                if setup_level == SetupLevel.BARE
                else 'Guest agent, autologin and no screen lock were set up and checked after a reboot.'
            )
        )
    if os_def.install_mode == 'manual':
        return (
            'This VM was installed manually. No guest agent or autologin was added (--setup bare): '
            'ADARE cannot drive it as it is.'
            if setup_level == SetupLevel.BARE or os_def.platform != 'linux'
            else 'This VM was installed manually; ADARE then installed its guest agent and set up autologin, '
            'unless a warning above says otherwise.'
        )
    if setup_level == SetupLevel.BARE:
        return 'No guest tools or agent software installed (--setup bare).'
    if setup_level == SetupLevel.BASE:
        return 'Guest tools installed and checked after a reboot. No Python environment (--setup base).'
    if setup_level == SetupLevel.AGENT:
        return 'adarevm agent pre-installed. Ready for immediate experiment execution.'
    return 'Python environment pre-installed; guest agent and autologin checked after a reboot. Ready for experiments.'


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
    env_name = getattr(arguments, 'env_name', None)
    interactive = getattr(arguments, 'interactive', False)
    arch = getattr(arguments, 'arch', None)
    allow_emulation = getattr(arguments, 'allow_emulation', False)
    compress = getattr(arguments, 'compress', True)
    recipe_flag = getattr(arguments, 'recipe', None)
    byo_iso = getattr(arguments, 'byo_iso', False)
    iso_notes = getattr(arguments, 'iso_notes', None)
    bare = getattr(arguments, 'bare', False)
    setup_arg = getattr(arguments, 'setup_level', None)
    # Resolve the setup level once, before branching, so every creator path
    # (recipe, manual, gui-auto, playbook, linux, windows) honours it. `--setup` wins;
    # `--bare` is the deprecated alias for `--setup bare`.
    if setup_arg is not None:
        setup_level = SetupLevel[setup_arg.upper()]
        if bare and setup_level != SetupLevel.BARE:
            log.warning('--bare is ignored because --setup %s was given explicitly', setup_arg)
    else:
        setup_level = SetupLevel.BARE if bare else SetupLevel.FULL
    # GUI-automation options (gui-auto install mode; --display also playbook).
    gui_record = getattr(arguments, 'record', False)
    gui_relearn = getattr(arguments, 'relearn', False)
    gui_display = getattr(arguments, 'display', False)
    gui_template = getattr(arguments, 'template', None)

    if setup_level == SetupLevel.AGENT:
        print_error_message(
            title="Setup level 'agent' is not implemented",
            next_steps=[
                f'Use the default instead: adare vm create {os_name} --setup full',
                'The adarevm agent installs itself on the first experiment/dev-session run, '
                'so no create-time install is needed.',
            ],
        )
        return

    # Look up OS definition
    try:
        os_def = get_os_definition(os_name)
    except KeyError as e:
        print_error_message(
            title=str(e),
            next_steps=[
                'Run: adare vm profile list',
                'Example: adare vm create ubuntu2404',
            ],
        )
        return

    # Override architecture if --arch was specified
    if arch is not None:
        os_def = replace(os_def, architecture=arch)

    if setup_level != SetupLevel.FULL and os_def.install_mode in GUI_INSTALL_MODES:
        log.warning(
            '--setup %s has little effect for %s installs: they bake no Python environment anyway',
            setup_level.name.lower(),
            os_def.install_mode,
        )

    iso_path = Path(iso).resolve() if iso else None

    # Recipe mode: emit a declarative recipe environment and defer the build to
    # `environment load` (build once, cached + hashed by recipe inputs). This is
    # the default for Windows so an expired eval/login can be rebuilt by dropping
    # in a fresh ISO. A recipe always needs an ISO with a known SHA256.
    if _use_recipe(os_def, recipe_flag):
        if iso_path is None:
            print_error_message(
                title=f'ISO required to create a recipe environment for {os_def.display_name}',
                next_steps=[
                    f'Provide the ISO: adare vm create {os_name} --iso /path/to/installer.iso',
                    'Or build a baked disk instead: add --no-recipe',
                ],
            )
            return
        if interactive:
            log.warning('--interactive is ignored for recipe environments (build is declarative)')
        if vm_dir is not None:
            log.warning('--vm-dir is ignored for recipe environments (built disks live in managed storage)')
        # BYO ISO exists because Windows installer media cannot lawfully be
        # rehosted. For Linux the ISO is freely redistributable, so a published URL
        # is required instead -- refuse rather than emit an unpublishable env.
        if byo_iso and os_def.platform != 'windows':
            print_error_message(
                title=f'--byo-iso is Windows-only ({os_name} is a {os_def.platform} profile)',
                details='A Linux ISO is freely redistributable, so it must be published '
                'as an http(s) URL rather than left to the consumer.',
                next_steps=[
                    f'Drop --byo-iso: adare vm create {os_name} --iso {iso_path} --recipe',
                    'Then publish with the catalog ISO URL for this profile',
                ],
            )
            return

        from adare.console import print_step
        from adare.helperfunctions.digest_cache import cached_file_sha256

        print_step(f'Hashing ISO for recipe integrity: [dim]{iso_path}[/dim]')
        iso_sha256 = cached_file_sha256(iso_path)
        final_name = env_name or vm_name or f'{os_name}-recipe'

        env_file_path = build_recipe_environment_file(
            os_name=os_name,
            os_def=os_def,
            iso_path=iso_path,
            iso_sha256=iso_sha256,
            setup_level=setup_level,
            disk_size=disk_size,
            ram=ram,
            cpus=cpus,
            arch=arch,
            env_name=final_name,
            byo_iso=byo_iso,
            iso_notes=iso_notes,
        )
        if byo_iso:
            print_success_message(
                title=f'Recipe environment "{final_name}" created (consumer-supplied ISO)!',
                location=str(env_file_path),
                next_steps=[
                    f'Build the disk on load: adare environment load {env_file_path} --iso {iso_path}',
                    'Then: adare experiment load <playbook> && adare experiment run',
                ],
                tip=f'The descriptor names "{iso_path.name}" + its sha256 instead of a '
                f'path, so it is publishable. Consumers put that ISO in '
                f'~/.adare/isos/ (or pass --iso) and the disk is built there.',
            )
            return
        print_success_message(
            title=f'Recipe environment "{final_name}" created!',
            location=str(env_file_path),
            next_steps=[
                f'Build the disk on load: adare environment load {env_file_path}',
                'Then: adare experiment load <playbook> && adare experiment run',
            ],
            tip='The disk is built once from the ISO on first load and cached by its recipe hash. '
            'Drop in a fresh ISO (new iso_sha256) to rebuild as a new environment.',
        )
        return

    # Resolve the image name before building: the build reuses its disk path.
    vm_name = _image_name(vm_name, os_def, force)
    if vm_name is None:
        return

    # Dispatch to the right creator. The install_mode-before-platform rule lives in
    # vm_creator.dispatch, shared with recipe builds so the two cannot drift.
    try:
        disk_path = create_vm_disk(
            os_def=os_def,
            iso_path=iso_path,
            vm_name=vm_name,
            disk_size=disk_size,
            ram_mb=ram,
            cpus=cpus,
            force=force,
            vm_dir=vm_dir,
            setup_level=setup_level,
            compress=compress,
            allow_emulation=allow_emulation,
            gui=GuiBuildOptions(
                record=gui_record,
                relearn=gui_relearn,
                display=gui_display,
                template=gui_template,
            ),
        )
    except DispatchError as e:
        print_error_message(title=e.title, next_steps=e.next_steps)
        return

    # Run interactive post-install session if requested (only for seed-based
    # automated installs — the manual/gui-* modes already drive the GUI directly).
    if interactive and os_def.install_mode not in GUI_INSTALL_MODES:
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
            allow_emulation=allow_emulation,
        )

    final_name = vm_name

    try:
        vm_sha256 = _register_image(disk_path, os_def, setup_level, iso_path)
        env_file_path = build_baked_environment_file(
            disk_path=disk_path, os_def=os_def, vm_name=final_name, env_name=env_name, vm_sha256=vm_sha256
        )
        # A disk already in managed storage is registered in place (no copy);
        # --no-copy only matters for a custom --vm-dir.
        no_copy = '' if _in_managed_storage(disk_path) else ' --no-copy'
        env_next_steps = [
            f'Load environment: adare environment load {env_file_path}{no_copy}',
            'Then: adare experiment load <playbook> && adare experiment run',
        ]
    except OSError as e:
        log.warning('Failed to generate environment file: %s', e)
        env_next_steps = [
            'Create an environment YAML referencing this VM',
            'Then: adare environment load <env.yml>',
        ]

    tip = _success_tip(os_def, setup_level)

    print_success_message(
        title=f'VM "{final_name}" created successfully!',
        location=str(disk_path),
        next_steps=env_next_steps,
        tip=tip,
    )
