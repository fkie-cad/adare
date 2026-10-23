"""Per-run QEMU resources.

Every QEMU experiment run boots a throwaway qcow2 overlay on top of the
environment's read-only disk (the *template*) and gets its own UEFI varstore,
domain config, domain UUID and a copy of the environment's vTPM template. Nothing
a run writes survives it, so runs of one environment are independent and can run
concurrently; the template is only ever opened read-only (as a backing file).

Layout under ``QEMU_STATE_DIR`` (``~/.adare/qemu``):

- ``disks/<run>-overlay-<ulid>.qcow2`` / ``disks/<run>-nvram.fd`` -- run disk + UEFI vars
- ``vms/<run>.json`` -- run domain config
- ``templates/<hash16>.qcow2`` -- one-time qcow2 conversion of a non-qcow2 template
- ``tpm-templates/<vm_id>/tpm2/`` -- the environment's vTPM; each run boots a copy at
  libvirt's ``swtpm/<run-domain-uuid>/tpm2/``

``<run>`` is the run's VmInstance name; :func:`remove_run_files` deletes everything
keyed by it.
"""

import json
import logging
import os
import shutil
import subprocess
import tarfile
import tempfile
import uuid
from collections.abc import Iterator
from contextlib import contextmanager, suppress
from pathlib import Path
from typing import Any

from adare.config.configdirectory import QEMU_STATE_DIR
from adare.helperfunctions.file.lock import exclusive_lock
from adare.hypervisor.exceptions import HypervisorException
from adare.hypervisor.qemu.mixins.configuration import (
    _ADARE_VM_UUID_NAMESPACE,
    get_qemu_disk_dir,
    get_qemu_runtime_dir,
    get_qemu_vm_config_dir,
)

log = logging.getLogger(__name__)

TEMPLATE_DISK_DIR = QEMU_STATE_DIR / 'templates'
TPM_TEMPLATE_DIR = QEMU_STATE_DIR / 'tpm-templates'
_TPM_STATE_FILE = 'tpm2-00.permall'


# ---------------------------------------------------------------------------
# Template disk
# ---------------------------------------------------------------------------


def detect_disk_format(path: Path, qemu_img: str) -> str:
    """qemu-img's format name for ``path`` ('qcow2', 'vmdk', 'raw', ...); 'ova' for an OVA archive."""
    if path.suffix.lower() == '.ova':
        return 'ova'
    result = subprocess.run(
        [qemu_img, 'info', '--output=json', '-U', str(path)], capture_output=True, text=True, check=False
    )
    if result.returncode != 0:
        raise HypervisorException(f"Cannot read disk format of {path}: {result.stderr.strip()}")
    fmt: str = json.loads(result.stdout)['format']
    return fmt


def resolve_template_disk(vm_file: Path, vm_hash: str, qemu_img: str) -> Path:
    """The qcow2 file runs of this VM overlay: the disk itself, or a one-time conversion.

    Overlays need a qcow2 backing file. A non-qcow2 disk (OVA, VMDK, VDI, raw) is
    converted once into ``templates/<hash16>.qcow2`` -- keyed by the disk's
    content hash, so a replaced disk never reuses a stale conversion -- under a
    lock so concurrent first runs convert it only once.
    """
    vm_file = Path(vm_file)
    if detect_disk_format(vm_file, qemu_img) == 'qcow2':
        return vm_file

    TEMPLATE_DISK_DIR.mkdir(parents=True, exist_ok=True)
    target = TEMPLATE_DISK_DIR / f'{vm_hash[:16]}.qcow2'
    with exclusive_lock(target.with_suffix('.lock')):
        if target.exists():
            return target
        log.info(f"Converting {vm_file.name} to a qcow2 template (one-time): {target}")
        with tempfile.TemporaryDirectory(dir=TEMPLATE_DISK_DIR) as work:
            source = _extract_ova_disk(vm_file, Path(work)) if vm_file.suffix.lower() == '.ova' else vm_file
            partial = Path(work) / target.name
            result = subprocess.run(
                [qemu_img, 'convert', '-O', 'qcow2', str(source), str(partial)],
                capture_output=True,
                text=True,
                check=False,
            )
            if result.returncode != 0:
                raise HypervisorException(f"Failed to convert {vm_file} to qcow2: {result.stderr.strip()}")
            os.replace(partial, target)
        if os.name == 'posix':
            target.chmod(0o444)
    return target


def _extract_ova_disk(ova: Path, work_dir: Path) -> Path:
    with tarfile.open(ova) as tar:
        members = [m for m in tar.getmembers() if m.isfile() and m.name.lower().endswith(('.vmdk', '.vdi'))]
        if not members:
            raise HypervisorException(f"No VMDK/VDI disk found in OVA {ova}")
        tar.extract(members[0], work_dir, filter='data')
    return work_dir / members[0].name


# ---------------------------------------------------------------------------
# vTPM
# ---------------------------------------------------------------------------


def swtpm_state_root() -> Path:
    """libvirt (session) keeps each domain's swtpm state in ``<this>/<domain-uuid>/``."""
    config_home = Path(os.environ.get('XDG_CONFIG_HOME') or Path.home() / '.config')
    return config_home / 'libvirt' / 'qemu' / 'swtpm'


def _legacy_tpm_dir(vm_id: str) -> Path:
    """Where the vTPM shared by all runs of an environment lived before per-run copies."""
    return swtpm_state_root() / str(uuid.uuid5(_ADARE_VM_UUID_NAMESPACE, vm_id)) / 'tpm2'


def _tpm_template(vm_id: str) -> Path:
    return TPM_TEMPLATE_DIR / vm_id / 'tpm2'


def adopt_legacy_tpm(vm_id: str) -> bool:
    """Keep the vTPM all runs of an environment used to share as its template.

    Before per-run copies every run of an environment booted the same vTPM
    (``swtpm/<uuid5(vm_id)>/``). Adopting it keeps that TPM's identity (EK,
    certificates, owner state) for future runs. No-op if a template exists or
    there is no shared vTPM.

    Returns:
        True if a template exists afterwards.
    """
    template = _tpm_template(vm_id)
    TPM_TEMPLATE_DIR.mkdir(parents=True, exist_ok=True)
    with exclusive_lock(TPM_TEMPLATE_DIR / f'{vm_id}.lock'):
        if (template / _TPM_STATE_FILE).exists():
            return True
        legacy = _legacy_tpm_dir(vm_id)
        if not (legacy / _TPM_STATE_FILE).exists():
            return False
        log.info(f"Adopting the shared vTPM of VM {vm_id} as its template")
        staging = template.with_name('tpm2.partial')
        shutil.rmtree(staging, ignore_errors=True)
        _copy_tpm_state(legacy, staging)
        os.replace(staging, template)
        return True


def ensure_tpm_template(vm_id: str) -> Path:
    """The environment's vTPM template (``.../tpm2`` directory), created on first use.

    An environment that already ran with the old shared vTPM keeps that TPM's
    identity (see :func:`adopt_legacy_tpm`). Otherwise a TPM is manufactured once
    with ``swtpm_setup`` (EK + certificates, as libvirt does).
    """
    template = _tpm_template(vm_id)
    if adopt_legacy_tpm(vm_id):
        return template
    with exclusive_lock(TPM_TEMPLATE_DIR / f'{vm_id}.lock'):
        if (template / _TPM_STATE_FILE).exists():
            return template
        log.info(f"Manufacturing vTPM template for VM {vm_id}")
        staging = template.with_name('tpm2.partial')
        shutil.rmtree(staging, ignore_errors=True)
        staging.mkdir(parents=True)
        result = subprocess.run(
            [
                'swtpm_setup',
                '--tpm2',
                '--tpmstate',
                str(staging),
                '--createek',
                '--create-ek-cert',
                '--create-platform-cert',
                '--lock-nvram',
                '--overwrite',
            ],
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode != 0:
            shutil.rmtree(staging, ignore_errors=True)
            raise HypervisorException(f"swtpm_setup failed: {(result.stderr or result.stdout).strip()}")
        os.replace(staging, template)
    return template


def seed_run_tpm(vm_id: str, domain_uuid: str) -> None:
    """Give a run domain its own copy of the environment's vTPM template."""
    template = ensure_tpm_template(vm_id)
    run_state = swtpm_state_root() / domain_uuid / 'tpm2'
    shutil.rmtree(run_state.parent, ignore_errors=True)
    _copy_tpm_state(template, run_state)
    log.debug(f"Seeded run vTPM {run_state} from {template}")


def _copy_tpm_state(source: Path, dest: Path) -> None:
    # The .lock file belongs to a (possibly running) swtpm process, not to the state.
    shutil.copytree(source, dest, ignore=shutil.ignore_patterns('.lock'))


# ---------------------------------------------------------------------------
# Removal
# ---------------------------------------------------------------------------


def remove_vm_templates(vm_id: str, vm_hash: str) -> None:
    """Delete what runs of a deleted VM shared: its qcow2 conversion and its vTPM template."""
    converted = TEMPLATE_DISK_DIR / f'{vm_hash[:16]}.qcow2'
    converted.unlink(missing_ok=True)
    shutil.rmtree(TPM_TEMPLATE_DIR / vm_id, ignore_errors=True)


def run_domain_uuid(instance_name: str) -> str | None:
    """Domain UUID recorded in a run's config, if the config still exists."""
    config_path = get_qemu_vm_config_dir() / f'{instance_name}.json'
    try:
        value = json.loads(config_path.read_text()).get('uuid')
    except (OSError, ValueError):
        return None
    return value if isinstance(value, str) else None


def remove_run_files(instance_name: str) -> list[Path]:
    """Delete every file a run created: overlays (+ checkpoint dirs), UEFI vars, config, sockets, vTPM copy.

    Never touches a template: only names derived from ``instance_name`` (and the
    run's own domain UUID) are removed.

    Returns:
        The paths that were removed.
    """
    removed: list[Path] = []
    domain_uuid = run_domain_uuid(instance_name)
    disk_dir = get_qemu_disk_dir()
    runtime_dir = get_qemu_runtime_dir()
    candidates: list[Path] = [
        *disk_dir.glob(f'{instance_name}-overlay-*.qcow2'),
        disk_dir / f'{instance_name}-nvram.fd',
        get_qemu_vm_config_dir() / f'{instance_name}.json',
        *(runtime_dir / f'{instance_name}{suffix}' for suffix in ('.qmp', '.qga', '.pid')),
    ]
    for path in candidates:
        try:
            path.unlink()
            removed.append(path)
        except FileNotFoundError:
            continue
        except OSError as e:
            log.warning(f"Could not remove run file {path}: {e}")
    # Dev-mode checkpoints live in a directory named after the overlay.
    for checkpoint_dir in disk_dir.glob(f'{instance_name}-overlay-*'):
        if checkpoint_dir.is_dir():
            shutil.rmtree(checkpoint_dir, ignore_errors=True)
            removed.append(checkpoint_dir)
    if domain_uuid:
        tpm_dir = swtpm_state_root() / domain_uuid
        if tpm_dir.is_dir():
            shutil.rmtree(tpm_dir, ignore_errors=True)
            removed.append(tpm_dir)
    if removed:
        log.info(f"Removed {len(removed)} run file(s) of {instance_name}")
    return removed


@contextmanager
def _libvirt_connection() -> Iterator[tuple[Any, Any] | None]:
    """``(libvirt module, open connection)``, or None without libvirt-python or libvirtd.

    libvirt's own error chatter goes to the experiment log, never the console.
    The connection is closed on exit.
    """
    try:
        import libvirt
    except ImportError:
        yield None
        return
    from adare.config import HYPERVISOR_CONFIGS
    from adare.hypervisor.qemu.libvirt_stderr_redirect import LibvirtStderrRedirect, get_experiment_log_file

    uri = HYPERVISOR_CONFIGS.get('qemu', {}).get('libvirt_uri', 'qemu:///session')
    redirect = LibvirtStderrRedirect(log_file=get_experiment_log_file(), suppress_console=True)
    try:
        with redirect:
            conn = libvirt.open(uri)
    except libvirt.libvirtError as e:
        log.debug(f"No libvirt connection ({uri}): {e}")
        conn = None
    if conn is None:
        yield None
        return
    try:
        with redirect:
            yield libvirt, conn
    finally:
        with suppress(libvirt.libvirtError):
            conn.close()


def destroy_run_domain(instance_name: str | None) -> bool:
    """Force-stop and undefine a run's libvirt domain, deleting its varstore and vTPM.

    Best-effort and silent about a domain that does not exist, an unreachable
    libvirtd or a missing libvirt-python, so it is safe from a signal handler
    (``destroy()``, not ``shutdown()``: the run's overlay is discarded anyway).

    Returns:
        True if a running domain was destroyed.
    """
    if not instance_name:
        return False
    from adare.hypervisor.qemu.libvirt_undefine import delete_firmware_state_flags, undefine

    with _libvirt_connection() as session:
        if session is None:
            return False
        libvirt, conn = session
        destroyed = False
        try:
            domain = conn.lookupByName(instance_name)
            if domain.isActive():
                domain.destroy()
                destroyed = True
            undefine(domain, delete_firmware_state_flags())
            log.info(f"Removed libvirt domain {instance_name}")
        except libvirt.libvirtError as e:
            if e.get_error_code() != libvirt.VIR_ERR_NO_DOMAIN:
                log.warning(f"Could not remove libvirt domain {instance_name}: {e}")
        return destroyed


def is_domain_running(instance_name: str) -> bool:
    """True if a libvirt domain of this name is currently running."""
    with _libvirt_connection() as session:
        if session is None:
            return False
        libvirt, conn = session
        try:
            return bool(conn.lookupByName(instance_name).isActive())
        except libvirt.libvirtError:
            return False
