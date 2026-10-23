"""Registering a disk image as a Vm row when an environment is loaded.

A Vm row is identified by its disk hash and shared by every environment whose
disk has the same bytes, so registration either reuses that row (after checking
the environment agrees with it) or copies + hashes the disk into a new one.
"""

import logging
from pathlib import Path

from adare.backend.vm import database as vm_database
from adare.backend.vm.manager import VMFileManager

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


def _refuse_replacing_shared_disk(vm_name: str, file_hash: str, environment_name: str) -> None:
    """Refuse to swap the disk of a VM that another environment still runs on.

    With ``--force``, a disk whose name matches a registered VM but whose bytes
    differ replaces that VM's disk in place. That is fine for the environment
    being reloaded (its previous version is superseded and pinned to the old
    hash), but any *other* environment on the same VM would silently start
    running on different bytes.
    """
    from adare.backend.environment.exceptions import EnvironmentLoadFailed
    from adare.database.api.environment import EnvironmentDbApi

    existing = vm_database.get_vm_by_name(vm_name)
    if not existing or existing.hash == file_hash:
        return
    with EnvironmentDbApi() as db:
        others = sorted(
            {env.name for env in db.get_environments() if env.vm_id == existing.id and env.name != environment_name}
        )
    if others:
        raise EnvironmentLoadFailed(
            log,
            f"VM '{vm_name}' is used by other environments ({', '.join(others)}); "
            "replacing its disk would change what they run on.",
            possible_solutions=[
                'Give the new disk a different file name so it is registered as a separate VM',
                'Remove or reload the other environments first',
            ],
        )


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
        force: If True, overwrite existing VM with same name but different hash
        build_source: 'baked' (default) or 'recipe' - how the disk was produced
        recipe_hash: Recipe integrity anchor (recipe builds only)
        iso_sha256: Expected ISO SHA256 (recipe builds only)
        profile_name: OS profile the disk was built from (recipe builds only)

    Returns:
        Dict with 'vm_id' and 'was_existing' keys
    """
    vm_manager = VMFileManager()

    # Extract hypervisor from environment metadata
    hypervisor = getattr(environment_metadata, 'hypervisor', 'virtualbox')
    log.info(f"Using hypervisor: {hypervisor}")

    # Calculate hash FIRST (heavy operation done during environment load)
    log.info("Calculating VM file hash during environment load...")
    file_hash = vm_manager.calculate_file_hash(vm_path, silent=False)
    log.info(f"VM file hash: {file_hash}")

    # Check if VM already exists by hash BEFORE copying
    existing_vm = vm_database.get_vm_by_hash(file_hash)
    if existing_vm:
        log.info(f"VM with hash {file_hash} already exists: {existing_vm.name} - reusing it, no file copy")
        _check_reused_vm_consistency(existing_vm, environment_metadata, hypervisor)
        return {'vm_id': existing_vm.id, 'was_existing': True}

    _refuse_replacing_shared_disk(vm_path.stem, file_hash, environment_metadata.name)
    # With --force, create_vm updates a VM of the same name in place. That row
    # predates this load (superseded versions may reference it), so it must not
    # count as created -- a failed load would otherwise delete it.
    same_name = vm_database.get_vm_by_name(vm_path.stem)

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
    return {'vm_id': vm.id, 'was_existing': same_name is not None and same_name.id == vm.id}
