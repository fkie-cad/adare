"""Wait for the guest agent (adarevm) to answer instead of sleeping a fixed time.

The probe is the real WebSocket upgrade plus the protocol-2 welcome, never a bare
TCP connect: QEMU user-net ``hostfwd`` accepts on the host port before anything
listens in the guest, so a TCP connect would report a still-starting (or dead)
agent as ready. The handshake only completes once adarevm itself is serving.
"""

import asyncio
import logging
import threading

from adare.backend.experiment.websocket_client import AdareVMClient, AgentAuthError, AgentProtocolError
from adare.helperfunctions.backoff import backoff_delays

log = logging.getLogger(__name__)

# How long ``wait_for_agent`` polls a freshly launched agent before giving up
# (replaces a flat 6 s sleep; the margin covers a slow first ``uv run``).
AGENT_READY_BUDGET = 15.0


async def connect_with_backoff(
    client: AdareVMClient,
    budget: float,
    *,
    initial: float = 0.1,
    cap: float = 2.0,
    attempt_timeout: float = 2.0,
    stop_event: threading.Event | None = None,
) -> bool:
    """Retry ``client.connect`` (quietly) until it succeeds or *budget* seconds have passed.

    Attempts start immediately and are spaced *initial*, 2×, 4×, ... up to *cap*
    seconds apart. On success the client stays connected.

    Returns:
        True once connected; False when the budget runs out or *stop_event* is set.

    Raises:
        AgentAuthError, AgentProtocolError: The agent answered but refused the handshake.
    """
    loop = asyncio.get_running_loop()
    deadline = loop.time() + budget
    delays = backoff_delays(initial=initial, factor=2.0, cap=cap)
    while not (stop_event is not None and stop_event.is_set()):
        timeout = max(0.1, min(attempt_timeout, deadline - loop.time()))
        if await client.connect(timeout=timeout, quiet=True):
            return True
        remaining = deadline - loop.time()
        if remaining <= 0:
            return False
        await asyncio.sleep(min(next(delays), remaining))
    return False


async def wait_for_agent(
    port: int,
    *,
    token: str | None = None,
    budget: float = AGENT_READY_BUDGET,
    stop_event: threading.Event | None = None,
) -> bool:
    """Wait until an adarevm completes a handshake on host *port*, then disconnect.

    An agent that answers but refuses the handshake (wrong token, other protocol)
    counts as up: the caller's own connect reports that error properly.

    Returns:
        True if the agent answered within *budget*, else False.
    """
    client = AdareVMClient(port=port, token=token)
    try:
        ready = await connect_with_backoff(client, budget, stop_event=stop_event)
    except (AgentAuthError, AgentProtocolError) as e:
        log.debug(f"adarevm is up but refused the probe handshake: {e}")
        return True
    if ready:
        await client.disconnect()
    else:
        log.warning(f"adarevm did not answer on port {port} within {budget:.0f}s")
    return ready
