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
    # GUI-automation options (gui-auto install mode).
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
                'Run: adare os-profile list',
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
            setup_level.name.lower(), os_def.install_mode,
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

        from adare.helperfunctions.hash import hash_file_sha256
        from adare.console import print_step
        print_step(f'Hashing ISO for recipe integrity: [dim]{iso_path}[/dim]')
        iso_sha256 = hash_file_sha256(iso_path)
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
                    f'Build the disk on load: adare environment load {env_file_path} '
                    f'--iso {iso_path}',
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

    final_name = vm_name or disk_path.stem

    try:
        env_file_path = build_baked_environment_file(disk_path=disk_path, os_def=os_def, vm_name=final_name, env_name=env_name)
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

    if os_def.install_mode == 'gui-auto':
        tip = ('This VM was installed by the GUI agent. The generated playbook can be '
               'edited and replayed; see the install report for a screenshot walkthrough.')
    elif os_def.install_mode == 'playbook':
        tip = ('This VM was installed by deterministic playbook replay driven by '
               'cv-server OCR (no vision LLM). The per-step screenshots next to the '
               'disk show exactly what was clicked.')
    elif os_def.install_mode == 'manual':
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
