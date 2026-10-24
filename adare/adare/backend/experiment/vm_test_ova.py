"""`adare vm test` for a VirtualBox OVA/OVF file.

Imports the file as a VirtualBox VM, shares the installed adarevm source with it,
starts adarevm from that source and checks it answers. Registered QEMU VMs are
tested the way experiments run instead (:mod:`~adare.backend.experiment.vm_test_qemu`).
"""

import asyncio
import logging
import threading
import time
from dataclasses import dataclass
from pathlib import Path

from adare.backend.experiment.runctx import ExperimentRunCtx
from adare.backend.experiment.vm_test import (
    AGENT_GUI_CHECKS,
    PYTHON,
    UV,
    VM_RESPONSIVE,
    CheckResult,
    CompatCheck,
    CompatRun,
    free_host_port,
    guest_files_exist,
    is_windows,
    start_flow_console,
    stop_flow_console,
)
from adare.exceptions import LoggedException
from adare.types.stages import VMAdareServerTestStage, VMSharedFoldersTestStage, VMWebSocketTestStage

log = logging.getLogger(__name__)

# The share is the host's installed appdata, so whatever the guest agent (root)
# writes there lands on the host and breaks the next `make install`. Keep the venv
# and bytecode in the guest, and --frozen so uv never rewrites the shared uv.lock.
_GUEST_UV_ENV = "export UV_PROJECT_ENVIRONMENT=/var/tmp/adarevm-venv PYTHONDONTWRITEBYTECODE=1; "


@dataclass
class OvaTestCtx(ExperimentRunCtx):
    """Run context of an OVA test: an experiment context plus the file under test."""

    ova_file_path: Path | None = None


def create_ova_test_context(ova_file_path: Path, guest_platform: str) -> OvaTestCtx:
    """Create minimal context for OVA testing."""
    import ulid

    from adare.backend.experiment.runctx import ExperimentConfig
    from adare.config.configdirectory import ADAREVM_DIR

    config = ExperimentConfig(
        project_path=Path("/tmp"),  # Dummy path
        experiment_name="ova_test",
        environment_name="ova_test_env",
        test_mode=True,
        preserve_snapshot=False,
        vm_cpus=2,
        vm_memory=2048,
        websocket_port=free_host_port(),  # outside the experiment pool; free so concurrent tests don't collide
        vm_resolution=(1920, 1080),
    )
    context = OvaTestCtx(config=config, ova_file_path=ova_file_path)
    context.vm_name = f"adare_ova_test_{int(time.time())}"
    context.experiment_run_ulid = str(ulid.ULID())
    context.guest_platform = guest_platform
    context.adarevm = ADAREVM_DIR
    context.vm = None
    context.client = None
    return context


# VM setup steps
async def import_ova_for_test(context):
    """Import OVA file directly for testing."""
    log.info("Phase 1 - Importing OVA file...")

    from adare.config import SHARE_POINT_VM, get_vm_credentials
    from adare.hypervisor.virtualbox.manager import VirtualBoxManager
    from adare.hypervisor.virtualbox.vm import VirtualBoxVM

    username, password = get_vm_credentials(context.guest_platform)
    context.vm = VirtualBoxVM(
        vm_name=context.vm_name,
        guest_os=context.guest_platform,
        manager=VirtualBoxManager(),
        username=username,
        password=password,
        cpus=context.config.vm_cpus,
        ram=context.config.vm_memory,
    )
    # Same pattern as the VM database import
    await context.vm.create_from_ovf_or_ova(
        file_path=context.ova_file_path, silent=True, stop_event=context.user_interrupt_event
    )
    context.config.shared_directories = {'app': {'host': str(context.adarevm), 'guest': SHARE_POINT_VM}}
    log.info("OVA imported successfully")


async def setup_shared_folders_for_test(context):
    """Setup shared folders in VirtualBox for testing."""
    log.info("Setting up shared folders...")
    for name, paths in context.config.shared_directories.items():
        await context.vm.add_shared_folder(name, host_path=paths['host'], stop_event=context.user_interrupt_event)
    log.info("Shared folders configured in VirtualBox")


async def start_test_vm(context):
    """Start the test VM."""
    log.info("Starting test VM...")
    await context.vm.start(stop_event=context.user_interrupt_event)
    log.info("Test VM started")


async def wait_for_test_vm_ready(context):
    """Wait for test VM to be ready."""
    log.info("Waiting for test VM to be ready...")
    await context.vm.wait_until_ready(stop_event=context.user_interrupt_event)
    log.info("Test VM is ready")


async def mount_shared_directories_in_test_vm(context):
    """Mount shared directories in test VM."""
    log.info("Mounting shared directories in test VM...")
    await context.vm.mount_shared_directories(stop_event=context.user_interrupt_event)
    log.info("Shared directories mounted in test VM")


# Checks
async def check_source_share(context, stage) -> CheckResult:
    """The adarevm source is shared at /adare/vm."""
    return await guest_files_exist(context, ['vm/pyproject.toml'])


async def check_source_agent_start(context, stage) -> CheckResult:
    """adarevm starts from the shared source (its ``adarevm.main:run`` entry point, via uv)."""
    try:
        if is_windows(context):
            return await _start_source_agent_windows(context)
        return await _start_source_agent_linux(context)
    except (OSError, ConnectionError, TimeoutError, RuntimeError) as e:
        log.warning(f"Exception starting adarevm server: {e}")
        return False, f"Exception starting adarevm server: {e}"


async def _start_source_agent_windows(context) -> CheckResult:
    # A user-session scheduled task (run_as_user): the later screenshot/click checks
    # need the GUI session. The task runner returns once port 18765 is LISTENING.
    log_path = r'C:\Windows\Temp'
    # Double quotes only: run_as_user embeds the command in a single-quoted string.
    command = (
        f'$env:UV_PROJECT_ENVIRONMENT = "{log_path}\\adarevm-venv"; $env:PYTHONDONTWRITEBYTECODE = "1"; '
        'uv run --frozen --package adarevm adarevm'
    )
    result = await context.vm.run_command(
        command,
        cwd=r'C:\adare\vm',  # editable source: the project root with pyproject.toml
        admin=True,
        run_as_user=True,
        stop_event=context.user_interrupt_event,
        redirect_stdout=rf'{log_path}\adarevm_stdout.log',
        redirect_stderr=rf'{log_path}\adarevm_stderr.log',
    )
    if result.returncode == 0:
        log.info("AdareVM server started successfully (port 18765 listening)")
        return True, None
    reason = f"Failed to start adarevm server. Exit code: {result.returncode}. stderr: {result.stderr}"
    log.warning(reason)
    return False, reason


async def _start_source_agent_linux(context) -> CheckResult:
    from adare.backend.experiment.agent_readiness import wait_for_agent

    # cd into the adarevm member so uv resolves its `adarelib = { workspace = true }`
    # dependency. Pre-sync the venv (the slow build), grant the guest agent (root)
    # the autologin user's X display (DISPLAY/XAUTHORITY + `xhost +SI:localuser:root`),
    # then start adarevm. The guest agent waits for the command's output pipe, so the
    # job is `cmd &`, not `cd X && cmd &`, whose subshell holds that pipe open.
    stop = context.user_interrupt_event
    log.info("Pre-syncing adarevm venv in guest (builds deps)...")
    await context.vm.run_command(
        f"{_GUEST_UV_ENV}cd /adare/vm/adarevm && uv sync --frozen 2>&1 | tail -3", stop_event=stop
    )
    start_command = (
        _GUEST_UV_ENV + "export DISPLAY=:0; "
        "export XAUTHORITY=$(ls /run/user/*/gdm/Xauthority /run/user/*/.mutter-Xwaylandauth.* "
        "/run/sddm/* /run/user/*/xauth_* /home/adare/.Xauthority 2>/dev/null | head -1); "
        "xhost +SI:localuser:root >/dev/null 2>&1 || true; "
        "cd /adare/vm/adarevm || exit 1; nohup uv run --frozen adarevm >/tmp/adarevm.log 2>&1 </dev/null &"
    )
    result = await context.vm.run_command(start_command, stop_event=stop)
    if result.returncode != 0:
        reason = f"Failed to start adarevm server. Exit code: {result.returncode}"
        log.warning(reason)
        return False, reason
    log.info("AdareVM server launched; waiting for it to answer")
    await wait_for_agent(context.config.websocket_port, stop_event=stop)
    return True, None


async def check_source_agent_connection(context, stage) -> CheckResult:
    """The started adarevm accepts a WebSocket connection."""
    from adare.backend.experiment.websocket_client import AdareVMClient

    context.client = AdareVMClient(port=context.config.websocket_port)
    try:
        connected = await context.client.connect(timeout=30.0)
    except (OSError, ConnectionError, TimeoutError, RuntimeError) as e:
        log.warning(f"WebSocket test error: {e}")
        return False, f"WebSocket test error: {e}"
    if connected:
        log.info("WebSocket connection established")
        return True, None
    log.warning("Could not establish WebSocket connection")
    return False, "Could not establish WebSocket connection"


OVA_CHECKS = (
    VM_RESPONSIVE,
    CompatCheck('shared_folders_working', VMSharedFoldersTestStage, check_source_share),
    PYTHON,
    UV,
    CompatCheck('adarevm_server_starts', VMAdareServerTestStage, check_source_agent_start),
    CompatCheck('websocket_connection', VMWebSocketTestStage, check_source_agent_connection),
)
# VirtualBox has no QMP, so the in-guest agent path is the whole test: of the 8
# checks, the VM basics, server, connection and at least one GUI command
_MIN_PASSED = 6


async def check_ova_compatibility(compat: CompatRun) -> bool:
    """Run the OVA checks (the agent's GUI commands only once connected) and decide the verdict."""
    log.info("Testing VM compatibility with ADARE WebSocket server...")
    try:
        await compat.run(OVA_CHECKS)
        if compat.results['websocket_connection']:
            await compat.run(AGENT_GUI_CHECKS)
    except (OSError, ConnectionError, TimeoutError, RuntimeError) as e:
        log.error(f"Compatibility test error: {e}")

    compat.log_results()
    passed = sum(compat.results.values())
    if passed >= _MIN_PASSED:
        log.info("VM appears compatible with ADARE (WebSocket server working)")
        return True
    log.warning(f"VM compatibility insufficient: only {passed}/{len(OVA_CHECKS) + len(AGENT_GUI_CHECKS)} tests passed")
    return False


async def cleanup_test_vm(context, keep_vm: bool = False):
    """Clean up test VM and resources."""
    log.info("Cleaning up test resources...")
    try:
        # Disconnect WebSocket client (adarevm server stops automatically when VM stops)
        if context.client:
            await context.client.disconnect()
            log.info("WebSocket client disconnected")
        if context.vm:
            if keep_vm:
                await context.vm.stop()
                log.info("Test VM stopped but kept for manual inspection")
                log.info("You can manually remove it later with: VBoxManage unregistervm --delete")
            else:
                await context.vm.remove()
                log.info("Test VM removed successfully")
    except (OSError, ConnectionError, TimeoutError, RuntimeError) as e:
        # Cleanup must not crash -- log and continue
        log.error(f"Error during cleanup: {e}")
    log.info("Cleanup completed")


async def ova_test(
    ova_file_path: Path, guest_platform: str, verbose: bool = False, vm_cleanup_mode: str = 'prompt'
) -> bool:
    """
    Test OVA file compatibility with ADARE using separate workflow that reuses existing steps.

    Args:
        ova_file_path: Path to the .ova file to test
        guest_platform: Platform type ('windows' or 'linux') - required
        verbose: Enable verbose logging
        vm_cleanup_mode: 'keep' stops but keeps the imported VM; otherwise it is removed

    Returns:
        True if VM is compatible with ADARE, False otherwise
    """
    from adare.backend.experiment.commands.manage import StageCtxManagerLite
    from adare.backend.experiment.step_runner import ExperimentStepRunner
    from adare.types.stages import VMCompatibilityTestStage, VMTestCleanupStage, VMTestSetupStage

    if not ova_file_path.exists():
        raise LoggedException(log, f"OVA file not found: {ova_file_path}")
    if guest_platform not in ['linux', 'windows']:
        raise LoggedException(log, f"Invalid platform '{guest_platform}'. Must be 'linux' or 'windows'")

    start_time = time.time()
    log.info(f"ova_test function started - Testing OVA file: {ova_file_path}")
    log.info(f"Platform: {guest_platform}")

    user_interrupt_event = threading.Event()
    flow_console = start_flow_console(f"VM Test: {ova_file_path.name}", user_interrupt_event)
    context = create_ova_test_context(ova_file_path, guest_platform)
    context.user_interrupt_event = user_interrupt_event
    compat = CompatRun(context, flow_console)

    stop_event = asyncio.Event()  # the step runner's; the context keeps its own threading.Event
    step_runner = ExperimentStepRunner(stop_event, user_interrupt_event)

    try:
        if not stop_event.is_set():
            log.info("Starting VM Test Setup Phase...")
            async with StageCtxManagerLite(VMTestSetupStage(), flow_console, level=1):
                for setup_step in (
                    import_ova_for_test,
                    setup_shared_folders_for_test,
                    start_test_vm,
                    wait_for_test_vm_ready,
                    mount_shared_directories_in_test_vm,
                ):
                    await step_runner.run_async_step(setup_step, context)

        compatible = False
        if not stop_event.is_set():
            async with StageCtxManagerLite(VMCompatibilityTestStage(), flow_console, level=1):
                compatible = await step_runner.run_async_step(lambda _: check_ova_compatibility(compat), context)

        if not compatible:
            log.error("VM compatibility tests failed - VM may not be fully compatible with ADARE")
            flow_console.finish_experiment_timer(success=False)
            return False

        elapsed_time = time.time() - start_time
        log.info(f"OVA test completed successfully! File is compatible with ADARE. (took {elapsed_time:.1f} seconds)")
        flow_console.finish_experiment_timer(success=True)
        return True

    except (OSError, ConnectionError, TimeoutError, RuntimeError, ValueError) as e:
        log.error(f"OVA test failed with unexpected error: {e}")
        # Always show traceback for debugging VM test failures
        import traceback

        traceback.print_exc()
        flow_console.finish_experiment_timer(success=False)
        return False
    finally:
        try:
            async with StageCtxManagerLite(VMTestCleanupStage(), flow_console, level=1):
                keep_vm = vm_cleanup_mode == 'keep'
                if context.vm:
                    log.info(
                        "Keeping VM for further testing (--keep-vm specified)"
                        if keep_vm
                        else "Removing VM automatically (default behavior)"
                    )
                await cleanup_test_vm(context, keep_vm=keep_vm)
        except (OSError, ConnectionError, TimeoutError, RuntimeError) as cleanup_error:
            # Cleanup in finally must not mask the original error
            log.error(f"Error during cleanup: {cleanup_error}")
        stop_flow_console(flow_console, compat)
