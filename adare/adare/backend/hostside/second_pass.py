"""Second pass of a host-side run: quiesce the guest, then evaluate the deferred tests on the image."""

from __future__ import annotations

import time
from typing import TYPE_CHECKING, Any, cast

if TYPE_CHECKING:
    from adare.backend.experiment.playbook_controller import PlaybookExecutionResult


async def run_second_pass(controller: Any, first: PlaybookExecutionResult) -> PlaybookExecutionResult:
    """Host-side backend: quiesce the guest, then evaluate the deferred ``test:`` actions against the image.

    The deferred tests run through the normal action pipeline (events, database records, console)
    with the VM stopped, by re-entering ``execute_playbook`` for just their indices; their position
    in the run stays in the qfm step markers. Returns the pass-2 result (or ``first`` when there is
    nothing to evaluate).
    """
    session = controller.hostside
    await session.quiesce()
    session.finalize_pulls()
    if not session.deferred:
        return first
    started = time.monotonic()
    controller._deferred_pass = True  # noqa: SLF001 - the controller reads this flag in execute_playbook
    try:
        result = await controller.execute_playbook(indices=[d.index for d in session.deferred], reload_variables=False)
    finally:
        controller._deferred_pass = False  # noqa: SLF001
    session.timings.evaluate_s = time.monotonic() - started
    return cast('PlaybookExecutionResult', result)
