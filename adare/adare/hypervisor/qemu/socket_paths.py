"""Where a run's QEMU control sockets live, and whether that path is short enough.

A Unix-domain socket path is stored in ``sockaddr_un.sun_path``: 104 bytes on macOS
(and the BSDs), 108 on Linux, both *including* the terminating NUL. A longer path
cannot be bound or connected, so a QEMU run whose ``<runtime dir>/<instance>.qmp``
is over the limit can never start.

The sockets stay in ``QEMU_STATE_DIR/run`` and are NOT relocated to a short
``/tmp`` directory, because other things expect them there: libvirt's QEMU process
on a Linux host is granted access to ``~/.adare`` by ACL (not to an arbitrary
``/tmp`` directory), the stale-socket sweep and run cleanup work on that one
directory, and the socket paths are recorded in each run's VM config. A path that
cannot fit is therefore reported up front, with the fix: a shorter ``ADARE_HOME``.
"""

import logging
import os
import platform
import re
from pathlib import Path

from adare.config.configdirectory import ADARE_HOME_ENV_VAR, QEMU_STATE_DIR
from adare.exceptions import LoggedErrorException

log = logging.getLogger(__name__)

# Socket files of one instance (``<instance>.qmp`` / ``.qga``); both suffixes are 4 characters.
SOCKET_SUFFIXES = ('.qmp', '.qga')

# Length of the ULID tail that ``run_instance_name`` appends: ``<vm>_run_<8 chars>``
_RUN_ID_TAIL = 8


class SocketPathTooLongError(LoggedErrorException):
    """A QEMU control socket path exceeds the host's ``sun_path`` limit."""


def qemu_runtime_dir_path() -> Path:
    """The directory holding run sockets and pid files, without creating it."""
    return QEMU_STATE_DIR / 'run'


# The macOS/BSD limit: a path that fits it fits on every OS. VM creation and interactive
# sessions place sockets next to disks in arbitrary directories and use this bound.
PORTABLE_SOCKET_PATH_MAX = 103


def unix_socket_path_limit(system: str | None = None) -> int:
    """Longest usable Unix socket path in characters (``sun_path`` size minus the NUL).

    107 on Linux and Windows (108-byte ``sun_path``), 103 on macOS and the BSDs (104).
    """
    system = system or platform.system()
    return 107 if system in ('Linux', 'Windows') else PORTABLE_SOCKET_PATH_MAX


def _name_budget(runtime_dir: Path, limit: int) -> int:
    """Characters left for an instance name once the directory, ``/`` and a suffix are placed."""
    return limit - len(str(runtime_dir)) - 1 - len(SOCKET_SUFFIXES[0])


def check_socket_paths(instance_name: str, runtime_dir: Path | None = None, system: str | None = None) -> None:
    """Raise :class:`SocketPathTooLongError` if any socket of ``instance_name`` would not fit.

    Pure computation: touches no file. ``runtime_dir`` defaults to the managed
    runtime directory, ``system`` to the host OS (both injectable for tests).
    """
    runtime_dir = runtime_dir if runtime_dir is not None else qemu_runtime_dir_path()
    limit = unix_socket_path_limit(system)
    longest = max((runtime_dir / f'{instance_name}{suffix}' for suffix in SOCKET_SUFFIXES), key=lambda p: len(str(p)))
    length = len(str(longest))
    if length <= limit:
        return

    budget = _name_budget(runtime_dir, limit)
    solutions = []
    if budget < 1:
        max_dir = limit - 2 - len(SOCKET_SUFFIXES[0]) - 1  # leave room for a one-character name
        solutions.append(
            f"The socket directory {runtime_dir} is {len(str(runtime_dir))} characters; it must be at most {max_dir}."
        )
    else:
        solutions.append(f"Use a VM name of at most {budget} characters (including its '_run_<id>' suffix).")
    if _home_is_overridden():
        solutions.insert(0, f'Use a shorter {ADARE_HOME_ENV_VAR} (for example /opt/adare or ~/.adare-home).')
    else:
        solutions.append(f'Set {ADARE_HOME_ENV_VAR} to a short directory so the sockets stay within the limit.')
    raise SocketPathTooLongError(
        log,
        f'QEMU socket path too long ({length} > {limit} characters on {system or platform.system()}): {longest}. '
        f'The operating system limits Unix socket paths, so this VM cannot start.',
        possible_solutions=solutions,
    )


def check_run_socket_paths(vm_name: str, machine_key: str | None = None, runtime_dir: Path | None = None) -> None:
    """Check the sockets a run of ``vm_name`` will use, before the run starts anything.

    Builds the instance name exactly as :func:`adare.backend.vm.run_instances.run_instance_name`
    does (``<vm>_run_<8 chars>[_<machine key>]``), with a placeholder run id of the same length.
    """
    name = f'{vm_name}_run_{"0" * _RUN_ID_TAIL}'
    if machine_key:
        name += '_' + re.sub(r'[^A-Za-z0-9-]', '-', machine_key)
    check_socket_paths(name, runtime_dir)


def _home_is_overridden() -> bool:
    return bool(os.getenv(ADARE_HOME_ENV_VAR))
