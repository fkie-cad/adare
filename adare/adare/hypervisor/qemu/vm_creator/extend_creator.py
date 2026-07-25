"""QEMU-only helpers for `adare environment extend --interactive` (Mode B).

Boots a throwaway overlay of a base VM disk in a native GUI window so the user
can install software by hand, then FLATTENS the overlay into a new standalone
qcow2 with no backing file. The flattened image is an immutable base -- exactly
like `vm create` output -- and flows through the identical experiment-runtime
path (a persistent overlay would be invisible at runtime, since the runtime
overlay machinery always rebuilds on the TRUE base and refuses to chain).

Boot-mode parity: the interactive window must boot the base the same way the
experiment runtime does. The runtime decides UEFI-vs-BIOS via
`get_boot_mode_for_os(guest_os, architecture)` (see
`hypervisor/qemu/mixins/configuration.py`), NOT via the OS catalog's
`requires_uefi`. We call that same function so the UEFI/BIOS choice is
identical, and -- when UEFI is needed -- create a fresh work NVRAM with the
same `create_nvram_for_vm` the runtime uses per run. NVRAM is never persisted
past the flatten; the runtime regenerates it on the immutable base.
"""

import logging
import platform
import shutil
import subprocess
import tempfile
from pathlib import Path

from adare.config import HYPERVISOR_CONFIGS
from adare.console import print_step
from adare.hypervisor.exceptions import HypervisorException
from adare.hypervisor.qemu.firmware import create_nvram_for_vm
from adare.hypervisor.qemu.utilities.disk_utils import get_boot_mode_for_os
from adare.hypervisor.qemu.vm_creator.disk_helpers import (
    DiskCompressionError, compress_qcow2_zstd,
)
from adare.hypervisor.qemu.vm_creator.interactive import run_post_install_session
from adare.hypervisor.qemu.vm_creator.os_catalog import OsDefinition

log = logging.getLogger(__name__)

__all__ = ['run_interactive_extend']

# Sensible fallbacks when the request does not pin --ram / --cpus.
_DEFAULT_RAM_MB = 4096
_DEFAULT_CPUS = 2

# Fixed name for the throwaway work overlay + its NVRAM inside the temp dir.
_WORK_NAME = 'work-overlay'


def _synthesize_os_definition(
    os_block: dict, ram_mb: int, cpus: int,
) -> tuple[OsDefinition, str]:
    """Build a minimal OsDefinition describing how to boot the base disk.

    Only `.architecture` (read by `qemu_params_for_arch`) and `.requires_uefi`
    (read by `run_post_install_session`) actually matter here; every other
    field gets a harmless placeholder.

    The UEFI/BIOS decision mirrors the experiment runtime EXACTLY by calling
    `get_boot_mode_for_os` -- the same function the runtime uses to set
    `config.boot_mode` for a loaded VM. `guest_os` is built from the OS block's
    platform/os/distribution so the runtime's `'windows' in guest_os` check
    behaves identically.

    Returns:
        Tuple of (OsDefinition, boot_mode_str) where boot_mode_str is
        'uefi' or 'bios' (for logging/UI).
    """
    architecture = os_block.get('architecture') or 'x86_64'
    guest_os = ' '.join(
        part for part in (
            os_block.get('platform') or '',
            os_block.get('os') or '',
            os_block.get('distribution') or '',
        ) if part
    ) or 'linux'

    boot_mode = get_boot_mode_for_os(guest_os, architecture)
    requires_uefi = boot_mode == 'uefi'

    os_def = OsDefinition(
        name='extend-interactive',
        display_name='Interactive extend base',
        platform=os_block.get('platform') or 'linux',
        distribution=os_block.get('distribution') or '',
        version=str(os_block.get('version') or '0'),
        iso_url='',
        iso_sha256='',
        iso_filename='',
        default_disk_size='0',
        default_ram_mb=ram_mb,
        default_cpus=cpus,
        requires_uefi=requires_uefi,
        architecture=architecture,
    )
    return os_def, boot_mode


def run_interactive_extend(
    base_disk: Path,
    dest_disk: Path,
    os_block: dict,
    ram: int | None,
    cpus: int | None,
    console: bool = False,
    compress: bool = True,
) -> tuple[bool, list[dict]]:
    """Boot an overlay of *base_disk* interactively, then flatten to *dest_disk*.

    The base disk is opened read-only through the overlay's backing chain and
    is NEVER mutated. *dest_disk* is a standalone qcow2 with no backing file.

    By default the session is GUI-only (a native QEMU window). With ``console``
    a terminal REPL is also started that records the commands typed in the guest
    as reproducible installs. Either way the user is asked at shutdown whether to
    store or discard the session.

    Args:
        base_disk: Path to the immutable base qcow2 to extend from.
        dest_disk: Path for the new flattened standalone qcow2.
        os_block: The environment-file `os:` dict (platform/os/distribution/
            version/architecture) used to decide boot mode.
        ram: RAM in MB (falls back to a sensible default).
        cpus: vCPU count (falls back to a sensible default).
        console: If True, also open the recording terminal REPL alongside the
            GUI window.
        compress: Zstd-compress the flattened disk (default True). On
            compression failure, falls back to a plain uncompressed flatten
            rather than losing the completed interactive session.

    Returns:
        Tuple of ``(store, recorded)``. ``store`` is the user's decision from the
        console: only when True is the overlay flattened into *dest_disk* and the
        recorded install dicts returned for folding into the new environment. On
        discard, ``(False, [])`` is returned and *dest_disk* is never created.

    Raises:
        HypervisorException: On any validation, overlay, boot, or flatten
            failure (including the QEMU-only Apple-Silicon guard).
        InteractiveSessionError: If the GUI QEMU session fails to boot.
    """
    base_disk = base_disk.resolve()
    if not base_disk.is_file():
        raise HypervisorException(f'Base disk not found: {base_disk}')

    # NEVER overwrite the base disk.
    if dest_disk.resolve() == base_disk:
        raise HypervisorException(
            f'Refusing to overwrite the base disk: destination "{dest_disk}" '
            f'resolves to the base disk. Choose a different --disk-name.'
        )

    # Fail fast before the (long) interactive session if the artifact exists.
    if dest_disk.exists():
        raise HypervisorException(
            f'Destination disk already exists: {dest_disk}. Remove it or choose '
            f'a different --disk-name.'
        )

    ram_mb = ram or _DEFAULT_RAM_MB
    cpu_count = cpus or _DEFAULT_CPUS

    os_def, boot_mode = _synthesize_os_definition(os_block, ram_mb, cpu_count)

    # Apple-Silicon guard: x86_64 guests can't be hardware-accelerated on ARM
    # macOS. Mirror the runtime guard (hypervisor/qemu/lifecycle.py) and fail
    # BEFORE booting rather than launching an unusable window.
    if (platform.system() == 'Darwin' and platform.machine() == 'arm64'
            and os_def.architecture != 'aarch64'):
        raise HypervisorException(
            f'QEMU cannot hardware-accelerate {os_def.architecture} guests on '
            'Apple Silicon (ARM). Only aarch64 guests are supported on Apple '
            'Silicon with HVF, so an x86_64 base cannot be extended '
            'interactively on this host.'
        )

    qemu_img = HYPERVISOR_CONFIGS['qemu']['qemu_img_exe']
    work_dir = Path(tempfile.mkdtemp(prefix='adare-extend-'))
    work_overlay = work_dir / f'{_WORK_NAME}.qcow2'

    try:
        # 1. Create the work overlay backed by the immutable base (absolute
        #    backing path -- mirrors hypervisor/qemu/mixins/disk.py for the
        #    cross-directory / external case).
        create_cmd = [
            qemu_img, 'create', '-f', 'qcow2', '-F', 'qcow2',
            '-b', str(base_disk), str(work_overlay),
        ]
        log.info('Creating interactive-extend work overlay: %s', ' '.join(create_cmd))
        result = subprocess.run(create_cmd, capture_output=True, text=True)
        if result.returncode != 0:
            raise HypervisorException(
                f'Failed to create work overlay: {result.stderr.strip()}'
            )

        # 2. Fresh work NVRAM only when UEFI is needed. Mirrors the runtime,
        #    which regenerates NVRAM per run rather than persisting it.
        work_nvram: Path | None = None
        if os_def.requires_uefi or os_def.architecture == 'aarch64':
            work_nvram = Path(
                create_nvram_for_vm(_WORK_NAME, work_dir, os_def.architecture)
            )

        # 3. Boot the GUI window + interactive console; blocks until the user
        #    stores/discards or shuts the VM down. Returns recorded installs.
        print_step(
            f'Booting base disk overlay ({boot_mode.upper()}) for interactive '
            f'customization...'
        )
        store, recorded = run_post_install_session(
            work_overlay, work_nvram, os_def, ram_mb, cpu_count,
            console_mode=console, ask_store=True,
        )

        # 4. Flatten the overlay into a standalone qcow2 (no backing file) ONLY
        #    when the user chose to store. On discard nothing is created; the
        #    work overlay is cleaned up by the `finally` below. The base is only
        #    read here, through the overlay's backing chain.
        if not store:
            print_step('Session discarded -- no environment will be created.')
            return False, []

        if compress:
            try:
                compress_qcow2_zstd(work_overlay, dest_disk)
                print_step(f'Flattened + compressed new standalone disk: [dim]{dest_disk}[/dim]')
                return True, recorded
            except DiskCompressionError as e:
                log.warning('Disk compression failed, falling back to plain flatten: %s', e)
                print_step(f'[yellow]Disk compression failed, falling back to plain flatten:[/yellow] {e}')
                dest_disk.unlink(missing_ok=True)

        convert_cmd = [
            qemu_img, 'convert', '-O', 'qcow2', str(work_overlay), str(dest_disk),
        ]
        log.info('Flattening interactive-extend overlay: %s', ' '.join(convert_cmd))
        result = subprocess.run(convert_cmd, capture_output=True, text=True)
        if result.returncode != 0:
            raise HypervisorException(
                f'Failed to flatten overlay into standalone disk: '
                f'{result.stderr.strip()}'
            )
        print_step(f'Flattened new standalone disk: [dim]{dest_disk}[/dim]')
        return True, recorded
    finally:
        # 5. Delete the work overlay + NVRAM + temp dir. No guest state leaks.
        shutil.rmtree(work_dir, ignore_errors=True)
