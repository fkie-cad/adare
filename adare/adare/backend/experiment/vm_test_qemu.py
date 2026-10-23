"""Setting up and tearing down the QEMU VM that `adare vm test` boots for a registered VM.

The test VM is a throwaway run on the registered disk: an overlay on its
read-only template, torn down afterwards like an experiment run's (see
:mod:`adare.hypervisor.qemu.run_resources`). The test steps themselves live in
:mod:`adare.backend.experiment.vm_test`.
"""

import asyncio
import logging
import time
from pathlib import Path

from adare.exceptions import LoggedException
from adare.hypervisor.exceptions import HypervisorException

log = logging.getLogger(__name__)


def _free_host_port() -> int:
    """A currently free TCP port on the forward bind address, chosen by the OS."""
    import socket

    from adare.hypervisor.port_forward import forward_bind_host

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind((forward_bind_host(), 0))
        port: int = sock.getsockname()[1]
        return port


def create_registered_test_context(vm_name: str, disk_path: str, guest_platform: str, architecture: str):
    """Create minimal context for testing a registered QEMU VM.

    Mirrors create_ova_test_context but targets QEMU: it sets hypervisor_type
    so connect_websocket / cleanup branch correctly, records the guest
    architecture for machine/accel selection, and stores the base disk path.

    Args:
        vm_name: Registered VM name (used only for logging / display)
        disk_path: Path to the VM's immutable base disk (vm.file)
        guest_platform: 'linux' or 'windows'
        architecture: Guest CPU architecture (e.g. 'x86_64' or 'aarch64')
    """
    import ulid

    from adare.backend.experiment.runctx import ExperimentConfig, ExperimentRunCtx
    from adare.config.configdirectory import ADAREVM_DIR

    # Minimal config for testing. websocket_port is a free HOST port;
    # setup_networking forwards it to the in-guest 18765.
    config = ExperimentConfig(
        project_path=Path("/tmp"),  # Dummy path
        experiment_name="qemu_vm_test",
        environment_name="qemu_vm_test_env",
        test_mode=True,
        preserve_snapshot=False,
        vm_cpus=2,
        vm_memory=2048,
        websocket_port=_free_host_port(),  # outside the experiment pool; free so concurrent tests don't collide
        vm_resolution=(1920, 1080),
    )

    context = ExperimentRunCtx(config=config)
    context.vm_name = f"adare_qemu_test_{int(time.time())}"
    context.experiment_run_ulid = str(ulid.ULID())
    context.guest_platform = guest_platform
    context.guest_architecture = architecture
    context.hypervisor_type = 'qemu'  # CRITICAL: connect_websocket + cleanup branch on this
    context.adarevm = ADAREVM_DIR
    context.vm = None
    context.client = None

    # Store immutable base disk path for overlay creation
    context._registered_disk_path = disk_path
    context._registered_vm_name = vm_name

    return context


async def create_qemu_vm_for_test(context):
    """Build a QEMUVM for the test and back it with an overlay disk.

    Mirrors QEMULifecycleStrategy.prepare_vm_for_experiment (arch/machine/accel
    selection via the shared resolve_accel chokepoint) but without any
    DB/environment lookups. The base disk stays immutable: all writes go to
    the experiment overlay.
    """
    from adare.config import get_vm_credentials
    from adare.hypervisor.qemu.accel import resolve_accel
    from adare.hypervisor.qemu.manager import QEMUManager
    from adare.hypervisor.qemu.vm import QEMUVM

    log.info("Phase 1 - Preparing QEMU VM for test...")

    vm_architecture = context.guest_architecture or 'x86_64'
    allow_emulation = getattr(context.config, 'allow_emulation', False)
    vm_accel = resolve_accel(vm_architecture, allow_emulation)
    vm_machine = 'virt' if vm_architecture == 'aarch64' else 'pc'

    qemu_manager = QEMUManager()
    username, password = get_vm_credentials(context.guest_platform)

    # Overlays need a qcow2 backing file: a non-qcow2 disk is converted once
    # into a managed template (see run_resources.resolve_template_disk).
    from adare.database.api.vm import VmApi
    from adare.hypervisor.qemu.run_resources import resolve_template_disk

    registered_disk = Path(context._registered_disk_path)
    with VmApi() as vm_api:
        registered_vm = vm_api.get_vm_by_name(context._registered_vm_name)
    if registered_vm is None:
        raise LoggedException(log, f"VM '{context._registered_vm_name}' is not registered")
    template_disk = resolve_template_disk(registered_disk, str(registered_vm.hash), qemu_manager.executables.qemu_img)

    # Pass the template path explicitly so QEMUVM treats it as the (external)
    # base and does not derive a managed path from the synthetic test vm_name.
    context.vm = QEMUVM(
        vm_name=context.vm_name,
        guest_os=context.guest_platform,
        manager=qemu_manager,
        username=username,
        password=password,
        executables=qemu_manager.executables,
        cpus=context.config.vm_cpus,
        ram=context.config.vm_memory,
        machine=vm_machine,
        accel=vm_accel,
        disk_path=str(template_disk),
        architecture=vm_architecture,
    )
    log.debug(f"Created QEMU VM instance for test: {context.vm_name}")

    # Create experiment overlay backed by the immutable base disk and point the
    # VM at the overlay so all disk writes stay off the base (forensic integrity).
    overlay_path = await context.vm.create_overlay_disk(context.experiment_run_ulid)
    context.vm.config.disk_path = overlay_path
    context.vm._save_vm_config()
    log.info(f"Using overlay disk for test (base preserved): {overlay_path}")


async def setup_qemu_networking_for_test(context):
    """Set up host->guest port forwarding for the WebSocket server."""
    from adare.hypervisor.qemu.lifecycle import QEMULifecycleStrategy

    log.info("Setting up QEMU port forwarding...")
    await QEMULifecycleStrategy().setup_networking(context)


async def setup_qemu_share_for_test(context):
    """Make the adarevm source available in the guest at /adare/vm.

    Bypasses the project-coupled build_share_list: the compat test only needs
    the adarevm source at /adare/vm so the guest can start the server.

    The mechanism follows the file-transfer strategy the QEMU lifecycle would
    resolve on this host (``detect_file_transfer_mode``), because
    ``start_qemu_test_vm`` delegates post-boot mounting to that same resolved
    strategy:

    - ``virtiofs`` (Linux, virtiofsd present): configure a single virtio-fs
      share; VirtioFSStrategy mounts it post-boot.
    - ``smb`` (macOS with smbd): stage the adarevm source in a temp directory
      served via QEMU SLIRP SMB (``smb_share_path``); SMBStrategy.post_boot_transfer
      mounts ``//10.0.2.4/qemu`` and junctions ``vm`` to ``C:\\adare\\vm`` (or
      mounts it at ``/adare`` on Linux). No strategy-instance state is needed.

    Other modes (qga, libguestfs) are not wired for the DB-free compat test.
    """
    from adare.config.configdirectory import ADARE_DIR
    from adare.hypervisor.qemu.file_transfer import detect_file_transfer_mode

    is_windows = 'windows' in context.guest_platform.lower()
    base_mount = 'C:\\adare' if is_windows else '/adare'
    guest_mount = f'{base_mount}\\vm' if is_windows else f'{base_mount}/vm'

    # Share the uv WORKSPACE ROOT (adare/adarevm/adarelib/adare-cv-server), not
    # just the adarevm subdir: `uv run --package adarevm adarevm` needs the
    # workspace so it can resolve adarevm's `adarelib = { workspace = true }`
    # dependency. The share is writable so uv can create its .venv in-tree.
    share_root = ADARE_DIR

    mode = detect_file_transfer_mode()
    log.info(f"Configuring test file share for adarevm ({mode} mode)...")

    if mode == 'virtiofs':
        shares = [
            {
                'tag': 'vm',
                'host_path': str(share_root),
                'guest_mount': guest_mount,
                'readonly': False,
            }
        ]

        context.vm.config.virtiofs_enabled = True
        context.vm.config.virtiofs_shares = shares
        context.vm._save_vm_config()

        # Also expose on context for post-boot mounting (mirrors virtiofs strategy)
        context.virtiofs_shares = shares

        log.info(f"Configured virtio-fs share: {share_root} -> {guest_mount}")
        return

    if mode == 'smb':
        import shutil
        import tempfile
        from pathlib import Path

        # SMBStrategy.post_boot_transfer creates one junction per top-level
        # directory in the share, so stage adarevm under a 'vm' subdir; it
        # becomes //10.0.2.4/qemu/vm -> C:\adare\vm (or /adare/vm on Linux).
        smb_dir = Path(tempfile.mkdtemp(prefix='adare_smb_test_'))
        shutil.copytree(
            str(share_root),
            str(smb_dir / 'vm'),
            dirs_exist_ok=True,
            ignore=shutil.ignore_patterns('.venv', '.git', '__pycache__'),
        )

        context.vm.config.smb_share_path = str(smb_dir)
        context.vm.config.virtiofs_enabled = False
        context.vm.config.virtiofs_shares = []
        context.vm._save_vm_config()

        # Track for teardown (SMBStrategy's own cleanup never runs for the test,
        # since setup() was bypassed and post_boot uses a fresh strategy instance)
        context._test_smb_dir = str(smb_dir)

        log.info(f"Configured QEMU SLIRP SMB share: {share_root} -> {smb_dir / 'vm'} -> {guest_mount}")
        return

    raise HypervisorException(
        f"vm test does not support '{mode}' file transfer mode. The compat "
        f"test needs adarevm at {guest_mount}, which requires virtiofsd (Linux) "
        f"or smbd for QEMU SLIRP SMB (macOS: brew install samba and symlink it "
        f"to QEMU's compiled-in smbd path). See earlier logs for the exact "
        f"symlink command."
    )


async def start_qemu_test_vm(context):
    """Start the QEMU test VM and mount shares via the lifecycle strategy.

    Uses QEMULifecycleStrategy.start_and_initialize_vm which tolerates
    context.playbook being None and performs post-boot virtio-fs mounting.
    """
    from adare.hypervisor.qemu.lifecycle import QEMULifecycleStrategy

    log.info("Starting QEMU test VM...")
    await QEMULifecycleStrategy().start_and_initialize_vm(context, rerun_file_transfer_on_retry=False)
    log.info("QEMU test VM started and ready")


class _CleanupFailed(Exception):
    """Sentinel: cleanup completed but one or more best-effort steps failed.

    Raised from _cleanup_registered_test_vm so StageCtxManagerLite.__aexit__
    marks the cleanup stage FAILED; caught at the call site so it does NOT
    propagate out of the finally block and does NOT flip the compatibility
    verdict.
    """

    def __init__(self, errors: list[str]):
        super().__init__("; ".join(errors))
        self.errors = errors


async def _cleanup_registered_test_vm(context, keep_vm: bool = False, flow_console=None, stage_id: str | None = None):
    """Stop the test VM and remove its libvirt domain and run files.

    The test VM has no VmInstance row, so this is the file/domain half of an
    experiment run's teardown. The read-only template disk is left untouched.
    """

    def _update_message(message: str) -> None:
        if flow_console is not None and stage_id is not None:
            try:
                flow_console.change_log_message(stage_id, message)
            except (AttributeError, KeyError, RuntimeError):
                pass

    # Each best-effort step records its failure here; if non-empty at the end
    # we raise _CleanupFailed so the stage finalizes as ✖, but the per-step
    # ✖ children (rendered via _surface_error) are what the reader actually sees.
    cleanup_errors: list[str] = []

    def _surface_error(step_key: str, label: str, err: BaseException) -> None:
        cleanup_errors.append(f"{label}: {err}")
        if flow_console is not None and stage_id is not None:
            try:
                flow_console.log_failed(f"{stage_id}:err:{step_key}", f"{label} failed: {err}", level=2)
            except (AttributeError, KeyError, RuntimeError):
                pass
        # File log only (the flow console suppresses console logging to
        # CRITICAL while active); the flow ✖ child line above is the
        # user-facing surface.
        log.warning(f"{label} failed: {err}")

    log.info("Cleaning up QEMU test resources...")

    # Every step is best-effort: a failure is surfaced to the flow console and
    # the remaining steps still run.
    _update_message("Disconnecting WebSocket…")
    try:
        if context.client:
            await asyncio.wait_for(context.client.disconnect(), timeout=10)
            log.info("WebSocket client disconnected")
    except TimeoutError as e:
        _surface_error("disconnect", "Disconnecting WebSocket", e)

    if not context.vm:
        if cleanup_errors:
            raise _CleanupFailed(cleanup_errors)
        return

    # Hard poweroff: the overlay is discarded, so no graceful ACPI shutdown.
    _update_message("Stopping VM…")
    try:
        await context.vm.stop(force=True)
        log.info("Test VM stopped")
    except (HypervisorException, OSError, RuntimeError) as e:
        _surface_error("stop", "Stopping VM", e)

    if keep_vm:
        log.info("Keeping overlay and libvirt domain (--keep-vm specified)")
        # Earlier steps (disconnect/stop) may have failed; surface them even
        # when --keep-vm short-circuits the remaining teardown.
        if cleanup_errors:
            raise _CleanupFailed(cleanup_errors)
        return

    # Like an experiment run's teardown: the domain (with its varstore and vTPM
    # copy), then every file keyed by the run's name -- overlay included. The
    # read-only template is never touched.
    _update_message("Removing test VM…")
    from adare.hypervisor.qemu.run_resources import destroy_run_domain, remove_run_files

    context.vm._libvirt_domain = None  # stale once the domain is undefined
    destroy_run_domain(context.vm.vm_name)
    remove_run_files(context.vm.vm_name)

    # Remove the temporary SMB share directory staged for the test (if any)
    _update_message("Removing temp SMB share…")
    smb_dir = getattr(context, '_test_smb_dir', None)
    if smb_dir:
        import shutil

        shutil.rmtree(smb_dir, ignore_errors=True)
        log.debug(f"Removed test SMB share directory: {smb_dir}")

    if cleanup_errors:
        log.warning(f"VM test cleanup completed with {len(cleanup_errors)} error(s)")
        raise _CleanupFailed(cleanup_errors)
    log.info("Cleanup completed")
