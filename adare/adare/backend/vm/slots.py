"""Cross-process VM slot counter.

``VmInstanceManager`` guards its allocation with an in-process ``threading.Lock``, so two
``adare`` processes can both pass the capacity check and start more VMs than intended.
This module adds a counter that works across processes: ``N`` slot files under the ADARE
data dir (``<appdata>/vm_slots/slot-<i>.lock``), each taken with ``fcntl.flock``. A live VM
holds one slot; a caller that needs the machine to itself takes *all* of them.

Properties:

* The kernel releases a flock when the holding process dies, so a crashed run never leaks a
  slot (there is no counter file to repair).
* ``guard.lock`` orders single takers against an exclusive taker. A taker of all slots holds
  the guard exclusively while it collects the slots, and single takers hold it shared while
  they try, so a stream of single takers cannot starve an exclusive request.
* Exclusive use works even when ``N`` was lowered after slots were handed out: it locks every
  slot file that exists, not just the first ``N``.

``N`` is ``ADARE_MAX_VMS`` (environment), else ``ADARE_MAX_VMS`` in the active user-config
profile, else 20 (the previous ``VmInstanceManager.MAX_INSTANCES_PER_VM``).

A process that took all slots can run adare itself: ``adare vm slots exclusive -- <command>``
(or ``exclusive_env()`` for a subprocess of your own) sets ``ADARE_VM_SLOTS_EXCLUSIVE_PID`` so
that descendants of the holder run under its lease instead of waiting for a slot. The marker is
honoured only while that pid is alive.

Limitation: a slot is held by the process that allocated the instance. A VM that outlives
that process (a detached dev session) stops counting once the process exits.
"""

import contextlib
import logging
import os
import time
from pathlib import Path

from adare.backend.vm.exceptions import VMError

try:  # POSIX only; on Windows hosts the counter is a no-op.
    import fcntl
except ImportError:  # pragma: no cover
    fcntl = None  # type: ignore[assignment]

log = logging.getLogger(__name__)

MAX_VMS_ENV = "ADARE_MAX_VMS"
SLOT_TIMEOUT_ENV = "ADARE_VM_SLOT_TIMEOUT"
EXCLUSIVE_PID_ENV = "ADARE_VM_SLOTS_EXCLUSIVE_PID"
DEFAULT_MAX_VMS = 20  # was VmInstanceManager.MAX_INSTANCES_PER_VM
DEFAULT_SLOT_TIMEOUT = 30.0  # seconds; matches the instance-manager lock timeout
_POLL_SECONDS = 0.2
_SLOT_PREFIX = "slot-"
_SLOT_SUFFIX = ".lock"
_GUARD_NAME = "guard.lock"


class VMSlotTimeout(VMError):
    """No VM slot became free within the timeout."""


def slots_enabled() -> bool:
    return fcntl is not None


def exclusive_env(env: dict[str, str] | None = None) -> dict[str, str]:
    """Environment for a subprocess that runs under this process's exclusive lease."""
    merged = dict(os.environ if env is None else env)
    merged[EXCLUSIVE_PID_ENV] = str(os.getpid())
    return merged


def _under_exclusive_lease() -> bool:
    """True if an ancestor that took all slots (and is still alive) started this process."""
    raw = os.environ.get(EXCLUSIVE_PID_ENV, "").strip()
    if not raw.isdigit():
        return False
    pid = int(raw)
    if pid == os.getpid():
        return False  # the holder itself must not skip: it already holds every slot
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True  # exists, owned by someone else
    return True


def _positive_int(raw, source: str) -> int | None:
    if raw is None or str(raw).strip() == "":
        return None
    try:
        value = int(str(raw).strip())
    except ValueError:
        log.warning(f"{source}={raw!r} is not an integer; ignoring")
        return None
    if value < 1:
        log.warning(f"{source}={raw!r} must be >= 1; ignoring")
        return None
    return value


def max_vm_slots() -> int:
    """Number of VM slots: env ``ADARE_MAX_VMS`` > user config > 20."""
    from_env = _positive_int(os.environ.get(MAX_VMS_ENV), MAX_VMS_ENV)
    if from_env is not None:
        return from_env
    try:
        from adare.config import userconfig

        from_config = _positive_int(userconfig.get(MAX_VMS_ENV), f"{MAX_VMS_ENV} (user config)")
    except (OSError, ValueError, KeyError, TypeError) as exc:  # config must never block a run
        log.debug(f"Could not read {MAX_VMS_ENV} from user config: {exc}")
        from_config = None
    return from_config if from_config is not None else DEFAULT_MAX_VMS


def slot_timeout() -> float:
    raw = os.environ.get(SLOT_TIMEOUT_ENV, "").strip()
    if raw:
        try:
            return max(0.0, float(raw))
        except ValueError:
            log.warning(f"{SLOT_TIMEOUT_ENV}={raw!r} is not a number; using {DEFAULT_SLOT_TIMEOUT}s")
    return DEFAULT_SLOT_TIMEOUT


def slots_dir() -> Path:
    from adare.config.configdirectory import APPDATA_DIR

    return Path(APPDATA_DIR) / "vm_slots"


def _slot_path(directory: Path, index: int) -> Path:
    return directory / f"{_SLOT_PREFIX}{index}{_SLOT_SUFFIX}"


def _existing_slot_count(directory: Path) -> int:
    """One past the highest slot index that has a file (slots may exceed a lowered N)."""
    highest = -1
    if directory.is_dir():
        for entry in directory.iterdir():
            name = entry.name
            if name.startswith(_SLOT_PREFIX) and name.endswith(_SLOT_SUFFIX):
                try:
                    highest = max(highest, int(name[len(_SLOT_PREFIX) : -len(_SLOT_SUFFIX)]))
                except ValueError:
                    continue
    return highest + 1


def _try_lock(fd: int, mode: int) -> bool:
    try:
        fcntl.flock(fd, mode | fcntl.LOCK_NB)
        return True
    except BlockingIOError:
        return False


def _open_lock_file(path: Path) -> int:
    return os.open(path, os.O_RDWR | os.O_CREAT, 0o600)


class SlotLease:
    """Holds one or more slots until :meth:`release` (or process exit)."""

    def __init__(self, fds: dict[int, int], exclusive: bool):
        self._fds = fds  # slot index -> open fd holding the flock
        self.exclusive = exclusive

    @property
    def indices(self) -> list[int]:
        return sorted(self._fds)

    def __len__(self) -> int:
        return len(self._fds)

    def release(self) -> None:
        fds, self._fds = self._fds, {}
        for fd in fds.values():
            with contextlib.suppress(OSError):
                os.close(fd)  # closing the descriptor drops the flock

    def __enter__(self) -> "SlotLease":
        return self

    def __exit__(self, *exc) -> None:
        self.release()

    def __del__(self):
        self.release()


class _NoLease(SlotLease):
    """Returned where flock is unavailable (Windows): nothing to hold."""

    def __init__(self):
        super().__init__({}, exclusive=False)


def _write_holder(fd: int) -> None:
    with contextlib.suppress(OSError):
        os.ftruncate(fd, 0)
        os.pwrite(fd, f"{os.getpid()}\n".encode(), 0)


def _acquire_guard(directory: Path, mode: int, deadline: float) -> int | None:
    """Take ``guard.lock`` in ``mode`` (LOCK_SH or LOCK_EX); None on timeout."""
    fd = _open_lock_file(directory / _GUARD_NAME)
    while True:
        if _try_lock(fd, mode):
            return fd
        if time.monotonic() >= deadline:
            os.close(fd)
            return None
        time.sleep(_POLL_SECONDS)


def acquire_slot(
    timeout: float | None = None, *, max_slots: int | None = None, directory: Path | None = None
) -> SlotLease:
    """Take one free slot, waiting up to ``timeout`` seconds (default ``ADARE_VM_SLOT_TIMEOUT``, 30).

    Raises :class:`VMSlotTimeout` if every slot stays taken.
    """
    if not slots_enabled():
        return _NoLease()
    if _under_exclusive_lease():
        log.debug(f"Running under the exclusive VM-slot lease of pid {os.environ[EXCLUSIVE_PID_ENV]}")
        return _NoLease()
    timeout = slot_timeout() if timeout is None else timeout
    count = max_slots if max_slots is not None else max_vm_slots()
    directory = directory or slots_dir()
    directory.mkdir(parents=True, exist_ok=True)
    deadline = time.monotonic() + timeout

    while True:
        guard = _acquire_guard(directory, fcntl.LOCK_SH, deadline)
        if guard is None:
            raise VMSlotTimeout(
                log, f"Timed out after {timeout:g}s: another process holds all {count} VM slots (exclusive use)"
            )
        try:
            for index in range(count):
                fd = _open_lock_file(_slot_path(directory, index))
                if _try_lock(fd, fcntl.LOCK_EX):
                    _write_holder(fd)
                    log.debug(f"Took VM slot {index}/{count}")
                    return SlotLease({index: fd}, exclusive=False)
                os.close(fd)
        finally:
            os.close(guard)
        if time.monotonic() >= deadline:
            raise VMSlotTimeout(log, f"Timed out after {timeout:g}s: all {count} VM slots are in use")
        time.sleep(_POLL_SECONDS)


def acquire_all_slots(
    timeout: float | None = None, *, max_slots: int | None = None, directory: Path | None = None
) -> SlotLease:
    """Take every slot: exclusive use of the VM capacity (no other adare process can start a VM).

    Waits up to ``timeout`` seconds for running VMs to finish. Raises :class:`VMSlotTimeout`
    (holding nothing) if not all slots can be collected in time.
    """
    if not slots_enabled():
        return _NoLease()
    timeout = slot_timeout() if timeout is None else timeout
    count = max_slots if max_slots is not None else max_vm_slots()
    directory = directory or slots_dir()
    directory.mkdir(parents=True, exist_ok=True)
    count = max(count, _existing_slot_count(directory))
    deadline = time.monotonic() + timeout

    guard = _acquire_guard(directory, fcntl.LOCK_EX, deadline)
    if guard is None:
        raise VMSlotTimeout(log, f"Timed out after {timeout:g}s waiting for another exclusive VM-slot holder")
    taken: dict[int, int] = {}
    try:
        for index in range(count):
            fd = _open_lock_file(_slot_path(directory, index))
            while not _try_lock(fd, fcntl.LOCK_EX):
                if time.monotonic() >= deadline:
                    os.close(fd)
                    raise VMSlotTimeout(
                        log,
                        f"Timed out after {timeout:g}s: only {len(taken)} of {count} VM slots could be taken "
                        f"(slot {index} is held by pid {_holder(directory, index)})",
                    )
                time.sleep(_POLL_SECONDS)
            _write_holder(fd)
            taken[index] = fd
    except BaseException:
        for fd in taken.values():
            os.close(fd)
        raise
    finally:
        os.close(guard)
    log.info(f"Took all {count} VM slots (exclusive use)")
    return SlotLease(taken, exclusive=True)


_PORT_LEASES: dict[tuple[str, int], SlotLease] = {}


def try_reserve_port(kind: str, port: int, *, directory: Path | None = None, reentrant: bool = False) -> bool:
    """Reserve ``port`` for this process across all adare processes (flock, no waiting).

    A bind probe cannot reserve a port: the probe socket is closed before the real server binds,
    and a sibling server that is still importing its libraries has not bound it yet. Holding a
    lock file per (kind, port) closes that gap. A port this process already holds is refused (two runs
    in one process need two ports) unless ``reentrant`` (re-assert after a restart). Release with
    :func:`release_port`; the kernel drops it when the process dies.
    """
    key = (kind, int(port))
    if key in _PORT_LEASES:
        return reentrant
    if not slots_enabled():
        return True
    base = directory or (slots_dir() / "ports")
    base.mkdir(parents=True, exist_ok=True)
    fd = _open_lock_file(base / f"{kind}-{int(port)}.lock")
    if _try_lock(fd, fcntl.LOCK_EX):
        _write_holder(fd)
        _PORT_LEASES[key] = SlotLease({0: fd}, exclusive=False)
        return True
    os.close(fd)
    return False


def release_port(kind: str, port: int) -> None:
    lease = _PORT_LEASES.pop((kind, int(port)), None)
    if lease is not None:
        lease.release()


def _holder(directory: Path, index: int) -> str:
    try:
        return _slot_path(directory, index).read_text().strip() or "unknown"
    except OSError:
        return "unknown"


def slot_status(*, max_slots: int | None = None, directory: Path | None = None) -> dict:
    """Snapshot for ``adare vm slots``: total, taken, free and the holder pids of taken slots."""
    count = max_slots if max_slots is not None else max_vm_slots()
    directory = directory or slots_dir()
    if not slots_enabled():
        return {"enabled": False, "total": count, "taken": 0, "free": count, "holders": {}}
    directory.mkdir(parents=True, exist_ok=True)
    # Scan every slot file: slots above the limit stay held if ADARE_MAX_VMS was lowered.
    holders: dict[int, str] = {}
    for index in range(max(count, _existing_slot_count(directory))):
        path = _slot_path(directory, index)
        if not path.exists():
            continue
        fd = _open_lock_file(path)
        try:
            if _try_lock(fd, fcntl.LOCK_EX):
                fcntl.flock(fd, fcntl.LOCK_UN)
            else:
                holders[index] = _holder(directory, index)
        finally:
            os.close(fd)
    return {
        "enabled": True,
        "total": count,
        "taken": len(holders),
        "free": max(0, count - len(holders)),
        "holders": holders,
    }
