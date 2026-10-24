"""
What `adare vm test`'s hypervisor flows share: the compatibility checks and their runner.

A flow -- :mod:`~adare.backend.experiment.vm_test_qemu` for registered QEMU VMs,
:mod:`~adare.backend.experiment.vm_test_ova` for VirtualBox OVA files -- boots its
test VM, runs its list of :class:`CompatCheck` through a :class:`CompatRun` and
decides the verdict from the results.

run_command executes a check's command in the guest's native shell -- PowerShell
on Windows guests, bash on Linux -- so every probe is written for both. Windows
PowerShell cmdlets (e.g. Test-Path) do not set a process exit code, so those
branches exit explicitly to make returncode meaningful.
"""

import logging
import socket
import threading
from collections.abc import Awaitable, Callable, Iterable, Sequence
from dataclasses import dataclass, field
from pathlib import PurePosixPath, PureWindowsPath
from typing import TYPE_CHECKING, Any

from adare.backend.experiment.vm_test_report import print_failures, split_reason
from adare.types.stages import (
    Stage,
    VMClickTestStage,
    VMPythonTestStage,
    VMResponseTestStage,
    VMScreenshotTestStage,
    VMUvTestStage,
)

if TYPE_CHECKING:
    from adare.backend.experiment.commands.manage import StageCtxManagerLite

log = logging.getLogger(__name__)

# (passed, failure reason)
CheckResult = tuple[bool, str | None]


@dataclass(frozen=True)
class CompatCheck:
    """One compatibility check: the key its result is stored under, the stage it runs
    under, and the check itself, which gets that stage for progress messages."""

    key: str
    stage: type[Stage]
    run: Callable[[Any, 'StageCtxManagerLite'], Awaitable[CheckResult]]


@dataclass
class CompatRun:
    """Runs compatibility checks under their stages and collects results and failure reasons."""

    context: Any
    flow_console: Any
    results: dict[str, bool] = field(default_factory=dict)
    # (stage message, summary, detail) per failed check, printed after the tree
    failures: list[tuple[str, str, str]] = field(default_factory=list)

    async def run(self, checks: Iterable[CompatCheck]) -> None:
        """Run checks in order; a failure shows as ✖ and keeps its reason for print_failures."""
        from adare.backend.experiment.commands.manage import StageCtxManagerLite

        for check in checks:
            async with StageCtxManagerLite(check.stage(), self.flow_console, level=2) as stage:
                ok, reason = await check.run(self.context, stage)
                stage.set_result(ok)
            self.results[check.key] = ok
            if not ok:
                self.failures.append((stage.stage.msg, *split_reason(reason)))

    def passed(self, keys: Iterable[str]) -> bool:
        """Whether every check under these keys ran and passed."""
        return all(self.results.get(key, False) for key in keys)

    def log_results(self) -> None:
        log.info(f"Compatibility test results: {sum(self.results.values())}/{len(self.results)} tests passed")
        for key, ok in self.results.items():
            log.info(f"  - {key}: {'PASS' if ok else 'FAIL'}")

    def print_failures(self) -> None:
        print_failures(self.failures)


def free_host_port() -> int:
    """A currently free TCP port on the forward bind address, chosen by the OS."""
    from adare.hypervisor.port_forward import forward_bind_host

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind((forward_bind_host(), 0))
        port: int = sock.getsockname()[1]
        return port


def start_flow_console(title: str, user_interrupt_event: threading.Event):
    """Start the VM test's live stage tree and the stage event machinery behind it."""
    from adare.backend.events.coordinator import start_stage_coordinator
    from adare.backend.experiment.diff_run import __create_and_start_flow_console, __start_event_listeners

    flow_console = __create_and_start_flow_console(
        "vm_test", disable_printing=False, external_stop_event=user_interrupt_event
    )
    flow_console.start_experiment_timer(title)
    start_stage_coordinator()
    __start_event_listeners("vm_test")
    return flow_console


def stop_flow_console(flow_console, compat: CompatRun) -> None:
    """Stop the live tree, then print the failure details below it, before the CLI's verdict."""
    from adare.backend.events.coordinator import stop_stage_coordinator

    try:
        stop_stage_coordinator()
        flow_console.stop()
        compat.print_failures()
    except (OSError, RuntimeError) as e:
        # Called from a finally block: must not mask the original error
        log.error(f"Error stopping flow console: {e}")


def is_windows(context) -> bool:
    return 'windows' in context.guest_platform.lower()


async def guest_files_exist(context, names: Sequence[str]) -> CheckResult:
    """Whether the guest sees these files below its shared /adare (C:\\adare) mount point."""
    if is_windows(context):
        paths = ' -and '.join(f"(Test-Path '{PureWindowsPath('C:/adare', name)}')" for name in names)
        command = f"if ({paths}) {{ exit 0 }} else {{ exit 1 }}"
    else:
        command = ' && '.join(f"test -f {PurePosixPath('/adare', name)}" for name in names)
    result = await context.vm.run_command(command, stop_event=context.user_interrupt_event)
    if result.returncode == 0:
        log.info("Shared folders are accessible")
        return True, None
    reason = f"Shared folders not accessible. Exit code: {result.returncode}"
    log.warning(reason)
    return False, reason


async def check_vm_response(context, stage) -> CheckResult:
    """The guest agent runs commands."""
    command = "Write-Output ok" if is_windows(context) else "true"
    result = await context.vm.run_command(command, stop_event=context.user_interrupt_event)
    if result.returncode == 0:
        log.info("VM is responsive to commands")
        return True, None
    reason = f"VM not responding to commands. Exit code: {result.returncode}"
    log.warning(reason)
    return False, reason


async def check_python(context, stage) -> CheckResult:
    """The guest has a Python."""
    if is_windows(context):
        # Windows ships 'python'/'py', not 'python3'. The App Execution Alias
        # stub returns non-zero, so accept either launcher.
        command = "python --version; if ($LASTEXITCODE -eq 0) { exit 0 }; py --version; exit $LASTEXITCODE"
    else:
        command = "python3 --version"
    result = await context.vm.run_command(command, stop_event=context.user_interrupt_event)
    if result.returncode == 0:
        log.info("Python is available")
        return True, None
    reason = f"Python not available. Exit code: {result.returncode}"
    log.warning(reason)
    return False, reason


async def check_uv(context, stage) -> CheckResult:
    """The guest has uv (source installs, and the agent install's fallback for old Pythons)."""
    # 'uv --version' is identical on both shells; inject the user PATH on Windows
    # so a per-user uv install (e.g. %USERPROFILE%\.local\bin) is discoverable.
    result = await context.vm.run_command(
        "uv --version", stop_event=context.user_interrupt_event, inject_user_path=is_windows(context)
    )
    if result.returncode == 0:
        log.info("uv is available")
        return True, None
    reason = f"uv not available. Exit code: {result.returncode}"
    log.warning(reason)
    return False, reason


async def check_agent_screenshot(context, stage) -> CheckResult:
    """The connected agent takes a screenshot in the guest."""
    try:
        result = await context.client.call_tool("screenshot", timeout=10.0)
    except (OSError, ConnectionError, TimeoutError, RuntimeError) as e:
        log.warning(f"Screenshot command error: {e}")
        return False, f"Screenshot command error: {e}"
    if result and not result.get('error'):
        log.info("Screenshot command successful")
        return True, None
    log.warning(f"Screenshot command failed: {result}")
    return False, f"Screenshot command failed: {result}"


async def check_agent_click(context, stage) -> CheckResult:
    """The connected agent clicks in the guest (near the top-left corner, where nothing reacts)."""
    x, y = 10, 10
    try:
        result = await context.client.call_tool("click", {"x": x, "y": y}, timeout=10.0)
    except (OSError, ConnectionError, TimeoutError, RuntimeError) as e:
        log.warning(f"Click command error: {e}")
        return False, f"Click command error: {e}"
    if result and not result.get('error'):
        log.info(f"Click command successful (clicked at {x}, {y})")
        return True, None
    log.warning(f"Click command failed: {result}")
    return False, f"Click command failed: {result}"


VM_RESPONSIVE = CompatCheck('vm_responsive', VMResponseTestStage, check_vm_response)
PYTHON = CompatCheck('python_available', VMPythonTestStage, check_python)
UV = CompatCheck('uv_available', VMUvTestStage, check_uv)
# The agent's own GUI commands: run once a flow's agent connection check passed
AGENT_GUI_CHECKS = (
    CompatCheck('screenshot_command', VMScreenshotTestStage, check_agent_screenshot),
    CompatCheck('click_command', VMClickTestStage, check_agent_click),
)
