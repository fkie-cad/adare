"""Cross-process advisory locking on a lock file (``fcntl.flock``).

ADARE has several caches whose entries live at a *derived* path — a name computed
from a hash of the inputs, so that a second invocation with the same inputs finds
the first one's work instead of redoing it. That is exactly what makes those paths
collision-prone: two concurrent invocations do not merely race, they aim at the
same byte range of the same file on purpose.

The observed damage in the recipe base cache was five concurrent QEMU processes
writing one disk inode and one serial log, with each one's ``--force`` deleting
the file the others were still installing into. A lock is the fix rather than a
per-invocation unique path, because a unique path removes the collision *and* the
cache: N builders would each perform the same 30-minute install and N-1 results
would be thrown away.

Why ``fcntl.flock``:

* POSIX, in the standard library — no new dependency for a correctness fix.
* Released by the kernel when the holding process dies, so a ``SIGKILL``\\ ed build
  cannot wedge a cache permanently. A lock implemented as "create a pidfile and
  check it" fails precisely in that case, which is the case this code has a
  documented history of.
* The lock lives on the open file *description*, so two independent ``os.open``
  calls exclude each other even inside one process — threads in one interpreter
  behave like separate processes here, which is also what makes it testable.

Advisory, not mandatory: it only excludes participants that take the lock. It is a
coordination protocol between ADARE invocations, not a guard against an unrelated
process (or a user with ``rm``) touching the same file.
"""

import fcntl
import logging
import os
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from pathlib import Path

log = logging.getLogger(__name__)


@contextmanager
def exclusive_lock(lock_path: Path,
                   on_contention: Callable[[], None] | None = None) -> Iterator[None]:
    """Hold an exclusive lock on *lock_path* for the duration of the block.

    ``lock_path`` must be a **dedicated lock file that is never unlinked** — never
    the artifact being protected. Two reasons, both of which have teeth:

    * Unlinking a locked file silently ends the exclusion. The lock belongs to the
      inode; once the name is gone the next process ``open``\\ s a *different* inode
      and its ``flock`` succeeds immediately. Everything still looks correct and
      the mutual exclusion is simply absent.
    * The artifact itself is usually published by ``os.replace``, which swaps the
      inode out from under the name — so locking the artifact would drop the lock
      at the exact moment it still matters.

    An empty lock file that outlives every build is the price, and it is the whole
    mechanism: the file's *existence* carries no meaning at all, only the kernel
    lock attached to it does. So there is nothing to clean up and no stale-lock
    recovery path to get wrong.

    Args:
        lock_path: Lock file to create (if absent) and lock. Its parent directory
            is created.
        on_contention: Called once, before blocking, if the lock is already held.
            The point is that the caller can say *what* is being waited for: a
            silent 30-minute wait is indistinguishable from a hang.

    Raises:
        OSError: If the lock file cannot be created or locked.
    """
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    # O_CREAT without O_TRUNC: the file is a lock handle, never a data carrier, so
    # concurrent openers must not disturb each other's content (there is none).
    fd = os.open(lock_path, os.O_RDWR | os.O_CREAT, 0o644)
    try:
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            # Held elsewhere. Announce first, then block: the non-blocking probe
            # exists only to distinguish "free" from "wait" so the wait can be
            # reported.
            if on_contention is not None:
                on_contention()
            log.info('Waiting for the exclusive lock on %s', lock_path)
            fcntl.flock(fd, fcntl.LOCK_EX)
            log.info('Acquired the exclusive lock on %s after waiting', lock_path)
        try:
            yield
        finally:
            fcntl.flock(fd, fcntl.LOCK_UN)
    finally:
        os.close(fd)


@contextmanager
def try_exclusive_lock(lock_path: Path) -> Iterator[bool]:
    """Like :func:`exclusive_lock` but never waits: yields whether it was acquired.

    For callers that must not block — "is somebody working on this right now?" —
    and that have a correct answer for both outcomes. The block always runs; it is
    the yielded flag that says whether the caller holds exclusivity inside it.

    The same never-unlink rule applies: see :func:`exclusive_lock`.
    """
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(lock_path, os.O_RDWR | os.O_CREAT, 0o644)
    acquired = False
    try:
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            acquired = True
        except BlockingIOError:
            acquired = False
        try:
            yield acquired
        finally:
            if acquired:
                fcntl.flock(fd, fcntl.LOCK_UN)
    finally:
        os.close(fd)
