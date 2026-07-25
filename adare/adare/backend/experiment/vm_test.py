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
#
# NOTE: run_command executes the given string via the guest's native shell --
# PowerShell on Windows guests, /bin/sh on Linux -- so every probe below must
# be issued in the correct syntax for the guest OS. Windows PowerShell cmdlets
# (e.g. Test-Path) do not set a process exit code, so those branches exit
# explicitly to make returncode meaningful.
def _is_windows(context) -> bool:
    return 'windows' in context.guest_platform.lower()


async def test_vm_response(context):
    """Test basic VM responsiveness."""
    cmd = "Write-Output ok" if _is_windows(context) else "true"
    test_result = await context.vm.run_command(cmd, stop_event=context.user_interrupt_event)
    if test_result.returncode == 0:
        log.info("VM is responsive to commands")
        return True, None
    log.warning(f"VM not responding to commands. Exit code: {test_result.returncode}")
    return False, f"VM not responding to commands. Exit code: {test_result.returncode}"


async def test_shared_folders(context):
    """Test shared folder accessibility (adarevm source reachable in guest)."""
    if _is_windows(context):
        cmd = "if (Test-Path 'C:\\adare\\vm\\pyproject.toml') { exit 0 } else { exit 1 }"
    else:
        cmd = "test -f /adare/vm/pyproject.toml"
    ls_result = await context.vm.run_command(cmd, stop_event=context.user_interrupt_event)
    if ls_result.returncode == 0:
        log.info("Shared folders are accessible")
        return True, None
    log.warning(f"Shared folders not accessible. Exit code: {ls_result.returncode}")
    return False, f"Shared folders not accessible. Exit code: {ls_result.returncode}"


async def test_python_availability(context):
    """Test Python availability in VM."""
    if _is_windows(context):
        # Windows ships 'python'/'py', not 'python3'. The App Execution Alias
        # stub returns non-zero, so accept either launcher.
        cmd = (
            "python --version; if ($LASTEXITCODE -eq 0) { exit 0 }; "
            "py --version; exit $LASTEXITCODE"
        )
    else:
        cmd = "python3 --version"
    python_result = await context.vm.run_command(cmd, stop_event=context.user_interrupt_event)
    if python_result.returncode == 0:
        log.info("Python is available")
        return True, None
    log.warning(f"Python not available. Exit code: {python_result.returncode}")
    return False, f"Python not available. Exit code: {python_result.returncode}"


async def test_uv_availability(context):
    """Test uv availability in VM (needed to launch adarevm from source)."""
    # 'uv --version' is identical on both shells; inject the user PATH on Windows
    # so a per-user uv install (e.g. %USERPROFILE%\.local\bin) is discoverable.
    uv_result = await context.vm.run_command(
        "uv --version",
        stop_event=context.user_interrupt_event,
        inject_user_path=_is_windows(context),
    )
    if uv_result.returncode == 0:
        log.info("uv is available")
        return True, None
    log.warning(f"uv not available. Exit code: {uv_result.returncode}")
    return False, f"uv not available. Exit code: {uv_result.returncode}"


async def test_adarevm_server_start(context, guest_bind_port: int | None = None):
    """Test starting the adarevm WebSocket server from the shared source.

    Launches the ``adarevm`` console entry point (``adarevm.main:run``) via uv.
    The server always binds ``0.0.0.0:18765`` (hardcoded in AdareVMServer); there
    is no ``--port`` flag, so ``guest_bind_port`` is informational only -- for
    QEMU the host reaches it over the 19000->18765 forward.

    On Windows the launch mirrors the real experiment flow (agent_lifecycle):
    a user-session scheduled task (``run_as_user``) is required for the GUI
    automation the later screenshot/click tests exercise, and -- in SMB mode --
    that task's session must re-establish the ``\\\\10.0.2.4\\qemu`` connection
    before it can resolve the ``C:\\adare\\vm`` junction. The scheduled-task
    runner waits and verifies port 18765 is LISTENING before returning.

    NOTE: requires uv-based (editable) VMs; wheel-only images are not covered.

    Args:
        context: ExperimentRunCtx
        guest_bind_port: In-guest bind port expected by the caller (18765 for QEMU).
    """
    if guest_bind_port is not None and guest_bind_port != 18765:
        log.warning(
            f"adarevm binds 18765 unconditionally; requested guest_bind_port="
            f"{guest_bind_port} cannot be honored."
        )
    try:
        if _is_windows(context):
            # Editable source is shared at C:\adare\vm (project root with
            # pyproject.toml). Re-establish SMB in the task's user session so
            # the junction resolves, then launch adarevm from that directory.
            log_path = r'C:\Windows\Temp'
            stderr_log = rf'{log_path}\adarevm_stderr.log'
            run_cmd = 'uv run --package adarevm adarevm'
            if getattr(context.vm.config, 'smb_share_path', None):
                run_cmd = (
                    'reg add "HKLM\\SYSTEM\\CurrentControlSet\\Services'
                    '\\LanmanWorkstation\\Parameters" '
                    '/v AllowInsecureGuestAuth /t REG_DWORD /d 1 /f >$null 2>&1; '
                    'Set-SmbClientConfiguration -RequireSecuritySignature $false '
                    '-Force -ErrorAction SilentlyContinue; '
                    f'net use \\\\10.0.2.4\\qemu /persistent:no 2>>"{stderr_log}"; '
                    + run_cmd
                )
            start_result = await context.vm.run_command(
                run_cmd,
                cwd=r'C:\adare\vm',
                admin=True,
                run_as_user=True,
                stop_event=context.user_interrupt_event,
                redirect_stdout=rf'{log_path}\adarevm_stdout.log',
                redirect_stderr=stderr_log,
            )
            if start_result.returncode == 0:
                log.info("AdareVM server started successfully (port 18765 listening)")
                return True, None
            log.warning(
                f"Failed to start adarevm server. Exit code: "
                f"{start_result.returncode}. stderr: {start_result.stderr}"
            )
            return False, (
                f"Failed to start adarevm server. Exit code: "
                f"{start_result.returncode}. stderr: {start_result.stderr}"
            )

        # Linux: mirror the real experiment launch (agent_command_builders).
        # The workspace root is shared at /adare/vm; cd into the adarevm member so
        # uv resolves its `adarelib = { workspace = true }` dependency. Pre-sync
        # the venv (the slow first-run build; cached in the shared .venv after),
        # grant the guest-agent (root) access to the autologin user's X display
        # (DISPLAY/XAUTHORITY + `xhost +SI:localuser:root`), then run adarevm.
        import asyncio
        sync_command = "cd /adare/vm/adarevm && uv sync 2>&1 | tail -3"
        log.info("Pre-syncing adarevm venv in guest (first run builds deps)...")
        await context.vm.run_command(sync_command, stop_event=context.user_interrupt_event)
        start_command = (
            "export DISPLAY=:0; "
            "export XAUTHORITY=$(ls /run/user/*/gdm/Xauthority /run/user/*/.mutter-Xwaylandauth.* "
            "/home/adare/.Xauthority 2>/dev/null | head -1); "
            "xhost +SI:localuser:root >/dev/null 2>&1 || true; "
            "cd /adare/vm/adarevm && nohup uv run adarevm >/tmp/adarevm.log 2>&1 &"
        )
        start_result = await context.vm.run_command(start_command, stop_event=context.user_interrupt_event)
        if start_result.returncode == 0:
            log.info("AdareVM server launched; waiting for it to initialize")
            await asyncio.sleep(6.0)
            return True, None
        log.warning(f"Failed to start adarevm server. Exit code: {start_result.returncode}")
        return False, f"Failed to start adarevm server. Exit code: {start_result.returncode}"

    except (OSError, ConnectionError, TimeoutError, RuntimeError) as e:
        log.warning(f"Exception starting adarevm server: {e}")
        return False, f"Exception starting adarevm server: {e}"


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
            return True, None
        log.warning("Could not establish WebSocket connection")
        return False, "Could not establish WebSocket connection"

    except (OSError, ConnectionError, TimeoutError, RuntimeError) as e:
        log.warning(f"WebSocket test error: {e}")
        return False, f"WebSocket test error: {e}"


async def test_screenshot_command(context):
    """Test screenshot command via WebSocket."""
    try:
        result = await context.client.call_tool("screenshot", timeout=10.0)
        if result and not result.get('error'):
            log.info("Screenshot command successful")
            return True, None
        log.warning(f"Screenshot command failed: {result}")
        return False, f"Screenshot command failed: {result}"
    except (OSError, ConnectionError, TimeoutError, RuntimeError) as e:
        log.warning(f"Screenshot command error: {e}")
        return False, f"Screenshot command error: {e}"


async def test_click_command(context):
    """Test click command via WebSocket."""
    try:
        click_x = 10
        click_y = 10

        result = await context.client.call_tool("click", {"x": click_x, "y": click_y}, timeout=10.0)
        if result and not result.get('error'):
            log.info(f"Click command successful (clicked at {click_x}, {click_y})")
            return True, None
        log.warning(f"Click command failed: {result}")
        return False, f"Click command failed: {result}"
    except (OSError, ConnectionError, TimeoutError, RuntimeError) as e:
        log.warning(f"Click command error: {e}")
        return False, f"Click command error: {e}"


def _decode_clixml_xml(xml_block: str) -> str:
    """Decode one PowerShell CLIXML ``<Objs>...</Objs>`` block to readable text.

    Drops ``<Obj S="progress">`` nodes (the "Preparing modules for first use"
    progress-bar noise) and joins the remaining text. Falls back to tag-stripping
    if the block is not well-formed XML.
    """
    import xml.etree.ElementTree as ET

    try:
        root = ET.fromstring(xml_block)
    except ET.ParseError:
        # Malformed CLIXML: strip tags and return the raw text.
        import re
        return re.sub(r'<[^>]+>', ' ', xml_block)

    for progress in root.findall('.//Obj[@S="progress"]'):
        # Remove the progress node in place from its parent.
        parent = None
        for candidate in root.iter():
            if progress in list(candidate):
                parent = candidate
                break
        if parent is not None:
            parent.remove(progress)

    return ' '.join(t for t in root.itertext() if t)


def _decode_guest_stderr(stderr: str) -> str:
    """Clean guest stderr into readable lines, decoding any CLIXML block.

    PowerShell remoting wraps stderr in ``#< CLIXML`` followed by an ``<Objs>``
    block. The plain-text lines outside it (``ERROR:`` / ``FATAL:`` /
    ``Task_Status:`` from the scheduled-task wrapper) are kept; the CLIXML block
    is decoded via ``_decode_clixml_xml``. Leftover tags are stripped, whitespace
    collapsed, and consecutive duplicate lines deduped. Non-CLIXML stderr (Linux
    guests, plain errors) passes through cleaned. The ``#< CLIXML`` marker never
    appears in the output.
    """
    import re

    if not stderr:
        return ''

    text = stderr
    # Locate the <Objs>...</Objs> block (case-insensitive, dot-matches-newline).
    # The opening tag carries a Version attribute (e.g. <Objs Version="1.1.0.1">).
    objs_match = re.search(r'<Objs[^>]*>.*?</Objs>', text, re.IGNORECASE | re.DOTALL)
    if objs_match:
        decoded = _decode_clixml_xml(objs_match.group(0))
        text = text[:objs_match.start()] + '\n' + decoded + '\n' + text[objs_match.end():]

    # Strip any remaining tags (e.g. stray <S>, <AV>, <Props> fragments).
    text = re.sub(r'<[^>]+>', ' ', text)
    # Drop the CLIXML marker if it survived.
    text = text.replace('#< CLIXML', ' ')

    lines = []
    for raw in text.splitlines():
        line = re.sub(r'\s+', ' ', raw).strip()
        if not line:
            continue
        if lines and lines[-1] == line:
            continue  # dedupe consecutive identical lines
        lines.append(line)
    return '\n'.join(lines)


def _split_reason(reason: str | None) -> tuple[str, str]:
    """Split a failure reason into ``(summary, detail)``.

    The adarevm-server failure embeds the raw guest stderr after ``. stderr: ``.
    The summary is the text before that boundary (re-dotted); the detail is the
    decoded stderr. Reasons without the boundary yield ``summary = reason`` and
    an empty detail.
    """
    if not reason:
        return '', ''
    marker = '. stderr: '
    idx = reason.find(marker)
    if idx == -1:
        return reason, ''
    summary = reason[:idx].rstrip('.') + '.'
    detail = _decode_guest_stderr(reason[idx + len(marker):])
    return summary, detail


def _print_compat_failures(context) -> None:
    """Print a parsed "Failure details" block after the tree, before the verdict.

    Uses bare ``print`` -- the flow console Live display is already stopped by the
    caller, so this renders as plain text below the persisted tree. No-op when
    ``context.compat_failures`` is empty (the fully-compatible case).
    """
    failures = getattr(context, 'compat_failures', None)
    if not failures:
        return
    print()
    print("Failure details:")
    for stage_msg, summary, detail in failures:
        print(f"  ✖ {stage_msg}: {summary}")
        if detail:
            for line in detail.splitlines():
                print(f"       {line}")


async def _run_compat_substage(stage_cls, flow_console, context, fn, **kwargs) -> bool:
    """Run one compatibility test under its stage and reflect the boolean result in the
    stage glyph (✖ on False). The failure reason is NOT emitted into the tree (a
    multiline CLIXML stderr would explode it mid-run); instead the parsed
    ``(summary, detail)`` is collected on ``context.compat_failures`` for the
    end-of-run "Failure details" block. Returns the bool so compatibility_results
    stays a dict of bools (sum() in the verdict logic is unchanged)."""
    from adare.backend.experiment.commands.manage import StageCtxManagerLite

    async with StageCtxManagerLite(stage_cls(), flow_console, level=2) as cm:
        ok, reason = await fn(context, **kwargs)
        cm.set_result(ok)
        if not ok:
            summary, detail = _split_reason(reason)
            context.compat_failures.append((cm.stage.msg, summary, detail))
        return ok


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
        VMPythonTestStage,
        VMResponseTestStage,
        VMScreenshotTestStage,
        VMSharedFoldersTestStage,
        VMUvTestStage,
        VMWebSocketTestStage,
    )
    from adare.backend.experiment.commands.manage import StageCtxManagerLite

    log.info("Testing VM compatibility with ADARE WebSocket server...")

    # Collected by _run_compat_substage: list of (stage_msg, summary, detail) for
    # failing sub-stages, printed as a parsed "Failure details" block after the
    # tree by the orchestrator's finally block.
    context.compat_failures = []

    compatibility_results = {
        'vm_responsive': False,
        'shared_folders_working': False,
        'python_available': False,
        'uv_available': False,  # set by test_uv_availability below
        'adarevm_server_starts': False,
        'websocket_connection': False,
        'screenshot_command': False,
        'click_command': False
    }

    try:
        # Test 1: Basic VM responsiveness with substage
        compatibility_results['vm_responsive'] = await _run_compat_substage(VMResponseTestStage, flow_console, context, test_vm_response)

        # Test 2: Shared folder access with substage
        compatibility_results['shared_folders_working'] = await _run_compat_substage(VMSharedFoldersTestStage, flow_console, context, test_shared_folders)

        # Test 3: Python availability with substage
        compatibility_results['python_available'] = await _run_compat_substage(VMPythonTestStage, flow_console, context, test_python_availability)

        # Test 4: uv availability with substage
        compatibility_results['uv_available'] = await _run_compat_substage(VMUvTestStage, flow_console, context, test_uv_availability)

        # Test 5: Start adarevm WebSocket server with substage
        compatibility_results['adarevm_server_starts'] = await _run_compat_substage(VMAdareServerTestStage, flow_console, context, test_adarevm_server_start, guest_bind_port=guest_bind_port)

        # Test 6: WebSocket connection with substage
        compatibility_results['websocket_connection'] = await _run_compat_substage(VMWebSocketTestStage, flow_console, context, test_websocket_connection)

        # Only run WebSocket commands if connection was successful
        if compatibility_results['websocket_connection']:
            # Test 7: Screenshot command with substage
            compatibility_results['screenshot_command'] = await _run_compat_substage(VMScreenshotTestStage, flow_console, context, test_screenshot_command)

            # Test 8: Click command with substage
            compatibility_results['click_command'] = await _run_compat_substage(VMClickTestStage, flow_console, context, test_click_command)

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
            # With the Live display stopped, print the parsed failure block below
            # the persisted tree and before the CLI's ❌ verdict.
            _print_compat_failures(context)
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
    from adare.hypervisor.exceptions import HypervisorException
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
        shares = [{
            'tag': 'vm',
            'host_path': str(share_root),
            'guest_mount': guest_mount,
            'readonly': False,
        }]

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
        shutil.copytree(str(share_root), str(smb_dir / 'vm'), dirs_exist_ok=True,
                        ignore=shutil.ignore_patterns('.venv', '.git', '__pycache__'))

        context.vm.config.smb_share_path = str(smb_dir)
        context.vm.config.virtiofs_enabled = False
        context.vm.config.virtiofs_shares = []
        context.vm._save_vm_config()

        # Track for teardown (SMBStrategy's own cleanup never runs for the test,
        # since setup() was bypassed and post_boot uses a fresh strategy instance)
        context._test_smb_dir = str(smb_dir)

        log.info(
            f"Configured QEMU SLIRP SMB share: {share_root} -> "
            f"{smb_dir / 'vm'} -> {guest_mount}"
        )
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
    await QEMULifecycleStrategy().start_and_initialize_vm(context)
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


async def _cleanup_registered_test_vm(context, keep_vm: bool = False,
                                      flow_console=None, stage_id: str | None = None):
    """Stop the test VM and remove its transient overlay + libvirt domain.

    Replicates the overlay + libvirt-undefine parts of the QEMU cleanup in
    vm_lifecycle_manager (NOT _release_vm_instance, which touches the
    VmInstance DB table). The immutable base disk is left untouched.
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

    # Intentionally broad `except Exception` on every step below: best-effort
    # cleanup must not abort the remaining steps, and each failure is surfaced
    # to the flow console (never swallowed). Mirrors the shutdown precedent
    # in run.py (~L430).
    _update_message("Disconnecting WebSocket…")
    try:
        if context.client:
            await asyncio.wait_for(context.client.disconnect(), timeout=10)
            log.info("WebSocket client disconnected")
    except Exception as e:
        _surface_error("disconnect", "Disconnecting WebSocket", e)

    if not context.vm:
        if cleanup_errors:
            raise _CleanupFailed(cleanup_errors)
        return

    # Stop the VM with a hard poweroff — ephemeral test VMs don't need a
    # graceful ACPI shutdown (the overlay is discarded, the base disk is
    # untouched). force=True calls dom.destroy() immediately and leaves the
    # domain SHUTOFF so the undefine below still succeeds.
    _update_message("Stopping VM…")
    try:
        await context.vm.stop(force=True)
        log.info("Test VM stopped")
    except Exception as e:
        _surface_error("stop", "Stopping VM", e)

    if keep_vm:
        log.info("Keeping overlay and libvirt domain (--keep-vm specified)")
        # Earlier steps (disconnect/stop) may have failed; surface them even
        # when --keep-vm short-circuits the remaining teardown.
        if cleanup_errors:
            raise _CleanupFailed(cleanup_errors)
        return

    # Delete the experiment overlay, leaving the immutable base disk intact
    _update_message("Cleaning up overlay disk…")
    if hasattr(context.vm, 'cleanup_overlay_disk'):
        experiment_id = context.experiment_run_ulid or 'default'
        try:
            await context.vm.cleanup_overlay_disk(experiment_id)
            log.info(f"Cleaned up QEMU overlay for test {experiment_id}")
        except Exception as e:
            _surface_error("overlay", "Cleaning up overlay disk", e)

    # Undefine the transient libvirt domain to avoid stale disk references
    _update_message("Undefining libvirt domain…")
    if hasattr(context.vm, '_libvirt_domain'):
        try:
            import libvirt

            if context.vm._libvirt_domain:
                try:
                    state, _ = context.vm._libvirt_domain.state()
                    if state == libvirt.VIR_DOMAIN_SHUTOFF:
                        # UEFI guests (e.g. win11arm2) carry an NVRAM varstore;
                        # a bare undefine() is rejected for those. Mirror the
                        # flags used in QEMUVM.remove() (vm.py).
                        flags = (libvirt.VIR_DOMAIN_UNDEFINE_MANAGED_SAVE |
                                 libvirt.VIR_DOMAIN_UNDEFINE_SNAPSHOTS_METADATA |
                                 libvirt.VIR_DOMAIN_UNDEFINE_NVRAM)
                        try:
                            context.vm._libvirt_domain.undefineFlags(flags)
                        except AttributeError:
                            context.vm._libvirt_domain.undefine()
                        log.info(f"Undefined libvirt domain '{context.vm.vm_name}'")
                    else:
                        log.warning(
                            f"Cannot undefine domain '{context.vm.vm_name}' - "
                            f"still running (state: {state})."
                        )
                except libvirt.libvirtError as e:
                    _surface_error("undefine", "Undefining libvirt domain", e)
                finally:
                    context.vm._libvirt_domain = None
        except Exception as e:
            _surface_error("undefine", "Undefining libvirt domain", e)

    # Remove the temporary SMB share directory staged for the test (if any)
    _update_message("Removing temp SMB share…")
    smb_dir = getattr(context, '_test_smb_dir', None)
    try:
        if smb_dir:
            import shutil
            shutil.rmtree(smb_dir, ignore_errors=True)
            log.debug(f"Removed test SMB share directory: {smb_dir}")
    except Exception as e:
        _surface_error("smb", "Removing temp SMB share", e)

    if cleanup_errors:
        log.warning(f"VM test cleanup completed with {len(cleanup_errors)} error(s)")
        raise _CleanupFailed(cleanup_errors)
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
            async with StageCtxManagerLite(VMTestCleanupStage(), flow_console, level=1) as cleanup_cm:
                keep_vm = False
                if context.vm and vm_cleanup_mode == 'keep':
                    keep_vm = True
                    log.info("Keeping VM for further testing (--keep-vm specified)")
                await _cleanup_registered_test_vm(
                    context,
                    keep_vm=keep_vm,
                    flow_console=flow_console,
                    stage_id=cleanup_cm.stage_id,
                )
        except _CleanupFailed:
            # Cleanup stage already marked ✖ by __aexit__; per-step ✖ children
            # show the cause. Do NOT re-raise — a cleanup failure must not flip
            # the compatibility verdict.
            pass
        except (OSError, ConnectionError, TimeoutError, RuntimeError) as cleanup_error:
            log.error(f"Error during cleanup: {cleanup_error}")

        # Let the render thread paint the final cleanup state (✖ + child lines)
        # before stop, otherwise the persisted Live frame stays on the last
        # spinning sub-step label.
        await asyncio.sleep(0.3)

        # Stop the flow console
        try:
            from adare.backend.events.coordinator import stop_stage_coordinator
            stop_stage_coordinator()
            flow_console.stop()
            # With the Live display stopped, print the parsed failure block below
            # the persisted tree and before the CLI's ❌ verdict.
            _print_compat_failures(context)
        except (OSError, RuntimeError) as e:
            log.error(f"Error stopping flow console: {e}")
