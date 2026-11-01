"""Host-side backend hooks of the VM lifecycle (called from ``VMLifecycleManager``).

Kept here, not inline in ``vm_lifecycle_manager.py``: each hook is the host-side counterpart of a
step the agent backend performs through QGA / the guest agent (file transfer, readiness wait,
artifact retrieval, diff).
"""

from __future__ import annotations

import asyncio
import logging
import threading
from typing import Any, cast

from adare.backend.experiment.stagectxmanager import StageCtxManager
from adare.exceptions import LoggedException

log = logging.getLogger(__name__)


def _ulid(context: Any) -> str:
    return cast(str, context.experiment_run_ulid)


def prepare(context: Any, hypervisor_type: str) -> None:
    """Validate the guest, drop the guest-agent channel from the domain, create the session."""
    from adare.backend.hostside.session import HostsideSession

    platform = (context.guest_platform or '').lower()
    if hypervisor_type != 'qemu' or platform != 'linux':
        raise LoggedException(
            log,
            f"The host-side backend supports QEMU Linux guests only (this environment: "
            f"{hypervisor_type}/{platform or 'unknown'}). Use --backend agent.",
        )
    vm = cast(Any, context.vm)
    # Without the virtio-serial port the guest's qemu-guest-agent has nothing to attach to and does not
    # start: the guest then runs no ADARE-related process at all.
    vm.config.guest_agent_channel = False
    vm._save_vm_config()  # noqa: SLF001 - persisted for libvirt domain XML generation
    context.hostside = HostsideSession(context)
    log.info("Host-side backend: guest-agent channel removed from the domain; no agent will be installed")


async def stage(context: Any) -> None:
    """Replace the file-transfer setup: classify commands, pre-flight, inject into the overlay."""
    from adare.types.stages import HostsideStagingStage

    event = cast(threading.Event, context.user_interrupt_event)
    with StageCtxManager(HostsideStagingStage(), _ulid(context), event=event):
        await context.hostside.stage()


async def boot(context: Any) -> None:
    """Replace the QGA readiness wait: start the VM, wait for a settled desktop, install the client."""
    await context.hostside.boot()
    context.client = context.hostside.make_client()


async def retrieve(context: Any, strategy: Any, event: threading.Event | None) -> None:
    """Make sure the guest is quiesced, extract pending pulls, collect the QEMU logs."""
    from adare.types.stages import VMFileTransferRetrievalStage

    with StageCtxManager(
        VMFileTransferRetrievalStage(), _ulid(context), event=cast(threading.Event, event)
    ) as stage_ctx:
        stage_ctx.stage.sub_msg = 'offline from the quiesced image (no guest agent)'
        session = context.hostside
        if session is None or context.vm is None:
            return
        if not session.quiesced:
            await session.quiesce()  # the playbook ended early: still read a consistent image
            session.finalize_pulls()
        await context.vm.stop(force=True)  # no-op when already off
        strategy._collect_host_qemu_logs(context)  # noqa: SLF001 - shared with the QEMU strategy


async def diff(context: Any, event: threading.Event | None) -> None:
    """Offline base-vs-overlay diff, exported like the virt-diff one."""
    from adare.backend.experiment.filesystem_snapshot import export_diff_bodyfile, export_diff_csv, export_diff_json
    from adare.types.stages import VMHostDiffStage

    with StageCtxManager(VMHostDiffStage(), _ulid(context), event=cast(threading.Event, event)) as stage_ctx:
        session = context.hostside
        if session is None or not session.quiesced or not context.experiment_run_directory:
            log.warning("Host-side diff skipped: the guest was not quiesced (no consistent overlay to read)")
            return
        diff_dir = context.experiment_run_directory.path / 'artifacts' / 'diff'
        diff_dir.mkdir(parents=True, exist_ok=True)
        result = await asyncio.to_thread(session.run_diff)
        if not result:
            return
        metadata = {
            'diff_mode': 'host',
            'tool': 'adare-hostside-dissect',
            'base_disk_path': str(session.base_image),
            'overlay_disk_path': str(session.overlay),
        }
        export_diff_json(result, diff_dir / 'filesystem_diffs.json', metadata)
        export_diff_csv(result, diff_dir / 'filesystem_diffs.csv')
        export_diff_bodyfile(result, diff_dir / 'filesystem_diffs.bodyfile')
        summary = (
            f"Added: {len(result['added'])}, Removed: {len(result['removed'])}, Modified: {len(result['modified'])}"
        )
        stage_ctx.stage.sub_msg = summary
        log.info(f"Host-side diff exported to {diff_dir} ({summary})")


async def finish(context: Any) -> None:
    """Before the overlay is removed: write the run report (footprint from the image) and close the session."""
    from adare.backend.hostside.report import write_run_report

    session = context.hostside
    if session is None:
        return
    if context.experiment_run_directory:
        try:
            await asyncio.to_thread(write_run_report, session)
        except (OSError, ValueError) as e:
            log.warning(f"Host-side report failed: {e}")
    session.close()
