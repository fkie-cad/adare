"""Registering a disk image as a Vm row (a VM image).

A Vm row is identified by its disk hash and shared by every environment whose
disk has the same bytes, so registration either reuses that row (after checking
the environment agrees with it) or copies + hashes the disk into a new one.

Images never change: a different disk under a registered name is a new image,
and the old one is retired (see :func:`retire_image`), never overwritten.
"""

import logging
from pathlib import Path

from adare.backend.vm import database as vm_database
from adare.database.api.vm.exceptions import VMLoadError

log = logging.getLogger(__name__)


def _check_reused_vm_consistency(existing_vm, environment_metadata, hypervisor: str) -> None:
    """Refuse to share one disk between environments that disagree about it.

    A Vm row is shared by every environment whose disk has the same hash, and
    run-time code reads the hypervisor and guest OS from that row. An
    environment declaring a different hypervisor or guest platform/architecture
    for the same bytes would silently run with the first loader's values.
    """
    from adare.backend.environment.exceptions import EnvironmentLoadFailed

    mismatches = []
    if existing_vm.hypervisor != hypervisor:
        mismatches.append(f"hypervisor: registered '{existing_vm.hypervisor}', this environment '{hypervisor}'")
    os_info = getattr(environment_metadata, 'os', None)
    if os_info is not None and existing_vm.osinfo is not None:
        for field in ('platform', 'architecture'):
            registered, declared = getattr(existing_vm.osinfo, field), getattr(os_info, field)
            if registered and declared and registered != declared:
                mismatches.append(f"os.{field}: registered '{registered}', this environment '{declared}'")
    if mismatches:
        raise EnvironmentLoadFailed(
            log,
            f"Disk is already registered as VM '{existing_vm.name}' with different settings: " + '; '.join(mismatches),
            possible_solutions=[
                'Make the environment file match the registered disk',
                f"List the environments sharing this disk with: adare vm info {existing_vm.id}",
            ],
        )


def retire_image(vm_id: str, replacing: Path | None = None) -> None:
    """Free a registered image's name (and managed disk path) for a new image.

    The old image stays usable for the environment versions that reference it,
    renamed to ``<name>-<sha12>`` -- its managed disk and sidecars alike. An image
    no environment version references is removed instead.

    *replacing* is the new image's disk. If it is the old image's disk file (its
    bytes were overwritten in place), the old image is lost: its row is renamed and
    points at a ``.replaced-<sha12>`` path that does not exist, so its environment
    versions fail their integrity check instead of running on the new bytes.
    """
    from adare.backend.vm.exceptions import VMRemovalError
    from adare.backend.vm.image_record import packages_path, record_path
    from adare.backend.vm.removal import _is_managed, plan_vm_removal, teardown_unreferenced_vm
    from adare.database.api.environment import EnvironmentDbApi

    with EnvironmentDbApi() as db:
        referenced = db.is_vm_referenced(vm_id)
    if not referenced:
        teardown_unreferenced_vm(vm_id)
        return
    plan = plan_vm_removal(vm_id)
    if plan.live_instances:
        raise VMRemovalError(
            log,
            f"VM '{plan.vm_name}' is running ({', '.join(plan.live_instances)}); "
            'its image cannot be replaced while it runs',
        )
    image = vm_database.get_image(vm_id)
    if image is None:
        return
    retired = f"{image['name']}-{image['hash'][:12]}"
    disk = Path(image['file'])
    overwritten = replacing is not None and disk.exists() and replacing.exists() and disk.samefile(replacing)
    if overwritten or (disk.exists() and _is_managed(disk)):
        # The record and package list describe the old image: they go with it
        for sidecar in (record_path(disk), packages_path(disk)):
            if sidecar.exists():
                sidecar.rename(sidecar.with_name(sidecar.name.replace(disk.stem, retired, 1)))
    if overwritten:
        log.warning(
            f"The disk of image '{image['name']}' was overwritten; the environment versions using it "
            'can no longer run (their image is gone)'
        )
        vm_database.set_vm_file(vm_id, f"{disk}.replaced-{image['hash'][:12]}")
    elif disk.exists() and _is_managed(disk):
        moved = disk.with_name(f'{retired}{disk.suffix}')
        disk.rename(moved)
        vm_database.set_vm_file(vm_id, str(moved))
    vm_database.rename_vm(vm_id, retired)
    log.info(f"Kept the replaced image '{image['name']}' as '{retired}' for the environment versions using it")


def register_built_image(disk: Path, record: dict, managed: bool) -> str:
    """Register a disk built by ``adare vm create`` with its record; returns the Vm id.

    The name is the disk's stem. A disk already registered (same bytes) keeps its
    row and gains the record if it had none.
    """
    from adare.backend.vm import image_record

    existing = vm_database.get_image(record['sha256'])
    if existing:
        if not existing['build_record']:
            image_record.store(existing['id'], Path(existing['file']), record)
        return str(existing['id'])
    os_block = record['os']
    build = record.get('build') or {}
    vm_database.create_vm(
        project_path=Path.cwd(),
        name=disk.stem,
        file_path=disk,
        file_hash=record['sha256'],
        description=f"Built by adare vm create ({build.get('profile')})",
        os_platform=os_block.get('platform', ''),
        os_type=os_block.get('os', ''),
        os_distribution=os_block.get('distribution', ''),
        os_version=os_block.get('version', ''),
        os_language=os_block.get('language', ''),
        os_architecture=os_block.get('architecture', 'x86_64'),
        silent=True,
        no_copy=not managed,
        hypervisor=record['hypervisor'],
        iso_sha256=(build.get('iso') or {}).get('sha256'),
        profile_name=build.get('profile'),
        build_record=image_record.to_json(record),
    )
    created = vm_database.get_image(record['sha256'])
    if created is None:
        raise VMLoadError(log, f'Registering {disk} failed: no VM with its hash afterwards')
    return str(created['id'])


def load_vm_file_for_environment(
    project_path: Path,
    vm_path: Path,
    environment_metadata,
    no_copy: bool = False,
    force: bool = False,
    build_source: str = 'baked',
    recipe_hash: str | None = None,
    iso_sha256: str | None = None,
    profile_name: str | None = None,
) -> dict:
    """
    Load VM file during environment load - only hash calculation and file copying.
    No VirtualBox import happens here!

    Args:
        project_path: Path to the project
        vm_path: Path to VM file
        environment_metadata: Environment configuration
        no_copy: If True, reference file at original location instead of copying
        force: If True, a registered VM of the same name but other bytes is retired
        build_source: 'baked' (default) or 'recipe' - how the disk was produced
        recipe_hash: Recipe integrity anchor (recipe builds only)
        iso_sha256: Expected ISO SHA256 (recipe builds only)
        profile_name: OS profile the disk was built from (recipe builds only)

    Returns:
        Dict with 'vm_id' and 'was_existing' keys
    """
    # Extract hypervisor from environment metadata
    hypervisor = getattr(environment_metadata, 'hypervisor', 'virtualbox')
    log.info(f"Using hypervisor: {hypervisor}")

    # The digest cache re-hashes only a disk whose size, mtime, ctime or inode
    # changed, so a disk that `vm create` or the vm_sha256 check just hashed is
    # not read again.
    from adare.helperfunctions.digest_cache import cached_file_sha256

    file_hash = cached_file_sha256(vm_path)
    log.info(f"VM file hash: {file_hash}")

    # Check if VM already exists by hash BEFORE copying
    existing_vm = vm_database.get_vm_by_hash(file_hash)
    if existing_vm:
        log.info(f"VM with hash {file_hash} already exists: {existing_vm.name} - reusing it, no file copy")
        _check_reused_vm_consistency(existing_vm, environment_metadata, hypervisor)
        return {'vm_id': existing_vm.id, 'was_existing': True}

    # A different disk under a registered name is a new image: with --force the old
    # one is retired (renamed, kept for the versions using it), never overwritten.
    same_name = vm_database.get_image(vm_path.stem)
    if same_name and force:
        retire_image(same_name['id'], replacing=vm_path)

    # VM doesn't exist or existing VM can't be reused - create new one with file operations
    log.info("Creating new VM entry with file operations...")

    # Determine if we should copy or reference
    if no_copy:
        log.info("Using --no-copy mode: VM file will be referenced at original location")
        log.warning(f"IMPORTANT: VM file must remain at {vm_path} for experiments to work!")

    vm = vm_database.create_vm(
        project_path=project_path,
        name=vm_path.stem,
        file_path=vm_path,
        file_hash=file_hash,
        description=f"VM for {environment_metadata.name}",
        os_platform=environment_metadata.os.platform,
        os_type=environment_metadata.os.os,
        os_distribution=environment_metadata.os.distribution,
        os_version=environment_metadata.os.version,
        os_language=environment_metadata.os.language,
        os_architecture=environment_metadata.os.architecture,
        silent=False,
        no_copy=no_copy,  # Pass the flag
        hypervisor=hypervisor,  # NEW: Pass hypervisor type
        force=force,  # Pass force flag for VM overwriting
        build_source=build_source,
        recipe_hash=recipe_hash,
        iso_sha256=iso_sha256,
        profile_name=profile_name,
    )

    log.info(f"VM file loaded into database: {vm.name} (ID: {vm.id})")
    return {'vm_id': vm.id, 'was_existing': False}
