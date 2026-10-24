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

from adare.backend.experiment.vm_test_qemu import (
    _cleanup_registered_test_vm,
    _CleanupFailed,
    _free_host_port,
    connect_agent_for_test,
    create_qemu_vm_for_test,
    create_registered_test_context,
    setup_qemu_networking_for_test,
    setup_qemu_share_for_test,
    start_agent_for_test,
    start_qemu_test_vm,
)
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
        websocket_port=_free_host_port(),  # outside the experiment pool; free so concurrent tests don't collide
        vm_resolution=(1920, 1080),
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
        ram=context.config.vm_memory,
    )

    # Import OVA file (using same pattern as working vm database import)
    await context.vm.create_from_ovf_or_ova(
        file_path=context._ova_file_path, silent=True, stop_event=context.user_interrupt_event
    )

    # Setup minimal shared directories configuration for testing
    from adare.config import SHARE_POINT_VM

    context.config.shared_directories = {'app': {'host': str(context.adarevm), 'guest': SHARE_POINT_VM}}

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


def _is_qemu(context) -> bool:
    return getattr(context, 'hypervisor_type', None) == 'qemu'


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
    """Test shared folder accessibility: the agent (and on QEMU the run's config.json) reachable in the guest."""
    # QEMU shares an experiment's layout (vm_runtime at vm, run directory at run); OVA the adarevm source at vm
    files = (
        [('run', 'config.json'), ('vm', 'adarevm', 'pyproject.toml')]
        if _is_qemu(context)
        else [('vm', 'pyproject.toml')]
    )
    if _is_windows(context):
        checks = ' -and '.join("(Test-Path 'C:\\adare\\" + '\\'.join(parts) + "')" for parts in files)
        cmd = f"if ({checks}) {{ exit 0 }} else {{ exit 1 }}"
    else:
        cmd = ' && '.join('test -f /adare/' + '/'.join(parts) for parts in files)
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
        cmd = "python --version; if ($LASTEXITCODE -eq 0) { exit 0 }; py --version; exit $LASTEXITCODE"
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


# The share is the host's installed appdata, so whatever the guest agent (root)
# writes there lands on the host and breaks the next `make install`. Keep the venv
# and bytecode in the guest, and --frozen so uv never rewrites the shared uv.lock.
_GUEST_UV_ENV = "export UV_PROJECT_ENVIRONMENT=/var/tmp/adarevm-venv PYTHONDONTWRITEBYTECODE=1; "


async def test_adarevm_server_start(context):
    """Test starting the adarevm WebSocket server from the shared source (VirtualBox/OVA).

    QEMU tests start the agent through the experiment's own install and launch
    instead (``vm_test_qemu.start_agent_for_test``). This launches the ``adarevm``
    console entry point (``adarevm.main:run``) via uv; the server binds
    ``0.0.0.0:18765``. On Windows a user-session scheduled task (``run_as_user``)
    is required for the GUI automation the later screenshot/click tests exercise;
    the scheduled-task runner waits until port 18765 is LISTENING before returning.
    """
    try:
        if _is_windows(context):
            # Editable source is shared at C:\adare\vm (project root with pyproject.toml)
            log_path = r'C:\Windows\Temp'
            # Double quotes only: run_as_user embeds the command in a single-quoted string.
            run_cmd = (
                f'$env:UV_PROJECT_ENVIRONMENT = "{log_path}\\adarevm-venv"; $env:PYTHONDONTWRITEBYTECODE = "1"; '
                'uv run --frozen --package adarevm adarevm'
            )
            start_result = await context.vm.run_command(
                run_cmd,
                cwd=r'C:\adare\vm',
                admin=True,
                run_as_user=True,
                stop_event=context.user_interrupt_event,
                redirect_stdout=rf'{log_path}\adarevm_stdout.log',
                redirect_stderr=rf'{log_path}\adarevm_stderr.log',
            )
            if start_result.returncode == 0:
                log.info("AdareVM server started successfully (port 18765 listening)")
                return True, None
            msg = f"Failed to start adarevm server. Exit code: {start_result.returncode}. stderr: {start_result.stderr}"
            log.warning(msg)
            return False, msg

        # Linux: mirror the real experiment launch (agent_command_builders).
        # The workspace root is shared at /adare/vm; cd into the adarevm member so
        # uv resolves its `adarelib = { workspace = true }` dependency. Pre-sync
        # the venv (the slow build), grant the guest-agent (root) access to the
        # autologin user's X display (DISPLAY/XAUTHORITY + `xhost +SI:localuser:root`),
        # then start adarevm. The guest agent waits for the command's output pipe, so the
        # job is `cmd &`, not `cd X && cmd &`, whose subshell holds that pipe open.
        from adare.backend.experiment.agent_readiness import wait_for_agent

        stop = context.user_interrupt_event
        sync_command = f"{_GUEST_UV_ENV}cd /adare/vm/adarevm && uv sync --frozen 2>&1 | tail -3"
        log.info("Pre-syncing adarevm venv in guest (builds deps)...")
        await context.vm.run_command(sync_command, stop_event=stop)
        start_command = (
            _GUEST_UV_ENV + "export DISPLAY=:0; "
            "export XAUTHORITY=$(ls /run/user/*/gdm/Xauthority /run/user/*/.mutter-Xwaylandauth.* "
            "/run/sddm/* /run/user/*/xauth_* /home/adare/.Xauthority 2>/dev/null | head -1); "
            "xhost +SI:localuser:root >/dev/null 2>&1 || true; "
            "cd /adare/vm/adarevm || exit 1; nohup uv run --frozen adarevm >/tmp/adarevm.log 2>&1 </dev/null &"
        )
        start_result = await context.vm.run_command(start_command, stop_event=stop)
        if start_result.returncode == 0:
            log.info("AdareVM server launched; waiting for it to answer")
            await wait_for_agent(context.config.websocket_port, stop_event=stop)
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
        client = AdareVMClient(port=context.config.websocket_port)
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


def _get_host_gui_executor(context):
    """Return a per-run QEMUHostGUIExecutor bound to the test VM.

    Cached on the context so the screenshot check (which primes the VM's cached
    screen resolution via update_screen_resolution) and the click check that
    follows share the same instance -- the click's coordinate normalization
    depends on the resolution the screenshot recorded.
    """
    executor = getattr(context, '_host_gui_executor', None)
    if executor is None:
        from adare.backend.experiment.execution.qemu_host_gui_executor import (
            QEMUHostGUIExecutor,
        )

        executor = QEMUHostGUIExecutor(context.vm)
        context._host_gui_executor = executor
    return executor


async def test_host_screenshot(context):
    """Test host-side screenshot capture via QMP screendump.

    This is the production-representative path for QEMU experiments (see
    QEMUHostGUIExecutor): the host grabs the framebuffer over QMP, so it works
    regardless of the guest's display server (native Wayland included). A
    non-empty, non-uniform image also proves the autologin desktop actually
    rendered (a black/blank frame means the greeter never handed off).

    The autologin desktop takes time to paint after the guest agent first
    responds, so a fresh boot can briefly return a uniform (black) frame. We
    therefore poll: capture, and if the frame is uniform, nudge input (a
    harmless SHIFT tap wakes any DPMS-blanked display without altering state)
    and retry until the desktop renders or we time out.
    """
    import asyncio
    import base64
    import io

    from PIL import Image

    executor = _get_host_gui_executor(context)

    # Poll up to ~90s for the desktop to render (fresh boot) / wake (blanked).
    max_attempts = 18
    poll_delay = 5.0
    last_error = "no screenshot captured"

    for attempt in range(1, max_attempts + 1):
        try:
            result = await executor.screenshot()

            if not result or result.get('status') != 'success':
                last_error = f"Host/QMP screenshot failed: {(result or {}).get('message', 'no result')}"
            else:
                image = result.get('image') or {}
                data = image.get('data')
                if not data:
                    last_error = "Host/QMP screenshot returned no image data"
                else:
                    img = Image.open(io.BytesIO(base64.b64decode(data))).convert('RGB')
                    if img.width < 1 or img.height < 1:
                        last_error = f"Host/QMP screenshot has invalid size {img.width}x{img.height}"
                    else:
                        # A uniform frame (all-black/single-colour) means the
                        # desktop has not painted yet (or the display is blanked).
                        extrema = img.getextrema()  # ((rmin,rmax),(gmin,gmax),(bmin,bmax))
                        if all(lo == hi for lo, hi in extrema):
                            last_error = (
                                f"Host/QMP screenshot is a uniform {img.width}x{img.height} "
                                f"frame (desktop did not render)"
                            )
                        else:
                            # Cache dimensions for the click check's safe coordinate.
                            context._host_screen_size = (img.width, img.height)
                            log.info(
                                f"Host/QMP screenshot captured ({img.width}x{img.height}, "
                                f"non-uniform) on attempt {attempt}"
                            )
                            return True, None
        except (OSError, ValueError, ConnectionError, TimeoutError, RuntimeError) as e:
            last_error = f"Host/QMP screenshot error: {e}"

        if attempt < max_attempts:
            log.info(f"Host/QMP screenshot attempt {attempt}: {last_error}; nudging + retrying")
            # Wake a possibly DPMS-blanked display; SHIFT is inert (no text/action).
            try:
                await executor.keyboard('press', 'shift')
            except (OSError, ConnectionError, TimeoutError, RuntimeError):
                pass
            await asyncio.sleep(poll_delay)

    log.warning(last_error)
    return False, last_error


async def test_host_click(context):
    """Test host-side mouse click via QMP input-send-event.

    Reuses the executor from test_host_screenshot (which must run first so the
    VM's cached resolution is set for absolute-coordinate normalization). Clicks
    near the screen centre -- a safe spot unlikely to trigger a hot corner.
    """
    try:
        executor = _get_host_gui_executor(context)

        width, height = getattr(context, '_host_screen_size', (0, 0))
        if width and height:
            click_x, click_y = width // 2, height // 2
        else:
            # Screenshot didn't record a size; fall back to a modest coordinate.
            click_x, click_y = 100, 100

        result = await executor.click(click_x, click_y)
        if result and result.get('status') == 'success':
            log.info(f"Host/QMP click successful (clicked at {click_x}, {click_y})")
            return True, None
        msg = (result or {}).get('message', 'no result')
        log.warning(f"Host/QMP click failed: {msg}")
        return False, f"Host/QMP click failed: {msg}"

    except (OSError, ConnectionError, TimeoutError, RuntimeError) as e:
        log.warning(f"Host/QMP click error: {e}")
        return False, f"Host/QMP click error: {e}"


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
        text = text[: objs_match.start()] + '\n' + decoded + '\n' + text[objs_match.end() :]

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
    detail = _decode_guest_stderr(reason[idx + len(marker) :])
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


async def _run_compat_substage(stage_cls, flow_console, context, fn, with_stage=False, **kwargs) -> bool:
    """Run one compatibility test under its stage and reflect the boolean result in the
    stage glyph (✖ on False). The failure reason is NOT emitted into the tree (a
    multiline CLIXML stderr would explode it mid-run); instead the parsed
    ``(summary, detail)`` is collected on ``context.compat_failures`` for the
    end-of-run "Failure details" block. Returns the bool so compatibility_results
    stays a dict of bools (sum() in the verdict logic is unchanged). ``with_stage``
    also hands ``fn`` the stage context, for progress messages."""
    from adare.backend.experiment.commands.manage import StageCtxManagerLite

    async with StageCtxManagerLite(stage_cls(), flow_console, level=2) as cm:
        ok, reason = await (fn(context, cm, **kwargs) if with_stage else fn(context, **kwargs))
        cm.set_result(ok)
        if not ok:
            summary, detail = _split_reason(reason)
            context.compat_failures.append((cm.stage.msg, summary, detail))
        return ok


async def test_vm_compatibility(context, flow_console):
    """Test VM compatibility with ADARE WebSocket server and execute simple experiment commands.

    Args:
        context: ExperimentRunCtx
        flow_console: ExperimentFlowConsole for progress reporting
    """
    from adare.types.stages import (
        VMAdareServerTestStage,
        VMClickTestStage,
        VMHostClickTestStage,
        VMHostScreenshotTestStage,
        VMPythonTestStage,
        VMResponseTestStage,
        VMScreenshotTestStage,
        VMSharedFoldersTestStage,
        VMUvTestStage,
        VMWebSocketTestStage,
    )

    log.info("Testing VM compatibility with ADARE WebSocket server...")

    # QEMU experiments default to host-side QMP GUI automation (Wayland-agnostic)
    # but run their tests through the in-guest agent, so on QEMU the host/QMP
    # screenshot+click and the agent's start + connection are the gating checks,
    # each done the way an experiment does it. The agent's own screenshot/click are
    # exercised too but non-fatal on QEMU -- a native-Wayland session may
    # legitimately fail the X11-only agent capture.
    # VirtualBox/OVA has no QMP, so there the agent path is primary and gating.
    is_qemu = _is_qemu(context)

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
        'click_command': False,
    }
    # Host/QMP results are only populated on QEMU (they gate the QEMU verdict).
    if is_qemu:
        compatibility_results['host_screenshot'] = False
        compatibility_results['host_click'] = False

    try:
        # Test 1: Basic VM responsiveness with substage
        compatibility_results['vm_responsive'] = await _run_compat_substage(
            VMResponseTestStage, flow_console, context, test_vm_response
        )

        # Test 2: Shared folder access with substage
        compatibility_results['shared_folders_working'] = await _run_compat_substage(
            VMSharedFoldersTestStage, flow_console, context, test_shared_folders
        )

        # Test 3: Python availability with substage
        compatibility_results['python_available'] = await _run_compat_substage(
            VMPythonTestStage, flow_console, context, test_python_availability
        )

        # Test 4: uv availability with substage
        compatibility_results['uv_available'] = await _run_compat_substage(
            VMUvTestStage, flow_console, context, test_uv_availability
        )

        # QEMU only: host-side QMP UI checks FIRST -- the gating, production-
        # representative path. Run before the (slow, non-fatal on QEMU) agent
        # server start so the screenshot lands on a freshly-rendered desktop
        # rather than one that has idle-blanked during a long uv sync.
        # Screenshot must precede click so the executor records the screen
        # resolution the click's coordinate normalization needs.
        if is_qemu:
            compatibility_results['host_screenshot'] = await _run_compat_substage(
                VMHostScreenshotTestStage, flow_console, context, test_host_screenshot
            )
            compatibility_results['host_click'] = await _run_compat_substage(
                VMHostClickTestStage, flow_console, context, test_host_click
            )

        # Test 5 + 6: start adarevm and connect to it -- on QEMU through the
        # experiment's own install, launch and connection (vm_test_qemu)
        start_agent, connect_agent = (
            (start_agent_for_test, connect_agent_for_test)
            if is_qemu
            else (test_adarevm_server_start, test_websocket_connection)
        )
        compatibility_results['adarevm_server_starts'] = await _run_compat_substage(
            VMAdareServerTestStage, flow_console, context, start_agent
        )
        compatibility_results['websocket_connection'] = await _run_compat_substage(
            VMWebSocketTestStage, flow_console, context, connect_agent, with_stage=is_qemu
        )

        # Only run WebSocket commands if connection was successful
        if compatibility_results['websocket_connection']:
            # Test 7: Screenshot command with substage
            compatibility_results['screenshot_command'] = await _run_compat_substage(
                VMScreenshotTestStage, flow_console, context, test_screenshot_command
            )

            # Test 8: Click command with substage
            compatibility_results['click_command'] = await _run_compat_substage(
                VMClickTestStage, flow_console, context, test_click_command
            )

    except (OSError, ConnectionError, TimeoutError, RuntimeError) as e:
        log.error(f"Compatibility test error: {e}")

    # Summary
    passed_tests = sum(compatibility_results.values())
    total_tests = len(compatibility_results)

    log.info(f"Compatibility test results: {passed_tests}/{total_tests} tests passed")
    for test_name, result in compatibility_results.items():
        status = "PASS" if result else "FAIL"
        log.info(f"  - {test_name}: {status}")

    if is_qemu:
        # QEMU verdict: QGA-responsive + shared folders + host/QMP screenshot and
        # click + the agent's start and connection (experiments run tests through
        # it). The agent's own screenshot/click are reported but NON-FATAL here
        # (native-Wayland sessions can't do in-guest X11 capture; experiments use QMP).
        gating = {
            key: compatibility_results[key]
            for key in (
                'vm_responsive',
                'shared_folders_working',
                'host_screenshot',
                'host_click',
                'adarevm_server_starts',
                'websocket_connection',
            )
        }
        success = all(gating.values())
        if not success:
            failed = [k for k, v in gating.items() if not v]
            log.warning(f"QEMU compatibility insufficient: failed gating checks: {failed}")
        else:
            log.info("VM appears compatible with ADARE (host/QMP GUI automation and agent working)")
        agent_gui_ok = compatibility_results['screenshot_command'] and compatibility_results['click_command']
        log.info(
            f"Agent GUI (in-guest screenshot/click) checks: {'PASS' if agent_gui_ok else 'FAIL (non-fatal on QEMU)'}"
        )
    else:
        # VirtualBox/OVA: no QMP -- the in-guest agent path is primary and gating.
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


async def ova_test(
    ova_file_path: Path, guest_platform: str, verbose: bool = False, vm_cleanup_mode: str = 'prompt'
) -> bool:
    """
    Test OVA file compatibility with ADARE using separate workflow that reuses existing steps.

    Args:
        ova_file_path: Path to the .ova file to test
        guest_platform: Platform type ('windows' or 'linux') - required
        verbose: Enable verbose logging

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

    # Create and start flow console for better visibility
    from adare.backend.experiment.diff_run import __create_and_start_flow_console, __start_event_listeners

    user_interrupt_event = threading.Event()
    flow_console = __create_and_start_flow_console(
        "vm_test", disable_printing=False, external_stop_event=user_interrupt_event
    )
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
                vm_compatibility_success = await step_runner.run_async_step(
                    lambda ctx: test_vm_compatibility(ctx, flow_console), context
                )

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


async def vm_test_registered(
    vm_name: str,
    disk_path: str,
    guest_platform: str,
    architecture: str = 'x86_64',
    verbose: bool = False,
    vm_cleanup_mode: str = 'prompt',
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
    from adare.backend.experiment.commands.manage import StageCtxManagerLite
    from adare.backend.experiment.step_runner import ExperimentStepRunner
    from adare.types.stages import VMCompatibilityTestStage, VMTestCleanupStage, VMTestSetupStage

    if guest_platform not in ['linux', 'windows']:
        raise LoggedException(log, f"Invalid platform '{guest_platform}'. Must be 'linux' or 'windows'")

    start_time = time.time()

    log.info(f"vm_test_registered started - Testing registered VM: {vm_name}")
    log.info(f"Platform: {guest_platform}, Architecture: {architecture}, Disk: {disk_path}")

    # Create and start flow console for better visibility (use the fixed diff_run import)
    from adare.backend.experiment.diff_run import __create_and_start_flow_console, __start_event_listeners

    user_interrupt_event = threading.Event()
    flow_console = __create_and_start_flow_console(
        "vm_test", disable_printing=False, external_stop_event=user_interrupt_event
    )
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

        # VM Compatibility Testing Phase (guest binds 18765, host connects on the forwarded port)
        vm_compatibility_success = False
        if not stop_event.is_set():
            async with StageCtxManagerLite(VMCompatibilityTestStage(), flow_console, level=1):
                vm_compatibility_success = await step_runner.run_async_step(
                    lambda ctx: test_vm_compatibility(ctx, flow_console), context
                )

        if not vm_compatibility_success:
            log.error("VM compatibility tests failed - VM may not be fully compatible with ADARE")
            flow_console.finish_experiment_timer(success=False)
            return False

        context.vm_test_passed = True  # cleanup drops the run directory (adarevm logs) only then
        elapsed_time = time.time() - start_time
        log.info(
            f"Registered VM test completed successfully! VM is compatible with ADARE. (took {elapsed_time:.1f} seconds)"
        )
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
