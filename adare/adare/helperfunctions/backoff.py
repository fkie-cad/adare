"""Poll-interval backoff shared by the VM wait loops.

Polling a condition at a flat interval makes every wait cost at least one full
interval, even when the condition is already true. :func:`backoff_delays` starts
short and grows geometrically to a cap, so quick conditions are seen quickly
while long waits still poll at the old, cheap rate. Callers keep their own
deadline / cancellation checks and only take the next sleep from the iterator::

    delays = backoff_delays()
    while time.monotonic() < deadline:
        if done():
            return
        await asyncio.sleep(next(delays))
"""

from collections.abc import Iterator


def backoff_delays(initial: float = 0.05, factor: float = 1.5, cap: float = 0.5) -> Iterator[float]:
    """Yield an endless sequence of sleep durations: *initial*, then ×*factor* per step, never above *cap*."""
    if initial <= 0 or cap <= 0 or factor < 1:
        raise ValueError(f'invalid backoff (initial={initial}, factor={factor}, cap={cap})')
    delay = min(initial, cap)
    while True:
        yield delay
        delay = min(delay * factor, cap)
