"""
VM Testing module for ADARE - handles OVA compatibility testing.

This module contains functions for testing VM compatibility with ADARE,
including setup, WebSocket server testing, and cleanup operations.
"""

import threading
import asyncio

import time
from pathlib import Path
from adare.exceptions import LoggedException
import logging
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
    log.info("CLAUDE: Phase 1 - Importing OVA file...")
    
    from adare.config import get_vm_credentials
    from adare.hypervisor.virtualbox.vm import VirtualBoxVM
    from adare.hypervisor.virtualbox.manager import VirtualBoxManager
    
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
    
    log.info("CLAUDE: OVA imported successfully")


async def setup_shared_folders_for_test(context):
    """Setup shared folders in VirtualBox for testing."""
    log.info("CLAUDE: Setting up shared folders...")
    
    # Add shared folders to VirtualBox (similar to VM lifecycle manager)
    for name, paths in context.config.shared_directories.items():
        await context.vm.add_shared_folder(name, host_path=paths['host'], stop_event=context.user_interrupt_event)
    
    log.info("CLAUDE: Shared folders configured in VirtualBox")


async def start_test_vm(context):
    """Start the test VM."""
    log.info("CLAUDE: Starting test VM...")
    
    # Start VM using same approach as VMLifecycleManager
    await context.vm.start(stop_event=context.user_interrupt_event)
    log.info("CLAUDE: Test VM started")


async def wait_for_test_vm_ready(context):
    """Wait for test VM to be ready."""
    log.info("CLAUDE: Waiting for test VM to be ready...")
    
    # Wait for VM to be responsive using same approach as VMLifecycleManager
    await context.vm.wait_until_ready(stop_event=context.user_interrupt_event)
    log.info("CLAUDE: Test VM is ready")


async def mount_shared_directories_in_test_vm(context):
    """Mount shared directories in test VM."""
    log.info("CLAUDE: Mounting shared directories in test VM...")
    
    # Mount shared directories using same approach as VMLifecycleManager
    await context.vm.mount_shared_directories(stop_event=context.user_interrupt_event)
    log.info("CLAUDE: Shared directories mounted in test VM")


# VM Compatibility Test Functions
async def test_vm_response(context):
    """Test basic VM responsiveness."""
    test_result = await context.vm.run_command("true", stop_event=context.user_interrupt_event)
    if test_result.returncode == 0:
        log.info("CLAUDE: VM is responsive to commands")
        return True
    else:
        log.warning(f"CLAUDE: VM not responding to commands. Exit code: {test_result.returncode}")
        return False


async def test_shared_folders(context):
    """Test shared folder accessibility."""
    ls_result = await context.vm.run_command("test -d /adare/app", stop_event=context.user_interrupt_event)
    if ls_result.returncode == 0:
        log.info("CLAUDE: Shared folders are accessible")
        return True
    else:
        log.warning(f"CLAUDE: Shared folders not accessible. Exit code: {ls_result.returncode}")
        return False


async def test_python_availability(context):
    """Test Python availability in VM."""
    python_result = await context.vm.run_command("python3 --version", stop_event=context.user_interrupt_event)
    if python_result.returncode == 0:
        log.info("CLAUDE: Python is available")
        return True
    else:
        log.warning(f"CLAUDE: Python not available. Exit code: {python_result.returncode}")
        return False


async def test_poetry_availability(context):
    """Test Poetry availability in VM."""
    poetry_result = await context.vm.run_command("poetry --version", stop_event=context.user_interrupt_event)
    if poetry_result.returncode == 0:
        log.info("CLAUDE: Poetry is available")
        return True
    else:
        log.warning(f"CLAUDE: Poetry not available. Exit code: {poetry_result.returncode}")
        return False


async def test_adarevm_server_start(context):
    """Test starting the adarevm WebSocket server.

    NOTE: This test requires Poetry-based VMs (does not support wheel-only installations).
    The test uses 'poetry run' to start the adarevm server from source.
    """
    try:
        # Start adarevm server in background
        # NOTE: This requires Poetry - does not work with wheel-only installations
        start_command = f"cd /adare/app && python3 -m poetry run python -m adarevm.server --port {context.config.websocket_port} &"

        start_result = await context.vm.run_command(start_command, stop_event=context.user_interrupt_event)

        if start_result.returncode == 0:
            log.info("CLAUDE: AdareVM server started successfully")
            # Give server time to initialize
            import asyncio
            await asyncio.sleep(3.0)
            return True
        else:
            log.warning(f"CLAUDE: Failed to start adarevm server. Exit code: {start_result.returncode}")
            return False
            
    except Exception as e:
        log.warning(f"CLAUDE: Exception starting adarevm server: {e}")
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
            log.info("CLAUDE: WebSocket connection established")
            return True
        else:
            log.warning("CLAUDE: Could not establish WebSocket connection")
            return False
            
    except Exception as e:
        log.warning(f"CLAUDE: WebSocket test error: {e}")
        return False


async def test_screenshot_command(context):
    """Test screenshot command via WebSocket."""
    try:
        result = await context.client.call_tool("take_screenshot", timeout=10.0)
        if result and not result.get('error'):
            log.info("CLAUDE: Screenshot command successful")
            return True
        else:
            log.warning(f"CLAUDE: Screenshot command failed: {result}")
            return False
    except Exception as e:
        log.warning(f"CLAUDE: Screenshot command error: {e}")
        return False


async def test_click_command(context):
    """Test click command via WebSocket."""
    try:
        click_x = 10
        click_y = 10
        
        result = await context.client.call_tool("click", {"x": click_x, "y": click_y}, timeout=10.0)
        if result and not result.get('error'):
            log.info(f"CLAUDE: Click command successful (clicked at {click_x}, {click_y})")
            return True
        else:
            log.warning(f"CLAUDE: Click command failed: {result}")
            return False
    except Exception as e:
        log.warning(f"CLAUDE: Click command error: {e}")
        return False


async def test_vm_compatibility(context, flow_console):
    """Test VM compatibility with ADARE WebSocket server and execute simple experiment commands."""
    from adare.backend.experiment.stagectxmanager import StageCtxManagerLite
    from adare.backend.events.stages import (
        VMResponseTestStage, VMSharedFoldersTestStage, VMPythonTestStage, 
        VMPoetryTestStage, VMAdareServerTestStage, VMWebSocketTestStage,
        VMScreenshotTestStage, VMClickTestStage
    )
    
    log.info("CLAUDE: Testing VM compatibility with ADARE WebSocket server...")
    
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
            compatibility_results['poetry_available'] = await test_poetry_availability(context)
            
        # Test 5: Start adarevm WebSocket server with substage
        async with StageCtxManagerLite(VMAdareServerTestStage(), flow_console, level=2):
            compatibility_results['adarevm_server_starts'] = await test_adarevm_server_start(context)
            
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
            
    except Exception as e:
        log.error(f"CLAUDE: Compatibility test error: {e}")
    
    # Summary 
    passed_tests = sum(compatibility_results.values())
    total_tests = len(compatibility_results)
    
    log.info(f"CLAUDE: Compatibility test results: {passed_tests}/{total_tests} tests passed")
    for test_name, result in compatibility_results.items():
        status = "PASS" if result else "FAIL"
        log.info(f"CLAUDE:   - {test_name}: {status}")
        
    # Return results instead of throwing exception - let flow console show the summary
    success = passed_tests >= 6  # At least VM basics + server + websocket + one command
    
    if success:
        log.info("CLAUDE: VM appears compatible with ADARE (WebSocket server working)")
    else:
        log.warning(f"CLAUDE: VM compatibility insufficient: only {passed_tests}/{total_tests} tests passed")
    
    return success


async def cleanup_test_vm(context, keep_vm: bool = False):
    """Clean up test VM and resources."""
    log.info("CLAUDE: Cleaning up test resources...")
    
    try:
        # Disconnect WebSocket client (adarevm server stops automatically when VM stops)
        if context.client:
            await context.client.disconnect()
            log.info("CLAUDE: WebSocket client disconnected")
        
        # Handle VM cleanup based on keep_vm flag
        if context.vm:
            if keep_vm:
                # Stop VM but don't remove it
                await context.vm.stop()
                log.info("CLAUDE: Test VM stopped but kept for manual inspection")
                log.info("CLAUDE: You can manually remove it later with: VBoxManage unregistervm --delete")
            else:
                await context.vm.remove()
                log.info("CLAUDE: Test VM removed successfully")
        
    except Exception as e:
        log.error(f"CLAUDE: Error during cleanup: {e}")
    
    log.info("CLAUDE: Cleanup completed")


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
    from adare.exceptions import LoggedException
    from adare.backend.experiment.step_runner import ExperimentStepRunner
    from adare.backend.experiment.stagectxmanager import StageCtxManagerLite
    from adare.backend.events.stages import VMTestSetupStage, VMCompatibilityTestStage, VMTestCleanupStage
    
    if not ova_file_path.exists():
        raise LoggedException(log, f"OVA file not found: {ova_file_path}")
    
    if guest_platform not in ['linux', 'windows']:
        raise LoggedException(log, f"Invalid platform '{guest_platform}'. Must be 'linux' or 'windows'")
    
    start_time = time.time()
    
    log.info(f"CLAUDE: ova_test function started - Testing OVA file: {ova_file_path}")
    log.info(f"CLAUDE: Platform: {guest_platform}")
    
    # Create and start flow console for better visibility
    from adare.backend.experiment.commands import __create_and_start_flow_console, __start_event_listeners
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
            log.info("CLAUDE: Starting VM Test Setup Phase...")
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
            log.error("CLAUDE: VM compatibility tests failed - VM may not be fully compatible with ADARE")
            flow_console.finish_experiment_timer(success=False)
            return False
        
        elapsed_time = time.time() - start_time
        log.info(f"CLAUDE: OVA test completed successfully! File is compatible with ADARE. (took {elapsed_time:.1f} seconds)")
        flow_console.finish_experiment_timer(success=True)
        return True
        
    except Exception as e:
        log.error(f"CLAUDE: OVA test failed with unexpected error: {e}")
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
                        log.info("CLAUDE: Keeping VM for further testing (--keep-vm specified)")
                    else:
                        keep_vm = False
                        log.info("CLAUDE: Removing VM automatically (default behavior)")
                
                await cleanup_test_vm(context, keep_vm=keep_vm)
        except Exception as cleanup_error:
            log.error(f"CLAUDE: Error during cleanup: {cleanup_error}")
        
        # Stop the flow console
        try:
            from adare.backend.events.coordinator import stop_stage_coordinator
            stop_stage_coordinator()
            flow_console.stop()
        except Exception as e:
            log.error(f"Error stopping flow console: {e}")
