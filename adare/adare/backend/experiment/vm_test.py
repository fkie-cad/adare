"""
VM Testing module for ADARE - handles OVA compatibility testing.

This module contains functions for testing VM compatibility with ADARE,
including setup, WebSocket server testing, and cleanup operations.
"""

import asyncio
import logging
import threading
import time
from pathlib import Path

from adare.exceptions import LoggedException

log = logging.getLogger(__name__)


def create_ova_test_context(ova_file_path: Path, guest_platform: str):
    """Create minimal context for OVA testing."""
    import ulid

    from adare.backend.experiment.runctx import ExperimentConfig, ExperimentRunCtx
    from adare.config.configdirectory import ADAREVM_DIR

    # Create minimal config for testing
    config = ExperimentConfig(
        project_path=Path("/tmp"),  # Dummy path
        experiment_name="ova_test",
        environment_name="ova_test_env",
        test_mode=True,
        preserve_snapshot=False,
        vm_cpus=2,
        vm_memory=2048,
        websocket_port=19000,  # Test port outside production range
        vm_resolution=(1920, 1080)
    )

    # Create context with minimal required fields
    context = ExperimentRunCtx(config=config)
    context.vm_name = f"adare_ova_test_{int(time.time())}"
    context.experiment_run_ulid = str(ulid.ULID())
    context.guest_platform = guest_platform
    context.adarevm = ADAREVM_DIR
    context.vm = None
    context.client = None

    # Store OVA file path for import
    context._ova_file_path = ova_file_path

    return context


# VM Setup Functions
async def import_ova_for_test(context):
    """Import OVA file directly for testing."""
    log.info("Phase 1 - Importing OVA file...")

    from adare.config import get_vm_credentials
    from adare.hypervisor.virtualbox.manager import VirtualBoxManager
    from adare.hypervisor.virtualbox.vm import VirtualBoxVM

    # Get credentials for guest platform
    username, password = get_vm_credentials(context.guest_platform)

    # Create VM instance
    vbox_manager = VirtualBoxManager()
    context.vm = VirtualBoxVM(
        vm_name=context.vm_name,
        guest_os=context.guest_platform,
        manager=vbox_manager,
        username=username,
        password=password,
        cpus=context.config.vm_cpus,
        ram=context.config.vm_memory
    )

    # Import OVA file (using same pattern as working vm database import)
    await context.vm.create_from_ovf_or_ova(
        file_path=context._ova_file_path,
        silent=True,
        stop_event=context.user_interrupt_event
    )

    # Setup minimal shared directories configuration for testing
    from adare.config import SHARE_POINT_VM
    context.config.shared_directories = {
        'app': {
            'host': str(context.adarevm),
            'guest': SHARE_POINT_VM
        }
    }

    log.info("OVA imported successfully")


async def setup_shared_folders_for_test(context):
    """Setup shared folders in VirtualBox for testing."""
    log.info("Setting up shared folders...")

    # Add shared folders to VirtualBox (similar to VM lifecycle manager)
    for name, paths in context.config.shared_directories.items():
        await context.vm.add_shared_folder(name, host_path=paths['host'], stop_event=context.user_interrupt_event)

    log.info("Shared folders configured in VirtualBox")


async def start_test_vm(context):
    """Start the test VM."""
    log.info("Starting test VM...")

    # Start VM using same approach as VMLifecycleManager
    await context.vm.start(stop_event=context.user_interrupt_event)
    log.info("Test VM started")


async def wait_for_test_vm_ready(context):
    """Wait for test VM to be ready."""
    log.info("Waiting for test VM to be ready...")

    # Wait for VM to be responsive using same approach as VMLifecycleManager
    await context.vm.wait_until_ready(stop_event=context.user_interrupt_event)
    log.info("Test VM is ready")


async def mount_shared_directories_in_test_vm(context):
    """Mount shared directories in test VM."""
    log.info("Mounting shared directories in test VM...")

    # Mount shared directories using same approach as VMLifecycleManager
    await context.vm.mount_shared_directories(stop_event=context.user_interrupt_event)
    log.info("Shared directories mounted in test VM")


# VM Compatibility Test Functions
async def test_vm_response(context):
    """Test basic VM responsiveness."""
    test_result = await context.vm.run_command("true", stop_event=context.user_interrupt_event)
    if test_result.returncode == 0:
        log.info("VM is responsive to commands")
        return True
    log.warning(f"VM not responding to commands. Exit code: {test_result.returncode}")
    return False


async def test_shared_folders(context):
    """Test shared folder accessibility."""
    # Check if vm runtime directory is accessible
    ls_result = await context.vm.run_command("test -d /adare/vm", stop_event=context.user_interrupt_event)
    if ls_result.returncode == 0:
        log.info("Shared folders are accessible")
        return True
    log.warning(f"Shared folders not accessible. Exit code: {ls_result.returncode}")
    return False


async def test_python_availability(context):
    """Test Python availability in VM."""
    python_result = await context.vm.run_command("python3 --version", stop_event=context.user_interrupt_event)
    if python_result.returncode == 0:
        log.info("Python is available")
        return True
    log.warning(f"Python not available. Exit code: {python_result.returncode}")
    return False


async def test_uv_availability(context):
    """Test uv availability in VM."""
    uv_result = await context.vm.run_command("uv --version", stop_event=context.user_interrupt_event)
    if uv_result.returncode == 0:
        log.info("uv is available")
        return True
    log.warning(f"uv not available. Exit code: {uv_result.returncode}")
    return False


async def test_adarevm_server_start(context, guest_bind_port: int | None = None):
    """Test starting the adarevm WebSocket server.

    NOTE: This test requires uv-based VMs (does not support wheel-only installations).
    The test uses 'uv run' to start the adarevm server from source.

    Args:
        context: ExperimentRunCtx
        guest_bind_port: In-guest bind port for the adarevm server. When None
            (VirtualBox/OVA loopback) the server binds ``context.config.websocket_port``.
            For QEMU the guest must bind 18765 while the host connects on the
            forwarded ``websocket_port`` -- pass ``guest_bind_port=18765`` there.
    """
    try:
        # Start adarevm server in background
        # NOTE: This requires uv - does not work with wheel-only installations
        bind_port = guest_bind_port if guest_bind_port is not None else context.config.websocket_port
        start_command = f"cd /adare/vm && uv run python -m adarevm.server --port {bind_port} &"

        start_result = await context.vm.run_command(start_command, stop_event=context.user_interrupt_event)

        if start_result.returncode == 0:
            log.info("AdareVM server started successfully")
            # Give server time to initialize
            import asyncio
            await asyncio.sleep(3.0)
            return True
        log.warning(f"Failed to start adarevm server. Exit code: {start_result.returncode}")
        return False

    except (OSError, ConnectionError, TimeoutError, RuntimeError) as e:
        log.warning(f"Exception starting adarevm server: {e}")
        return False


async def test_websocket_connection(context):
    """Test WebSocket connection to AdareVM server."""
    try:
        from adare.backend.experiment.websocket_client import AdareVMClient

        # Create WebSocket client
        client = AdareVMClient(host='localhost', port=context.config.websocket_port)
        context.client = client

        # Try to connect with reasonable timeout
        connected = await client.connect(timeout=30.0)
        if connected:
            log.info("WebSocket connection established")
            return True
        log.warning("Could not establish WebSocket connection")
        return False

    except (OSError, ConnectionError, TimeoutError, RuntimeError) as e:
        log.warning(f"WebSocket test error: {e}")
        return False


async def test_screenshot_command(context):
    """Test screenshot command via WebSocket."""
    try:
        result = await context.client.call_tool("take_screenshot", timeout=10.0)
        if result and not result.get('error'):
            log.info("Screenshot command successful")
            return True
        log.warning(f"Screenshot command failed: {result}")
        return False
    except (OSError, ConnectionError, TimeoutError, RuntimeError) as e:
        log.warning(f"Screenshot command error: {e}")
        return False


async def test_click_command(context):
    """Test click command via WebSocket."""
    try:
        click_x = 10
        click_y = 10

        result = await context.client.call_tool("click", {"x": click_x, "y": click_y}, timeout=10.0)
        if result and not result.get('error'):
            log.info(f"Click command successful (clicked at {click_x}, {click_y})")
            return True
        log.warning(f"Click command failed: {result}")
        return False
    except (OSError, ConnectionError, TimeoutError, RuntimeError) as e:
        log.warning(f"Click command error: {e}")
        return False


async def test_vm_compatibility(context, flow_console, guest_bind_port: int | None = None):
    """Test VM compatibility with ADARE WebSocket server and execute simple experiment commands.

    Args:
        context: ExperimentRunCtx
        flow_console: ExperimentFlowConsole for progress reporting
        guest_bind_port: Optional in-guest bind port for the adarevm server. Threaded
            through to ``test_adarevm_server_start``. None keeps the OVA/VirtualBox
            loopback behavior; QEMU passes 18765 (host connects on the forwarded port).
    """
    from adare.types.stages import (
        VMAdareServerTestStage,
        VMClickTestStage,
        VMPoetryTestStage,
        VMPythonTestStage,
        VMResponseTestStage,
        VMScreenshotTestStage,
        VMSharedFoldersTestStage,
        VMWebSocketTestStage,
    )
    from adare.backend.experiment.commands.manage import StageCtxManagerLite

    log.info("Testing VM compatibility with ADARE WebSocket server...")

    compatibility_results = {
        'vm_responsive': False,
        'shared_folders_working': False,
        'python_available': False,
        'poetry_available': False,
        'adarevm_server_starts': False,
        'websocket_connection': False,
        'screenshot_command': False,
        'click_command': False
    }

    try:
        # Test 1: Basic VM responsiveness with substage
        async with StageCtxManagerLite(VMResponseTestStage(), flow_console, level=2):
            compatibility_results['vm_responsive'] = await test_vm_response(context)

        # Test 2: Shared folder access with substage
        async with StageCtxManagerLite(VMSharedFoldersTestStage(), flow_console, level=2):
            compatibility_results['shared_folders_working'] = await test_shared_folders(context)

        # Test 3: Python availability with substage
        async with StageCtxManagerLite(VMPythonTestStage(), flow_console, level=2):
            compatibility_results['python_available'] = await test_python_availability(context)

        # Test 4: Poetry availability with substage
        async with StageCtxManagerLite(VMPoetryTestStage(), flow_console, level=2):
            compatibility_results['uv_available'] = await test_uv_availability(context)

        # Test 5: Start adarevm WebSocket server with substage
        async with StageCtxManagerLite(VMAdareServerTestStage(), flow_console, level=2):
            compatibility_results['adarevm_server_starts'] = await test_adarevm_server_start(context, guest_bind_port=guest_bind_port)

        # Test 6: WebSocket connection with substage
        async with StageCtxManagerLite(VMWebSocketTestStage(), flow_console, level=2):
            compatibility_results['websocket_connection'] = await test_websocket_connection(context)

        # Only run WebSocket commands if connection was successful
        if compatibility_results['websocket_connection']:
            # Test 7: Screenshot command with substage
            async with StageCtxManagerLite(VMScreenshotTestStage(), flow_console, level=2):
                compatibility_results['screenshot_command'] = await test_screenshot_command(context)

            # Test 8: Click command with substage
            async with StageCtxManagerLite(VMClickTestStage(), flow_console, level=2):
                compatibility_results['click_command'] = await test_click_command(context)

    except (OSError, ConnectionError, TimeoutError, RuntimeError) as e:
        log.error(f"Compatibility test error: {e}")

    # Summary
    passed_tests = sum(compatibility_results.values())
    total_tests = len(compatibility_results)

    log.info(f"Compatibility test results: {passed_tests}/{total_tests} tests passed")
    for test_name, result in compatibility_results.items():
        status = "PASS" if result else "FAIL"
        log.info(f"  - {test_name}: {status}")

    # Return results instead of throwing exception - let flow console show the summary
    success = passed_tests >= 6  # At least VM basics + server + websocket + one command

    if success:
        log.info("VM appears compatible with ADARE (WebSocket server working)")
    else:
        log.warning(f"VM compatibility insufficient: only {passed_tests}/{total_tests} tests passed")

    return success


async def cleanup_test_vm(context, keep_vm: bool = False):
    """Clean up test VM and resources."""
    log.info("Cleaning up test resources...")

    try:
        # Disconnect WebSocket client (adarevm server stops automatically when VM stops)
        if context.client:
            await context.client.disconnect()
            log.info("WebSocket client disconnected")

        # Handle VM cleanup based on keep_vm flag
        if context.vm:
            if keep_vm:
                # Stop VM but don't remove it
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


async def ova_test(ova_file_path: Path, guest_platform: str, verbose: bool = False, vm_cleanup_mode: str = 'prompt') -> bool:
    """
    Test OVA file compatibility with ADARE using separate workflow that reuses existing steps.

    Args:
        ova_file_path: Path to the .ova file to test
        guest_platform: Platform type ('windows' or 'linux') - required
        verbose: Enable verbose logging

    Returns:
        True if VM is compatible with ADARE, False otherwise
    """
    from adare.types.stages import VMCompatibilityTestStage, VMTestCleanupStage, VMTestSetupStage
    from adare.backend.experiment.commands.manage import StageCtxManagerLite
    from adare.backend.experiment.step_runner import ExperimentStepRunner

    if not ova_file_path.exists():
        raise LoggedException(log, f"OVA file not found: {ova_file_path}")

    if guest_platform not in ['linux', 'windows']:
        raise LoggedException(log, f"Invalid platform '{guest_platform}'. Must be 'linux' or 'windows'")

    start_time = time.time()

    log.info(f"ova_test function started - Testing OVA file: {ova_file_path}")
    log.info(f"Platform: {guest_platform}")

    # Create and start flow console for better visibility
    from adare.backend.experiment.diff_run import __create_and_start_flow_console, __start_event_listeners
    user_interrupt_event = threading.Event()
    flow_console = __create_and_start_flow_console("vm_test", disable_printing=False, external_stop_event=user_interrupt_event)
    flow_console.start_experiment_timer(f"VM Test: {ova_file_path.name}")

    # Start stage event coordinator for stage management
    from adare.backend.events.coordinator import start_stage_coordinator
    start_stage_coordinator()
    __start_event_listeners("vm_test")

    # Create minimal context for OVA test
    context = create_ova_test_context(ova_file_path, guest_platform)
    context.user_interrupt_event = user_interrupt_event

    # Create step runner for consistent execution
    stop_event = asyncio.Event()
    context.stop_event = stop_event
    step_runner = ExperimentStepRunner(stop_event, user_interrupt_event)

    try:
        # VM Test Setup Phase - Import OVA, setup shared folders, start and prepare VM
        if not stop_event.is_set():
            log.info("Starting VM Test Setup Phase...")
            async with StageCtxManagerLite(VMTestSetupStage(), flow_console, level=1):
                setup_steps = [
                    import_ova_for_test,
                    setup_shared_folders_for_test,
                    start_test_vm,
                    wait_for_test_vm_ready,
                    mount_shared_directories_in_test_vm,
                ]
                for setup_step in setup_steps:
                    await step_runner.run_async_step(setup_step, context)

        # VM Compatibility Testing Phase
        vm_compatibility_success = False
        if not stop_event.is_set():
            async with StageCtxManagerLite(VMCompatibilityTestStage(), flow_console, level=1):
                vm_compatibility_success = await step_runner.run_async_step(lambda ctx: test_vm_compatibility(ctx, flow_console), context)

        # Check if VM compatibility tests passed
        if not vm_compatibility_success:
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
        # VM Test Cleanup Phase
        try:
            async with StageCtxManagerLite(VMTestCleanupStage(), flow_console, level=1):
                # Determine VM cleanup behavior - default is remove unless --keep-vm specified
                keep_vm = False
                if context.vm:
                    if vm_cleanup_mode == 'keep':
                        keep_vm = True
                        log.info("Keeping VM for further testing (--keep-vm specified)")
                    else:
                        keep_vm = False
                        log.info("Removing VM automatically (default behavior)")

                await cleanup_test_vm(context, keep_vm=keep_vm)
        except (OSError, ConnectionError, TimeoutError, RuntimeError) as cleanup_error:
            # Cleanup in finally must not mask the original error
            log.error(f"Error during cleanup: {cleanup_error}")

        # Stop the flow console
        try:
            from adare.backend.events.coordinator import stop_stage_coordinator
            stop_stage_coordinator()
            flow_console.stop()
        except (OSError, RuntimeError) as e:
            # Cleanup in finally must not mask the original error
            log.error(f"Error stopping flow console: {e}")


# =============================================================================
# Registered QEMU VM compatibility test
#
# Mirrors the OVA flow above but for a VM already registered in the database.
# It runs entirely DB-free (no VmInstance rows), boots the guest off an
# overlay backed by the immutable base disk, and reuses the same compatibility
# test functions and stage classes as ova_test.
# =============================================================================

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

    # Minimal config for testing. websocket_port is the fixed test HOST port;
    # setup_networking forwards it to the in-guest 18765.
    config = ExperimentConfig(
        project_path=Path("/tmp"),  # Dummy path
        experiment_name="qemu_vm_test",
        environment_name="qemu_vm_test_env",
        test_mode=True,
        preserve_snapshot=False,
        vm_cpus=2,
        vm_memory=2048,
        websocket_port=19000,  # Test port outside production range
        vm_resolution=(1920, 1080)
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
    selection + Apple-Silicon guard) but without any DB/environment lookups.
    The base disk stays immutable: all writes go to the experiment overlay.
    """
    import platform as _platform

    from adare.config import get_vm_credentials
    from adare.hypervisor.exceptions import HypervisorException
    from adare.hypervisor.qemu.manager import QEMUManager
    from adare.hypervisor.qemu.vm import QEMUVM

    log.info("Phase 1 - Preparing QEMU VM for test...")

    vm_architecture = context.guest_architecture or 'x86_64'

    # Block x86_64 guests on Apple Silicon (no hardware acceleration)
    if _platform.system() == 'Darwin' and _platform.machine() == 'arm64' and vm_architecture != 'aarch64':
        raise HypervisorException(
            f"QEMU cannot hardware-accelerate {vm_architecture} guests on Apple Silicon (ARM). "
            "Only aarch64 guests are supported on Apple Silicon with HVF. "
            "Use VirtualBox instead (supports x86 via Rosetta)."
        )

    # Compute architecture-appropriate machine type and accelerator
    if vm_architecture == 'aarch64':
        vm_machine = 'virt'
        vm_accel = 'hvf' if _platform.system() == 'Darwin' else 'kvm'
    else:
        vm_machine = 'pc'
        vm_accel = 'hvf' if _platform.system() == 'Darwin' else 'kvm'

    qemu_manager = QEMUManager()
    username, password = get_vm_credentials(context.guest_platform)

    # Pass the base disk path explicitly so QEMUVM treats it as the (external)
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
        disk_path=context._registered_disk_path,
        architecture=vm_architecture
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
    """Configure a single virtio-fs share (ADAREVM_DIR -> /adare/vm).

    Bypasses the project-coupled build_share_list: the compat test only needs
    the adarevm source available at /adare/vm so the guest can start the server.
    """
    from adare.config.configdirectory import ADAREVM_DIR

    log.info("Configuring single virtio-fs share for test...")

    is_windows = 'windows' in context.guest_platform.lower()
    base_mount = 'C:\\adare' if is_windows else '/adare'
    guest_mount = f'{base_mount}\\vm' if is_windows else f'{base_mount}/vm'

    shares = [{
        'tag': 'vm',
        'host_path': str(ADAREVM_DIR),
        'guest_mount': guest_mount,
        'readonly': True,
    }]

    context.vm.config.virtiofs_enabled = True
    context.vm.config.virtiofs_shares = shares
    context.vm._save_vm_config()

    # Also expose on context for post-boot mounting (mirrors virtiofs strategy)
    context.virtiofs_shares = shares

    log.info(f"Configured virtio-fs share: {ADAREVM_DIR} -> {guest_mount}")


async def start_qemu_test_vm(context):
    """Start the QEMU test VM and mount shares via the lifecycle strategy.

    Uses QEMULifecycleStrategy.start_and_initialize_vm which tolerates
    context.playbook being None and performs post-boot virtio-fs mounting.
    """
    from adare.hypervisor.qemu.lifecycle import QEMULifecycleStrategy

    log.info("Starting QEMU test VM...")
    await QEMULifecycleStrategy().start_and_initialize_vm(context)
    log.info("QEMU test VM started and ready")


async def _cleanup_registered_test_vm(context, keep_vm: bool = False):
    """Stop the test VM and remove its transient overlay + libvirt domain.

    Replicates the overlay + libvirt-undefine parts of the QEMU cleanup in
    vm_lifecycle_manager (NOT _release_vm_instance, which touches the
    VmInstance DB table). The immutable base disk is left untouched.
    """
    log.info("Cleaning up QEMU test resources...")

    try:
        if context.client:
            await context.client.disconnect()
            log.info("WebSocket client disconnected")
    except (OSError, ConnectionError, TimeoutError, RuntimeError) as e:
        log.warning(f"Error disconnecting WebSocket client: {e}")

    if not context.vm:
        return

    # Stop the VM (leaves the domain defined but shut off)
    try:
        await context.vm.stop()
        log.info("Test VM stopped")
    except (OSError, ConnectionError, TimeoutError, RuntimeError) as e:
        log.warning(f"Error stopping test VM: {e}")

    if keep_vm:
        log.info("Keeping overlay and libvirt domain (--keep-vm specified)")
        return

    # Delete the experiment overlay, leaving the immutable base disk intact
    if hasattr(context.vm, 'cleanup_overlay_disk'):
        experiment_id = context.experiment_run_ulid or 'default'
        try:
            await context.vm.cleanup_overlay_disk(experiment_id)
            log.info(f"Cleaned up QEMU overlay for test {experiment_id}")
        except (OSError, RuntimeError) as e:
            log.warning(f"Failed to cleanup overlay disk: {e}")

    # Undefine the transient libvirt domain to avoid stale disk references
    if hasattr(context.vm, '_libvirt_domain'):
        try:
            import libvirt

            if context.vm._libvirt_domain:
                try:
                    state, _ = context.vm._libvirt_domain.state()
                    if state == libvirt.VIR_DOMAIN_SHUTOFF:
                        context.vm._libvirt_domain.undefine()
                        log.info(f"Undefined libvirt domain '{context.vm.vm_name}'")
                    else:
                        log.warning(
                            f"Cannot undefine domain '{context.vm.vm_name}' - "
                            f"still running (state: {state})."
                        )
                except libvirt.libvirtError as e:
                    log.debug(f"Could not undefine domain: {e}")
                finally:
                    context.vm._libvirt_domain = None
        except (OSError, RuntimeError, ImportError) as e:
            log.warning(f"Failed to cleanup libvirt domain: {e}")

    log.info("Cleanup completed")


async def vm_test_registered(
    vm_name: str,
    disk_path: str,
    guest_platform: str,
    architecture: str = 'x86_64',
    verbose: bool = False,
    vm_cleanup_mode: str = 'prompt'
) -> bool:
    """Test a registered QEMU VM's compatibility with ADARE.

    DB-free orchestrator mirroring ova_test stage-for-stage: it boots the guest
    off an overlay, runs the shared compatibility tests, and cleans up the
    overlay + transient libvirt domain afterwards.

    Args:
        vm_name: Registered VM name (display only)
        disk_path: Path to the VM's immutable base disk (vm.file)
        guest_platform: 'linux' or 'windows'
        architecture: Guest CPU architecture
        verbose: Enable verbose logging
        vm_cleanup_mode: 'keep' skips overlay/domain removal; otherwise removed

    Returns:
        True if the VM is compatible with ADARE, False otherwise
    """
    from adare.types.stages import VMCompatibilityTestStage, VMTestCleanupStage, VMTestSetupStage
    from adare.backend.experiment.commands.manage import StageCtxManagerLite
    from adare.backend.experiment.step_runner import ExperimentStepRunner

    if guest_platform not in ['linux', 'windows']:
        raise LoggedException(log, f"Invalid platform '{guest_platform}'. Must be 'linux' or 'windows'")

    start_time = time.time()

    log.info(f"vm_test_registered started - Testing registered VM: {vm_name}")
    log.info(f"Platform: {guest_platform}, Architecture: {architecture}, Disk: {disk_path}")

    # Create and start flow console for better visibility (use the fixed diff_run import)
    from adare.backend.experiment.diff_run import __create_and_start_flow_console, __start_event_listeners
    user_interrupt_event = threading.Event()
    flow_console = __create_and_start_flow_console("vm_test", disable_printing=False, external_stop_event=user_interrupt_event)
    flow_console.start_experiment_timer(f"VM Test: {vm_name}")

    # Start stage event coordinator for stage management
    from adare.backend.events.coordinator import start_stage_coordinator
    start_stage_coordinator()
    __start_event_listeners("vm_test")

    # Create minimal DB-free context for the registered QEMU VM test
    context = create_registered_test_context(vm_name, disk_path, guest_platform, architecture)
    context.user_interrupt_event = user_interrupt_event

    # Create step runner for consistent execution
    stop_event = asyncio.Event()
    context.stop_event = stop_event
    step_runner = ExperimentStepRunner(stop_event, user_interrupt_event)

    try:
        # VM Test Setup Phase - build VM + overlay, network, share, start
        if not stop_event.is_set():
            log.info("Starting QEMU VM Test Setup Phase...")
            async with StageCtxManagerLite(VMTestSetupStage(), flow_console, level=1):
                setup_steps = [
                    create_qemu_vm_for_test,
                    setup_qemu_networking_for_test,
                    setup_qemu_share_for_test,
                    start_qemu_test_vm,
                ]
                for setup_step in setup_steps:
                    await step_runner.run_async_step(setup_step, context)

        # VM Compatibility Testing Phase (guest binds 18765, host connects forwarded 19000)
        vm_compatibility_success = False
        if not stop_event.is_set():
            async with StageCtxManagerLite(VMCompatibilityTestStage(), flow_console, level=1):
                vm_compatibility_success = await step_runner.run_async_step(
                    lambda ctx: test_vm_compatibility(ctx, flow_console, guest_bind_port=18765), context
                )

        if not vm_compatibility_success:
            log.error("VM compatibility tests failed - VM may not be fully compatible with ADARE")
            flow_console.finish_experiment_timer(success=False)
            return False

        elapsed_time = time.time() - start_time
        log.info(f"Registered VM test completed successfully! VM is compatible with ADARE. (took {elapsed_time:.1f} seconds)")
        flow_console.finish_experiment_timer(success=True)
        return True

    except (OSError, ConnectionError, TimeoutError, RuntimeError, ValueError) as e:
        log.error(f"Registered VM test failed with unexpected error: {e}")
        import traceback
        traceback.print_exc()
        flow_console.finish_experiment_timer(success=False)
        return False
    finally:
        # VM Test Cleanup Phase
        try:
            async with StageCtxManagerLite(VMTestCleanupStage(), flow_console, level=1):
                keep_vm = False
                if context.vm and vm_cleanup_mode == 'keep':
                    keep_vm = True
                    log.info("Keeping VM for further testing (--keep-vm specified)")
                await _cleanup_registered_test_vm(context, keep_vm=keep_vm)
        except (OSError, ConnectionError, TimeoutError, RuntimeError) as cleanup_error:
            log.error(f"Error during cleanup: {cleanup_error}")

        # Stop the flow console
        try:
            from adare.backend.events.coordinator import stop_stage_coordinator
            stop_stage_coordinator()
            flow_console.stop()
        except (OSError, RuntimeError) as e:
            log.error(f"Error stopping flow console: {e}")
